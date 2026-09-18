"""
The hole catalog: every hole a randomizer seed can reference, under ids that never change.

The catalog is frozen and append-only. An entry binds an id to one hole's content, through
a content hash, and to its provenance. Nothing here steers generation: tags, retirement and
families are curation (`golf.randomizer.curation`). A changed hole is a new version of its
lineage, `nes_uk/01@2`, never an edit to an existing entry. See docs/catalog.md.
"""

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from golf.core import jp_rom_utils, rom_utils
from golf.formats.hole_data import HoleData

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = REPO_ROOT / "data" / "catalog" / "holes.json"
DEFAULT_COURSES = REPO_ROOT / "courses"

US_ROM = "nes_open_us"
JP_ROM = "mario_open_jp"
VANILLA_AUTHOR = "Nintendo"

_SEGMENT = r"[a-z0-9_]+"
LINEAGE_PATTERN = re.compile(rf"{_SEGMENT}/{_SEGMENT}")
_ID_PATTERN = re.compile(
    rf"(?P<lineage>{_SEGMENT}/{_SEGMENT})(?:@(?P<version>[1-9][0-9]*))?"
)

# HoleData.to_dict() keys whose values reach the ROM (see CoursePatch). `hole` and
# `_debug` do not; nor do terrain rows past `terrain.height`.
ROM_BOUND_KEYS = (
    "par",
    "distance",
    "handicap",
    "scroll_limit",
    "green",
    "tee",
    "flag_positions",
    "terrain",
    "attributes",
    "greens",
)


class CatalogError(Exception):
    """A malformed id or index, or hole data that does not match its catalog entry."""


@dataclass(frozen=True, order=True)
class HoleId:
    """A lineage and a version. `nes_uk/01` and `nes_uk/01@1` are the same id."""

    lineage: str
    version: int = 1

    def __post_init__(self):
        if not LINEAGE_PATTERN.fullmatch(self.lineage):
            raise CatalogError(
                f"bad hole lineage {self.lineage!r}: expected owner/slug"
            )
        if self.version < 1:
            raise CatalogError(f"bad hole version {self.version} for {self.lineage}")

    @classmethod
    def parse(cls, text: "HoleId | str") -> "HoleId":
        if isinstance(text, HoleId):
            return text
        match = _ID_PATTERN.fullmatch(text)
        if not match:
            raise CatalogError(
                f"bad hole id {text!r}: expected owner/slug or owner/slug@N"
            )
        return cls(match["lineage"], int(match["version"] or 1))

    def __str__(self) -> str:
        return self.lineage if self.version == 1 else f"{self.lineage}@{self.version}"


