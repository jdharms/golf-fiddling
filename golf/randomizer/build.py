"""
The two-stage build: a manifest into an unfinished ROM, and an unfinished ROM into a finished one.

- **Unfinished**, once per seed: the base patches, the course, seeded wind, the course theme,
  mercy tap-in, the scorecard QR image with its credential placeholders at the fill, the
  signpost banner and the magic words on the menus and scorecard. Everything it reads is
  the manifest's `course`, the catalog and the hole store. The site stores the result as an
  IPS against the vanilla ROM.
- **Finished**, per download: the player's new-save defaults under the seed's SRAM magic,
  then either `qr_credentials` (signed in) or `qr_disable` (guest). It runs as a second
  `PatchStack` on the unfinished ROM, since both QR finishing patches rewrite bytes
  `scorecard_qr` wrote.

See docs/randomizer_devplan.md.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from golf.core import ips, rom_utils
from golf.core.patches import (
    ATTR_STREAMING_PATCH,
    COURSE_MIRRORS_PATCH,
    MULTI_BANK_CODE_PATCH,
    QR_DISABLE_PATCH,
    SCORECARD_QR_PATCH,
    WRAM_EXPANSION_PATCH,
    CompositePatch,
    CoursePatch,
    CourseWriteStats,
    PatchStack,
    QrCredentials,
    ROMPatch,
    course_theme_patch,
    menu_trim_patch,
    mercy_tap_in_patches,
    music_import_patch,
    qr_credentials_patch,
    scorecard_course_name_patch,
    seeded_wind_patch,
    sram_defaults_patch,
)
from golf.core.patches.signpost_random_banner import signpost_banner_patch
from golf.core.patches.sram_defaults import (
    Club,
    club_bag_bytes,
    parse_club,
    player_name_bytes,
)
from golf.core.rom_reader import RomReader
from golf.qr import payload

from .catalog import JP_ROM, REPO_ROOT, US_ROM, Catalog, HoleStore
from .manifest import ClubRules, Manifest
from .music import MUSIC_DUMPS, track
from .words import scorecard_title

SIGNPOST_ART = (
    REPO_ROOT / "golf" / "core" / "patches" / "data" / "signpost_random.aseprite"
)

#: The largest seed ID the 8-byte field holds. The site draws below 62**10.
MAX_SEED_ID = (1 << (8 * payload.SEED_ID_LEN)) - 1
MAX_PLAYER_ID = (1 << (8 * payload.PLAYER_ID_LEN)) - 1


class BuildError(ValueError):
    """Inputs a build refuses: player options the seed's rules forbid, or the wrong base ROM."""


# -- Player options -------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayerOptions:
    """What a player chooses at download time. The putter is added to the bag if missing."""

    player_name: str
    clubs: frozenset[Club]
    bgm: bool = True

    def __post_init__(self):
        clubs = frozenset(self.clubs) | {Club.PT}
        object.__setattr__(self, "clubs", clubs)
        try:
            player_name_bytes(self.player_name)
            club_bag_bytes(clubs)
        except ValueError as problem:
            raise BuildError(str(problem)) from None
        if not isinstance(self.bgm, bool):
            raise BuildError("bgm must be true or false")

    def check(self, rules: ClubRules) -> None:
        """Raise BuildError if the bag breaks the seed's club rules."""
        labels = lambda clubs: " ".join(club.label for club in sorted(clubs))  # noqa: E731
        if rules.required_bag is not None and self.clubs != rules.required_bag:
            raise BuildError(
                f"this seed requires the bag {labels(rules.required_bag)}, got {labels(self.clubs)}"
            )
        if len(self.clubs) > rules.max:
            raise BuildError(
                f"this seed allows at most {rules.max} clubs, got {len(self.clubs)}"
            )
        banned = self.clubs & rules.banned
        if banned:
            raise BuildError(f"this seed bans {labels(banned)}")


# -- Credentials ----------------------------------------------------------------------------


def seed_id_bytes(qr_seed_id: int) -> bytes:
    """A seed's `qr_seed_id` as the QR payload's seed ID field: big-endian."""
    if (
        isinstance(qr_seed_id, bool)
        or not isinstance(qr_seed_id, int)
        or not 1 <= qr_seed_id <= MAX_SEED_ID
    ):
        raise BuildError(f"qr_seed_id must be 1-{MAX_SEED_ID}, got {qr_seed_id!r}")
    return qr_seed_id.to_bytes(payload.SEED_ID_LEN, "big")


def player_id_bytes(player_id: int) -> bytes:
    """A user's `player_id` as the QR payload's player ID field: big-endian."""
    if (
        isinstance(player_id, bool)
        or not isinstance(player_id, int)
        or not 1 <= player_id <= MAX_PLAYER_ID
    ):
        raise BuildError(f"player_id must be 1-{MAX_PLAYER_ID}, got {player_id!r}")
    return player_id.to_bytes(payload.PLAYER_ID_LEN, "big")


def credentials_for(
    qr_seed_id: int, player_id: int, keys: tuple[bytes, bytes]
) -> QrCredentials:
    """A signed-in player's credentials: their player ID in both slots, one key per slot."""
    player = player_id_bytes(player_id)
    try:
        return QrCredentials(
            seed_id=seed_id_bytes(qr_seed_id),
            player_ids=(player, player),
            keys=tuple(keys),
        )
    except ValueError as problem:
        raise BuildError(str(problem)) from None


