"""Rebuild the vanilla hole data and the rangefinder's renders from the vanilla ROMs.

The repository holds no vanilla course data. `rehydrate` dumps each ROM it is given into a
scratch directory under the hole store, checks every catalog entry sourced from that ROM
against the dump, and only then moves the hole files into place, so a failed run leaves
the store as it was. The rangefinder is re-rendered from the result. `check_rehydrated`
is the same verification without the dump, and `check_site_data` runs it for the ROMs the
site has before it starts.

The US ROM is required and the JP ROM optional: without it, the Mario Open holes are
neither dumped nor expected.
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from golf.core.course_dump import dump_jp_courses, dump_us_courses
from golf.core.rom_reader import RomReader
from golf.rendering.rangefinder import COURSES as RANGEFINDER_COURSES
from golf.rendering.rangefinder import METADATA, render_rangefinder

from .catalog import JP_ROM, US_ROM, Catalog, CatalogError, HoleStore, RomSource
from .roms import VANILLA_ROMS, VanillaRom

REQUIRED_ROMS = frozenset({US_ROM})
#: how many mismatched holes an error lists before summing up the rest
MAX_PROBLEMS_SHOWN = 10

#: dumps a ROM's courses under a root, as `HoleStore` lays them out
_DUMPERS: dict[str, Callable[[RomReader, Path], None]] = {
    US_ROM: lambda rom, root: dump_us_courses(rom, root),
    JP_ROM: lambda rom, root: dump_jp_courses(rom, root / "jp"),
}


class RehydrateError(Exception):
    """A missing or wrong ROM, or a dump that does not match the catalog."""


@dataclass(frozen=True)
class RehydrateReport:
    #: the ids of the ROMs dumped
    dumped: tuple[str, ...]
    #: the ids of the optional ROMs skipped because their file was not found
    skipped: tuple[str, ...]
    #: holes checked against the catalog
    holes: int


def find_roms(rom_dir: Path) -> dict[str, Path]:
    """The vanilla ROMs present in `rom_dir` under their `roms.py` file names, by id."""
    return {
        rom.id: rom_dir / rom.filename
        for rom in VANILLA_ROMS
        if (rom_dir / rom.filename).is_file()
    }


def check_rom(rom: VanillaRom, path: Path) -> bytes:
    """The ROM's bytes, after checking them against its SHA-1. Raises RehydrateError."""
    data = path.read_bytes()
    actual = hashlib.sha1(data).hexdigest()
    if actual != rom.sha1:
        raise RehydrateError(
            f"{path} is not {rom.title}: SHA-1 {actual}, expected {rom.sha1}"
        )
    return data


def verify_holes(catalog: Catalog, store: HoleStore, rom_ids: Iterable[str]) -> int:
    """Check every live catalog entry sourced from these ROMs against the store.

    Returns the number of holes checked. Raises RehydrateError listing every hole that is
    missing or whose content hash differs.
    """
    rom_ids = set(rom_ids)
    problems = []
    checked = 0
    for entry in catalog:
        source = entry.source
        if entry.withdrawn or not isinstance(source, RomSource):
            continue
        if source.rom not in rom_ids:
            continue
        try:
            store.load(entry)
        except CatalogError as error:
            problems.append(str(error))
        except (KeyError, ValueError) as error:
            problems.append(
                f"{entry.id}: {store.path_for(entry)} is malformed: {error!r}"
            )
        checked += 1
    if problems:
        shown = problems[:MAX_PROBLEMS_SHOWN]
        if len(problems) > len(shown):
            shown.append(f"... and {len(problems) - len(shown)} more")
        raise RehydrateError(
            f"{len(problems)} of {checked} holes do not match the catalog:\n  "
            + "\n  ".join(shown)
        )
    return checked


def check_rangefinder(holes_root: Path, rangefinder_dir: Path) -> None:
    """Check the rangefinder was rendered from the courses under `holes_root`.

    Raises RehydrateError if its metadata is missing or lists different courses or hole
    counts than the store holds.
    """
    metadata_path = rangefinder_dir / METADATA
    if not metadata_path.is_file():
        raise RehydrateError(f"rangefinder metadata not found at {metadata_path}")
    rendered = {
        course_id: len(course["holes"])
        for course_id, course in json.loads(metadata_path.read_text())[
            "courses"
        ].items()
    }
    expected = {
        course_id: count
        for course_id, subpath, _ in RANGEFINDER_COURSES
        if (count := len(list((holes_root / subpath).glob("hole_*.json"))))
    }
    if rendered != expected:
        raise RehydrateError(
            f"rangefinder at {rangefinder_dir} was rendered from other courses than "
            f"{holes_root} holds: rendered {rendered}, expected {expected}"
        )


def check_rehydrated(
    catalog: Catalog,
    holes_root: Path,
    rom_ids: Iterable[str],
    rangefinder_dir: Path | None = None,
) -> int:
    """Verify an earlier rehydration of these ROMs, and the rangefinder if given.

    Returns the number of holes checked. Raises RehydrateError.
    """
    checked = verify_holes(catalog, HoleStore(holes_root), rom_ids)
    if rangefinder_dir is not None:
        check_rangefinder(holes_root, rangefinder_dir)
    return checked


def check_site_data(
    catalog: Catalog, rom_dir: Path, holes_root: Path, rangefinder_dir: Path
) -> int:
    """Check the site can serve: a US ROM, and every ROM's holes and the rangefinder.

    The ROMs in `rom_dir` decide which holes are expected. Returns the number of holes
    checked. Raises RehydrateError.
    """
    roms = find_roms(rom_dir)
    missing = sorted(REQUIRED_ROMS - roms.keys())
    if missing:
        raise RehydrateError(
            f"required ROM missing from {rom_dir}: {', '.join(missing)}"
        )
    return check_rehydrated(catalog, holes_root, roms, rangefinder_dir)


def rehydrate(
    catalog: Catalog,
    holes_root: Path,
    roms: dict[str, Path],
    rangefinder_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> RehydrateReport:
    """Dump, verify and install the vanilla holes of `roms`, a ROM id to file map.

    Raises RehydrateError, leaving the store untouched, if a required ROM is missing, any
    ROM's hash is wrong or a dump does not match the catalog.
    """

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    missing = sorted(REQUIRED_ROMS - roms.keys())
    if missing:
        raise RehydrateError(f"required ROM missing: {', '.join(missing)}")
    present = [rom for rom in VANILLA_ROMS if rom.id in roms]
    contents = {rom.id: check_rom(rom, roms[rom.id]) for rom in present}

    holes_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".rehydrate-", dir=holes_root) as scratch:
        scratch_root = Path(scratch)
        for rom in present:
            say(f"dumping {rom.title}")
            _DUMPERS[rom.id](RomReader.from_bytes(contents[rom.id]), scratch_root)
        checked = verify_holes(
            catalog, HoleStore(scratch_root), [rom.id for rom in present]
        )
        say(f"{checked} holes match the catalog")
        _install(scratch_root, holes_root)

    if rangefinder_dir is not None:
        say(f"rendering the rangefinder to {rangefinder_dir}")
        render_rangefinder(holes_root, rangefinder_dir)

    return RehydrateReport(
        dumped=tuple(rom.id for rom in present),
        skipped=tuple(rom.id for rom in VANILLA_ROMS if rom.id not in roms),
        holes=checked,
    )


def _install(source: Path, target: Path) -> None:
    """Move every file under `source` to the same place under `target`.

    Files, not directories, move, so what else a course directory holds (its `.gitkeep`)
    stays.
    """
    for path in sorted(source.rglob("*")):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, destination)