def content_hash(hole: HoleData) -> str:
    """SHA-256 over the canonical form of everything about a hole that reaches the ROM."""
    data = hole.to_dict()
    canonical = {key: data[key] for key in ROM_BOUND_KEYS}
    canonical["terrain"] = {
        **data["terrain"],
        "rows": data["terrain"]["rows"][: hole.terrain_height],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class RomSource:
    """A vanilla hole: its ROM, the course directory name it dumps to, and its number."""

    rom: str
    course: str
    hole: int

    def to_json(self) -> dict:
        return {"rom": self.rom, "course": self.course, "hole": self.hole}


@dataclass(frozen=True)
class FileSource:
    """A community hole: a hole JSON file, relative to the hole store root."""

    file: str

    def to_json(self) -> dict:
        return {"file": self.file}


Source = RomSource | FileSource


def _source_from_json(hole_id: str, data: dict) -> Source:
    if set(data) == {"rom", "course", "hole"}:
        return RomSource(data["rom"], data["course"], data["hole"])
    if set(data) == {"file"}:
        return FileSource(data["file"])
    raise CatalogError(f"{hole_id}: unrecognized source {data!r}")


@dataclass(frozen=True)
class CatalogEntry:
    id: HoleId
    source: Source
    content_hash: str
    par: int
    distance: int
    author: str
    withdrawn: bool = False

    def to_json(self) -> dict:
        data = {
            "source": self.source.to_json(),
            "content_hash": self.content_hash,
            "par": self.par,
            "distance": self.distance,
            "author": self.author,
        }
        if self.withdrawn:
            data["withdrawn"] = True
        return data


_ENTRY_KEYS = {"source", "content_hash", "par", "distance", "author"}


def _entry_from_json(key: str, data: dict) -> CatalogEntry:
    hole_id = HoleId.parse(key)
    if str(hole_id) != key:
        raise CatalogError(
            f"catalog key {key!r} is not canonical; write it as {hole_id}"
        )
    missing = _ENTRY_KEYS - set(data)
    unknown = set(data) - _ENTRY_KEYS - {"withdrawn"}
    if missing or unknown:
        raise CatalogError(
            f"{key}: missing fields {sorted(missing)}, unknown {sorted(unknown)}"
        )
    return CatalogEntry(
        id=hole_id,
        source=_source_from_json(key, data["source"]),
        content_hash=data["content_hash"],
        par=data["par"],
        distance=data["distance"],
        author=data["author"],
        withdrawn=data.get("withdrawn", False),
    )


@dataclass(frozen=True)
class Catalog:
    """The frozen index. `version` increases whenever entries are added or withdrawn."""

    version: int
    entries: Mapping[HoleId, CatalogEntry] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = DEFAULT_INDEX) -> "Catalog":
        return cls.from_json(json.loads(Path(path).read_text()))

    @classmethod
    def from_json(cls, data: dict) -> "Catalog":
        if set(data) != {"version", "holes"}:
            raise CatalogError(
                f"catalog index needs exactly 'version' and 'holes', got {sorted(data)}"
            )
        entries = {}
        for key, value in data["holes"].items():
            entry = _entry_from_json(key, value)
            entries[entry.id] = entry
        return cls(data["version"], entries)

    def to_json(self) -> dict:
        return {
            "version": self.version,
            "holes": {
                str(hole_id): self.entries[hole_id].to_json()
                for hole_id in sorted(self.entries)
            },
        }

    def save(self, path: Path = DEFAULT_INDEX) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=2) + "\n")

    def __getitem__(self, hole_id: HoleId | str) -> CatalogEntry:
        parsed = HoleId.parse(hole_id)
        try:
            return self.entries[parsed]
        except KeyError:
            raise CatalogError(f"{parsed} is not in the catalog") from None

    def __contains__(self, hole_id: HoleId | str) -> bool:
        return HoleId.parse(hole_id) in self.entries

    def __iter__(self) -> Iterator[CatalogEntry]:
        return iter(self.entries[hole_id] for hole_id in sorted(self.entries))

    def __len__(self) -> int:
        return len(self.entries)

    def lineages(self) -> set[str]:
        return {hole_id.lineage for hole_id in self.entries}

    def newest(self) -> dict[str, CatalogEntry]:
        """Each lineage's highest version, the only one generation may draw.

        Supersession never rolls back: a lineage whose highest version is withdrawn has no
        entry here, even when an older version is not withdrawn.
        """
        highest: dict[str, CatalogEntry] = {}
        for entry in self:
            highest[entry.id.lineage] = entry  # iteration is sorted, so versions ascend
        return {
            lineage: entry for lineage, entry in highest.items() if not entry.withdrawn
        }