# -- Unfinished -----------------------------------------------------------------------------


def music_step(slug: str) -> ROMPatch:
    """The patch that makes a music slug the course theme.

    A NES Open theme is already in the ROM and only needs `CourseBgmTable`; a Mario Open
    theme is imported from its dump.
    """
    theme = track(slug)
    if theme.rom == US_ROM:
        return course_theme_patch(theme.music_id)
    if theme.rom == JP_ROM:
        dump = json.loads(Path(MUSIC_DUMPS[JP_ROM]).read_text())
        return music_import_patch(dump, track=theme.music_id)
    raise BuildError(
        f"music {slug!r} comes from {theme.rom!r}, which no build knows"
    )  # pragma: no cover


def unfinished_steps(
    manifest: Manifest, catalog: Catalog, store: HoleStore, vanilla: bytes
) -> list[ROMPatch]:
    """The unfinished stack's steps, in order. `vanilla` is read for the signpost art."""
    course = manifest.course
    holes = [store.load(catalog[slot.id]) for slot in course.holes]
    steps: list[ROMPatch] = [
        WRAM_EXPANSION_PATCH,
        MULTI_BANK_CODE_PATCH,
        COURSE_MIRRORS_PATCH,
        ATTR_STREAMING_PATCH,
        CoursePatch(holes),
        seeded_wind_patch(seeds=[slot.wind_seed for slot in course.holes]),
        music_step(course.music),
    ]
    if course.mercy_point is not None:
        steps.append(
            CompositePatch(
                "mercy_tap_in",
                f"End a hole at stroke {course.mercy_point} with a tap-in",
                mercy_tap_in_patches(course.mercy_point),
            )
        )
    steps += [
        SCORECARD_QR_PATCH,
        signpost_banner_patch(RomReader.from_bytes(vanilla), SIGNPOST_ART),
        scorecard_course_name_patch(title=scorecard_title(course.magic_words)),
        menu_trim_patch(list(course.magic_words)),
    ]
    return steps


@dataclass(frozen=True)
class UnfinishedBuild:
    rom: bytes
    #: the IPS from the vanilla ROM to `rom`, what the site stores on the seed row
    ips: bytes
    #: step name -> the [start, end) PRG offset ranges it wrote
    regions: dict[str, list[tuple[int, int]]]
    course_stats: CourseWriteStats


def _check_vanilla(vanilla: bytes) -> None:
    actual = hashlib.sha1(vanilla).hexdigest()
    if actual != rom_utils.US_ROM_SHA1:
        raise BuildError(
            f"the base ROM has SHA-1 {actual}, not the vanilla US ROM's {rom_utils.US_ROM_SHA1}"
        )


def build_unfinished(
    manifest: Manifest, catalog: Catalog, store: HoleStore, vanilla: bytes
) -> UnfinishedBuild:
    _check_vanilla(vanilla)
    steps = unfinished_steps(manifest, catalog, store, vanilla)
    build = PatchStack(steps).build(vanilla)
    course = next(step for step in steps if isinstance(step, CoursePatch))
    return UnfinishedBuild(
        rom=build.rom,
        ips=ips.diff(vanilla, build.rom),
        regions=build.regions,
        course_stats=course.stats,
    )


# -- Finished -------------------------------------------------------------------------------


def finishing_steps(
    options: PlayerOptions, sram_magic: int, credentials: QrCredentials | None
) -> list[ROMPatch]:
    """New-save defaults, then credentials when signed in or the QR screen disabled for a guest."""
    steps: list[ROMPatch] = [
        sram_defaults_patch(
            options.player_name, sorted(options.clubs), options.bgm, sram_magic
        ),
    ]
    steps.append(
        QR_DISABLE_PATCH if credentials is None else qr_credentials_patch(credentials)
    )
    return steps


@dataclass(frozen=True)
class FinishedBuild:
    rom: bytes
    #: the IPS from the vanilla ROM to `rom`, what a download sends
    ips: bytes
    #: step name -> the [start, end) PRG offset ranges the finishing stack wrote
    regions: dict[str, list[tuple[int, int]]]


def finish(
    manifest: Manifest,
    vanilla: bytes,
    unfinished_ips: bytes,
    options: PlayerOptions,
    credentials: QrCredentials | None = None,
) -> FinishedBuild:
    """Finish a seed's stored unfinished IPS for one player. No credentials finishes a guest ROM."""
    _check_vanilla(vanilla)
    options.check(manifest.course.clubs)
    unfinished = ips.apply(vanilla, unfinished_ips)
    steps = finishing_steps(options, manifest.course.sram_magic, credentials)
    build = PatchStack(steps, base_sha1=None).build(unfinished)
    return FinishedBuild(
        rom=build.rom, ips=ips.diff(vanilla, build.rom), regions=build.regions
    )


def clubs_from_labels(labels: Iterable[str]) -> frozenset[Club]:
    """A bag from choose-clubs labels such as `1W` and `PW`, for callers holding strings."""
    try:
        return frozenset(parse_club(label) for label in labels)
    except ValueError as problem:
        raise BuildError(str(problem)) from None
