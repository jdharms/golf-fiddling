"""
The patch registry: every patch type a recipe or `golf-patch` can name.

Each `PatchSpec` pairs a patch type's id - always the name of the patch it
builds - with a frozen dataclass of parameters, a factory that builds the
patch from them, and an optional report for `golf-patch --verbose`. Parameters
are concrete values: no factory draws anything at random, so a recipe and a
base ROM always build the same ROM.

A new patch is reachable from recipes and `golf-patch` once it has an entry in
`PATCH_SPECS`. See docs/patch_stack.md.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from golf.core.rom_reader import RomReader
from golf.formats.hole_data import HoleData
from golf.qr.port import layout as qr_layout

from .attr_streaming import ATTR_STREAMING_PATCH
from .base import ROMPatch
from .composite import CompositePatch
from .course import CoursePatch
from .course_theme import course_theme_patch
from .menu_trim import menu_trim_patch
from .mercy_tap_in import mercy_tap_in_patches
from .multi_bank import COURSE_MIRRORS_PATCH, MULTI_BANK_CODE_PATCH
from .music_import import music_import_patch
from .practice_swing import DEFAULT_HOLD_FRAMES, practice_swing_patch
from .putting_practice import putting_practice_patches
from .scorecard_course_name import DEFAULT_NAME as DEFAULT_COURSE_NAME
from .scorecard_course_name import scorecard_course_name_patch
from .qr_credentials import load_credentials, qr_credentials_patch
from .scorecard_qr import (
    QR_BANK,
    QR_DISABLE_PATCH,
    SCORECARD_QR_PATCH,
    TRAMPOLINE_CPU_ADDR,
    ScorecardQrPatch,
)
from .seeded_wind import derive_hole_seeds, predict_hole, seeded_wind_patch
from .signpost_banner import remove_course_banner_patches
from .signpost_random_banner import signpost_banner_patch
from .sram_defaults import (
    VANILLA_CLUBS,
    VANILLA_MAGIC,
    VANILLA_NAME,
    club_bag_bytes,
    club_labels,
    magic_bytes,
    sram_defaults_patch,
)
from .wram_expansion import WRAM_EXPANSION_PATCH


class BuildContext:
    """What a factory may look at while building: the base ROM of the stack."""

    def __init__(self, base: bytes):
        self.base = base
        self._reader: RomReader | None = None

    @property
    def reader(self) -> RomReader:
        if self._reader is None:
            self._reader = RomReader.from_bytes(self.base)
        return self._reader


def _no_report(params, patch) -> list[str]:
    return []


@dataclass(frozen=True)
class PatchSpec:
    """One patch type: its id, parameters, factory and report."""

    id: str
    summary: str
    params: type
    build: Callable[[BuildContext, object], ROMPatch]
    report: Callable[[object, ROMPatch], list[str]] = _no_report


# --- Parameters ---------------------------------------------------------------


@dataclass(frozen=True)
class NoParams:
    pass


@dataclass(frozen=True)
class CourseParams:
    #: a directory holding hole_01.json-hole_18.json
    course: Path | None = None
    #: or the 18 hole files, in play order
    holes: list[Path] | None = None


@dataclass(frozen=True)
class CourseThemeParams:
    #: a US ROM course theme: $02 (US), $03 (Japan) or $04 (UK)
    music: int


@dataclass(frozen=True)
class MenuTrimParams:
    #: three 4-6 character header words for menus $00-$02; default OPEN GOLF RANDO
    words: list[str] | None = None


@dataclass(frozen=True)
class SignpostBannerParams:
    #: the edited signpost screen export
    art: Path
    #: the banner the export was drawn over
    banner: str = "us"
    #: the hole the export shows
    hole: int = 1


@dataclass(frozen=True)
class MercyTapInParams:
    mercy_point: int
    #: defaults to mercy_point + 1
    mercy_result: int | None = None


@dataclass(frozen=True)
class SeededWindParams:
    seed: str


@dataclass(frozen=True)
class PracticeSwingParams:
    hold_frames: int = DEFAULT_HOLD_FRAMES


@dataclass(frozen=True)
class ScorecardCourseNameParams:
    #: the word before "COURSE": A-Z, 0-9 and space, at most 13 characters
    name: str = DEFAULT_COURSE_NAME
    #: replaces "18H STROKE PLAY": A-Z, 0-9 and space, at most 26 characters
    title: str | None = None


@dataclass(frozen=True)
class QrCredentialsParams:
    #: a file written by golf-qr-credentials
    credentials: Path


@dataclass(frozen=True)
class MusicImportParams:
    #: a golf-export-music --dump document
    dump: Path
    #: import only this dump music ID, as the one course theme; default all three
    track: int | None = None
    #: defaults to the dump's recorded tuning difference
    transpose_adjust: int | None = None


@dataclass(frozen=True)
class SramDefaultsParams:
    #: 1-10 characters: A-Z, '.' and space
    player_name: str | None = None
    #: up to 14 of 1W-4W, 1I-9I, PW, SW and PT; the putter is added if missing
    clubs: list[str] | None = None
    #: false starts a new save with music off
    bgm: bool = True
    #: the high byte is stored at $6001; neither byte may be $00 or $FF
    sram_magic: int = VANILLA_MAGIC


# --- Factories and reports ------------------------------------------------------


def _build_course(ctx: BuildContext, params: CourseParams) -> ROMPatch:
    if (params.course is None) == (params.holes is None):
        raise ValueError(
            "course takes exactly one of 'course' (a directory) or 'holes' (18 files)"
        )
    if params.holes is not None:
        files = params.holes
    else:
        files = [params.course / f"hole_{number:02d}.json" for number in range(1, 19)]
    holes = []
    for path in files:
        hole = HoleData()
        hole.load(str(path))
        holes.append(hole)
    return CoursePatch(holes)


def _report_course(params: CourseParams, patch: CoursePatch) -> list[str]:
    stats = patch.stats
    lines = [
        f"bank {bank}: {stats.bank_usage[bank]:,} / {capacity:,} bytes"
        for bank, capacity in stats.bank_capacity.items()
    ]
    lines.append(f"greens: {stats.total_greens_bytes:,} bytes")
    lines.append(
        f"scorecard totals: {stats.total_yards:,} yards, par {stats.total_par}"
    )
    return lines


def _build_signpost(ctx: BuildContext, params: SignpostBannerParams) -> ROMPatch:
    return signpost_banner_patch(
        ctx.reader, params.art, banner=params.banner, hole=params.hole
    )


def _report_signpost(params: SignpostBannerParams, patch) -> list[str]:
    ranges = ", ".join(
        f"${first:02X}-${first + count - 1:02X}" for first, count in patch.chunks
    )
    return [
        f"{patch.new_tiles} new tile(s)" + (f" at {ranges}" if ranges else ""),
        *patch.notes,
    ]


def _build_mercy(ctx: BuildContext, params: MercyTapInParams) -> ROMPatch:
    return CompositePatch(
        name="mercy_tap_in",
        description=f"End a hole at stroke {params.mercy_point} with a tap-in",
        patches=mercy_tap_in_patches(params.mercy_point, params.mercy_result),
    )


def _report_seeded_wind(params: SeededWindParams, patch) -> list[str]:
    lines = ["hole  seed  pin  dir  spd  first 6 winds (dir/spd)"]
    for hole, seed in enumerate(derive_hole_seeds(params.seed), start=1):
        forecast = predict_hole(seed, 6)
        winds = " ".join(
            f"{direction:02X}/{speed}" for direction, speed in forecast.winds
        )
        lines.append(
            f"{hole:>4}  {seed:04X}  {forecast.pin_index:>3}  ${forecast.direction_anchor:02X}"
            f"  {forecast.speed_anchor:>3}  {winds}"
        )
    return lines


def _report_qr(params: NoParams, patch: ScorecardQrPatch) -> list[str]:
    return [
        f"image {len(patch.image):,} bytes at bank {QR_BANK} ${qr_layout.TABLE_ORIGIN:04X}",
        f"entry ${patch.entry:04X} QrShowCodes, via the trampoline at ${TRAMPOLINE_CPU_ADDR:04X}",
    ]


def _build_qr_credentials(ctx: BuildContext, params: QrCredentialsParams) -> ROMPatch:
    return qr_credentials_patch(load_credentials(params.credentials))


def _report_qr_credentials(params: QrCredentialsParams, patch) -> list[str]:
    credentials = load_credentials(params.credentials)
    return [
        f"seed ID {credentials.seed_id.hex()}",
        *[
            f"player {slot + 1} {player_id.hex()} (key withheld)"
            for slot, player_id in enumerate(credentials.player_ids)
        ],
    ]


def _build_music(ctx: BuildContext, params: MusicImportParams) -> ROMPatch:
    dump = json.loads(Path(params.dump).read_text())
    return music_import_patch(
        dump, track=params.track, transpose_adjust=params.transpose_adjust
    )


def _report_music(params: MusicImportParams, patch) -> list[str]:
    lines = []
    if patch.track is not None:
        lines.append(
            f"dump music ${patch.track:02X} is the only course theme (CourseBgmTable 03 03 03)"
        )
    lines += [
        f"music ${track['music_id']:02X}: {len(track['patterns'])} patterns, transpose "
        f"{track['transpose']:+d} -> {track['transpose'] + patch.transpose_adjust:+d}"
        for track in patch.tracks
    ]
    lines += [
        f"{name}: {used:,} / {size:,} bytes" for name, used, size in patch.usage()
    ]
    lines.append(
        f"envelope table relocated to ${patch.envelope_addr:04X} ({len(patch.envelope_table)} bytes)"
    )
    return lines


def _report_sram_defaults(params: SramDefaultsParams, patch) -> list[str]:
    name = VANILLA_NAME if params.player_name is None else params.player_name.upper()
    clubs = VANILLA_CLUBS if params.clubs is None else params.clubs
    magic = magic_bytes(params.sram_magic)
    return [
        f"player name: {name}",
        f"clubs: {' '.join(club_labels(club_bag_bytes(clubs)))}",
        f"bgm: {'on' if params.bgm else 'off'}",
        f"sram magic: ${magic[0]:02X} ${magic[1]:02X}",
    ]


def _fixed(patch: ROMPatch) -> Callable[[BuildContext, object], ROMPatch]:
    return lambda ctx, params: patch


PATCH_SPECS: dict[str, PatchSpec] = {
    spec.id: spec
    for spec in [
        PatchSpec(
            "wram_expansion",
            "Grow the terrain buffer past 48 rows (docs/wram_expansion.md)",
            NoParams,
            _fixed(WRAM_EXPANSION_PATCH),
        ),
        PatchSpec(
            "multi_bank_lookup",
            "Look up each hole's terrain bank per hole (docs/multi_bank_terrain.md)",
            NoParams,
            _fixed(MULTI_BANK_CODE_PATCH),
        ),
        PatchSpec(
            "course_mirrors",
            "Make every course slot play course 1",
            NoParams,
            _fixed(COURSE_MIRRORS_PATCH),
        ),
        PatchSpec(
            "attr_streaming",
            "Stream terrain attributes from ROM, lifting the 72-byte limit",
            NoParams,
            _fixed(ATTR_STREAMING_PATCH),
        ),
        PatchSpec(
            "course",
            "Write one 18-hole course (docs/multi_bank_terrain.md)",
            CourseParams,
            _build_course,
            _report_course,
        ),
        PatchSpec(
            "course_theme",
            "Play one of the US ROM's course themes on every course",
            CourseThemeParams,
            lambda ctx, params: course_theme_patch(params.music),
        ),
        PatchSpec(
            "menu_trim",
            "Trim the title, course select and club house menus, under a three-word header (docs/menu_system.md)",
            MenuTrimParams,
            lambda ctx, params: menu_trim_patch(params.words),
        ),
        PatchSpec(
            "remove_course_banner",
            "Drop the country banner from the pre-hole signpost (docs/prehole_signpost.md)",
            NoParams,
            lambda ctx, params: remove_course_banner_patches(),
        ),
        PatchSpec(
            "signpost_random_banner",
            "Draw one banner with new art on the pre-hole signpost (docs/prehole_signpost.md)",
            SignpostBannerParams,
            _build_signpost,
            _report_signpost,
        ),
        PatchSpec(
            "mercy_tap_in",
            "End a hole with a tap-in once a player reaches a stroke count",
            MercyTapInParams,
            _build_mercy,
        ),
        PatchSpec(
            "seeded_wind",
            "Seed pin positions and wind per hole (docs/seeded_wind.md)",
            SeededWindParams,
            lambda ctx, params: seeded_wind_patch(params.seed),
            _report_seeded_wind,
        ),
        PatchSpec(
            "practice_swing",
            "Select toggles practice swings that cost no stroke (docs/practice_swing.md)",
            PracticeSwingParams,
            lambda ctx, params: practice_swing_patch(params.hold_frames),
        ),
        PatchSpec(
            "scorecard_course_name",
            "Show one course name on the scorecard for every course slot (docs/scorecard.md)",
            ScorecardCourseNameParams,
            lambda ctx, params: scorecard_course_name_patch(params.name, params.title),
        ),
        PatchSpec(
            "scorecard_qr",
            "Show a submission QR code after the round, its credentials unfilled (docs/scorecard_qr.md)",
            NoParams,
            _fixed(SCORECARD_QR_PATCH),
            _report_qr,
        ),
        PatchSpec(
            "qr_credentials",
            "Write a seed ID, player IDs and MAC keys into the QR placeholders (docs/scorecard_qr.md)",
            QrCredentialsParams,
            _build_qr_credentials,
            _report_qr_credentials,
        ),
        PatchSpec(
            "qr_disable",
            "Revert the round-end splice so a guest ROM never shows the QR screen",
            NoParams,
            _fixed(QR_DISABLE_PATCH),
        ),
        PatchSpec(
            "music_import",
            "Replace the course themes from a music dump, or make one track the only theme (docs/music_format.md)",
            MusicImportParams,
            _build_music,
            _report_music,
        ),
        PatchSpec(
            "sram_defaults",
            "Change a new save's player name, club bags, BGM option and SRAM magic",
            SramDefaultsParams,
            lambda ctx, params: sram_defaults_patch(
                params.player_name, params.clubs, params.bgm, params.sram_magic
            ),
            _report_sram_defaults,
        ),
        PatchSpec(
            "putting_practice",
            "Experimental: start every hole as a putt (docs/putting_practice.md)",
            NoParams,
            lambda ctx, params: CompositePatch(
                "putting_practice",
                "Start every hole with the ball on the putting surface",
                putting_practice_patches(),
            ),
        ),
    ]
}