class HoleStore:
    """Resolves catalog entries to hole data under a root directory, verifying each hash.

    Vanilla holes live where the dump tools write them: `<root>/<course>/hole_NN.json` for
    the US ROM and `<root>/jp/<course>/hole_NN.json` for Mario Open. Community holes live at
    their file path relative to the root.
    """

    def __init__(self, root: Path = DEFAULT_COURSES):
        self.root = Path(root)

    def path_for(self, entry: CatalogEntry) -> Path:
        source = entry.source
        if isinstance(source, FileSource):
            return self.root / source.file
        if source.rom == US_ROM:
            return self.root / source.course / f"hole_{source.hole:02d}.json"
        if source.rom == JP_ROM:
            return self.root / "jp" / source.course / f"hole_{source.hole:02d}.json"
        raise CatalogError(f"{entry.id}: unknown source ROM {source.rom!r}")

    def load(self, entry: CatalogEntry) -> HoleData:
        if entry.withdrawn:
            raise CatalogError(f"{entry.id} is withdrawn")
        path = self.path_for(entry)
        if not path.exists():
            raise CatalogError(f"{entry.id}: hole data not found at {path}")
        hole = HoleData()
        hole.load(str(path))
        actual = content_hash(hole)
        if actual != entry.content_hash:
            raise CatalogError(
                f"{entry.id}: {path} has content hash {actual}, catalog has {entry.content_hash}"
            )
        return hole


# -- Syncing vanilla holes -----------------------------------------------------------------

VANILLA_COURSES: tuple[tuple[str, str, int], ...] = (
    *(
        (US_ROM, course["name"], rom_utils.HOLES_PER_COURSE)
        for course in rom_utils.COURSES
    ),
    *(
        (JP_ROM, course["name"], jp_rom_utils.HOLES_PER_COURSE)
        for course in jp_rom_utils.COURSES
    ),
)


def vanilla_lineage(rom: str, course: str, hole: int) -> str:
    """`nes_us/07` for the US ROM's courses; Mario Open's dump names already carry `jp_`."""
    prefix = f"nes_{course}" if rom == US_ROM else course
    return f"{prefix}/{hole:02d}"


def vanilla_entry(
    store: HoleStore, rom: str, course: str, hole_number: int
) -> CatalogEntry | None:
    """The version 1 entry for a vanilla hole as dumped under the store, or None if absent."""
    source = RomSource(rom, course, hole_number)
    hole_id = HoleId(vanilla_lineage(rom, course, hole_number))
    probe = CatalogEntry(hole_id, source, "", 0, 0, VANILLA_AUTHOR)
    path = store.path_for(probe)
    if not path.exists():
        return None
    hole = HoleData()
    hole.load(str(path))
    return replace(
        probe,
        content_hash=content_hash(hole),
        par=hole.metadata["par"],
        distance=hole.metadata["distance"],
    )


@dataclass
class SyncReport:
    catalog: Catalog
    added: list[HoleId] = field(default_factory=list)
    verified: list[HoleId] = field(default_factory=list)
    absent: list[HoleId] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatched


def sync_vanilla(catalog: Catalog, store: HoleStore) -> SyncReport:
    """Add version 1 entries for dumped vanilla holes the catalog lacks; verify the rest.

    Never removes or rewrites an entry. An existing entry whose data no longer matches is
    reported in `mismatched`: changed data needs a new version, added by hand.
    """
    entries = dict(catalog.entries)
    report = SyncReport(catalog)
    for rom, course, hole_count in VANILLA_COURSES:
        for number in range(1, hole_count + 1):
            computed = vanilla_entry(store, rom, course, number)
            hole_id = HoleId(vanilla_lineage(rom, course, number))
            existing = entries.get(hole_id)
            if computed is None:
                if existing is not None:
                    report.absent.append(hole_id)
                continue
            if existing is None:
                entries[hole_id] = computed
                report.added.append(hole_id)
            elif existing.withdrawn:
                continue
            elif existing != computed:
                fields = [
                    name
                    for name in ("source", "content_hash", "par", "distance", "author")
                    if getattr(existing, name) != getattr(computed, name)
                ]
                report.mismatched.append(
                    f"{hole_id}: {', '.join(fields)} differ from {store.path_for(existing)}; "
                    "catalog entries never change, so changed data needs a new version"
                )
            else:
                report.verified.append(hole_id)
    if report.added:
        report.catalog = Catalog(catalog.version + 1, entries)
    return report
