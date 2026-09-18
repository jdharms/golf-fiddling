"""Integration: the two-stage build from a generated manifest, on the real vanilla ROM."""

from dataclasses import replace
from pathlib import Path

import pytest

from golf.core import ips
from golf.core.patches import PatchStack, StackError
from golf.core.patches.qr_credentials import PLACEHOLDERS, placeholder_offset
from golf.core.patches.scorecard_qr import SCORECARD_QR_PATCH
from golf.core.patches.sram_defaults import MAGIC_CHECK_ADDRS, Club, magic_bytes
from golf.qr import port
from golf.randomizer.build import (
    BuildError,
    PlayerOptions,
    build_unfinished,
    credentials_for,
    finish,
    finishing_steps,
    unfinished_steps,
)
from golf.randomizer.catalog import US_ROM, Catalog, HoleStore
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.generate import generate
from golf.randomizer.manifest import ClubRules, Settings

ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = ROOT / "nes_open_us.nes"
HEADER = 0x10

pytestmark = pytest.mark.skipif(
    not ROM_PATH.exists(), reason=f"{ROM_PATH.name} not present"
)

UNFINISHED_ORDER = [
    "wram_expansion",
    "multi_bank_lookup",
    "course_mirrors",
    "attr_streaming",
    "course",
    "seeded_wind",
    "music_import",
    "mercy_tap_in",
    "scorecard_qr",
    "signpost_random_banner",
    "scorecard_course_name",
    "menu_trim",
]

OPTIONS = PlayerOptions(
    "LUIGI", frozenset({Club.W1, Club.W3, Club.I5, Club.PW, Club.SW}), bgm=False
)
CREDENTIALS = credentials_for(
    839299365868340223, 0xDEADBEEF, (b"\x11" * 8, b"\x22" * 8)
)


@pytest.fixture(scope="module")
def vanilla() -> bytes:
    return ROM_PATH.read_bytes()


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def store() -> HoleStore:
    return HoleStore()


@pytest.fixture(scope="module")
def curation() -> CurationSnapshot:
    return CurationSnapshot.load()


@pytest.fixture(scope="module")
def jp_manifest(catalog, curation):
    return generate(
        catalog, curation, Settings(prng_seed="build-stages-jp", music="jp_france")
    )


@pytest.fixture(scope="module")
def nes_manifest(catalog, curation):
    settings = Settings(
        prng_seed="build-stages-nes", sources={US_ROM}, music="nes_us", mercy_point=None
    )
    return generate(catalog, curation, settings)


@pytest.fixture(scope="module")
def unfinished(jp_manifest, catalog, store, vanilla):
    return build_unfinished(jp_manifest, catalog, store, vanilla)


@pytest.fixture(scope="module")
def signed_in(jp_manifest, vanilla, unfinished):
    return finish(jp_manifest, vanilla, unfinished.ips, OPTIONS, CREDENTIALS)


@pytest.fixture(scope="module")
def guest(jp_manifest, vanilla, unfinished):
    return finish(jp_manifest, vanilla, unfinished.ips, OPTIONS)


def file_offsets(regions) -> set[int]:
    return {HEADER + i for start, end in regions for i in range(start, end)}


def prg_bytes(regions) -> set[int]:
    return {i for start, end in regions for i in range(start, end)}


def changed(before: bytes, after: bytes) -> set[int]:
    return {i for i in range(len(before)) if before[i] != after[i]}


# -- Unfinished ------------------------------------------------------------------------------


def test_the_unfinished_rom_runs_every_step_in_order(unfinished):
    assert list(unfinished.regions) == UNFINISHED_ORDER
    for name, regions in unfinished.regions.items():
        assert regions, f"{name} wrote nothing"


def test_the_unfinished_ips_rebuilds_the_rom(unfinished, vanilla):
    assert ips.apply(vanilla, unfinished.ips) == unfinished.rom


def test_the_unfinished_build_is_deterministic(
    unfinished, jp_manifest, catalog, store, vanilla
):
    assert build_unfinished(jp_manifest, catalog, store, vanilla).ips == unfinished.ips


def test_the_unfinished_rom_holds_the_placeholder_fill(unfinished):
    for _, symbol, length in PLACEHOLDERS:
        start = HEADER + placeholder_offset(symbol)
        assert (
            unfinished.rom[start : start + length] == bytes([port.PATCH_FILL]) * length
        )


def test_a_nes_open_seed_repoints_the_theme_and_can_leave_out_mercy(
    nes_manifest, catalog, store, vanilla
):
    names = [
        step.name for step in unfinished_steps(nes_manifest, catalog, store, vanilla)
    ]
    assert "course_theme" in names and "music_import" not in names
    assert "mercy_tap_in" not in names
    build = build_unfinished(nes_manifest, catalog, store, vanilla)
    table = HEADER + 0x3C000 + (0xDA14 - 0xC000)
    assert build.rom[table : table + 3] == b"\x02\x02\x02"


def test_the_base_must_be_vanilla(jp_manifest, catalog, store, unfinished):
    with pytest.raises(BuildError, match="SHA-1"):
        build_unfinished(jp_manifest, catalog, store, unfinished.rom)


# -- Finished --------------------------------------------------------------------------------


def test_signed_in_finishing_changes_only_defaults_and_credentials(
    signed_in, unfinished, vanilla
):
    assert list(signed_in.regions) == ["sram_defaults", "qr_credentials"]
    allowed = file_offsets(signed_in.regions["sram_defaults"]) | file_offsets(
        signed_in.regions["qr_credentials"]
    )
    assert changed(unfinished.rom, signed_in.rom) <= allowed
    assert ips.apply(vanilla, signed_in.ips) == signed_in.rom

    values = {
        "seed_id": CREDENTIALS.seed_id,
        "player_ids": b"".join(CREDENTIALS.player_ids),
        "mac_keys": b"".join(CREDENTIALS.keys),
    }
    for suffix, symbol, length in PLACEHOLDERS:
        start = HEADER + placeholder_offset(symbol)
        assert signed_in.rom[start : start + length] == values[suffix]


def test_guest_finishing_changes_only_defaults_and_the_splice(
    guest, unfinished, vanilla
):
    assert list(guest.regions) == ["sram_defaults", "qr_disable"]
    splice = HEADER + SCORECARD_QR_PATCH.splice_offset
    allowed = file_offsets(guest.regions["sram_defaults"]) | {splice, splice + 1}
    assert changed(unfinished.rom, guest.rom) <= allowed
    assert guest.rom[splice : splice + 2] == vanilla[splice : splice + 2]
    assert ips.apply(vanilla, guest.ips) == guest.rom


def test_finishing_writes_the_seeds_sram_magic(signed_in, jp_manifest):
    magic = jp_manifest.course.sram_magic
    for index, addr in enumerate(MAGIC_CHECK_ADDRS):
        operand = HEADER + 9 * 0x4000 + (addr - 0x8000)
        assert signed_in.rom[operand] == magic_bytes(magic)[index]


@pytest.mark.parametrize("flavour", ["signed_in", "guest"])
def test_the_stages_overlap_only_where_scorecard_qr_wrote(flavour, request, unfinished):
    finished = request.getfixturevalue(flavour)
    unfinished_bytes = set().union(
        *(prg_bytes(regions) for regions in unfinished.regions.values())
    )
    finishing_bytes = set().union(
        *(prg_bytes(regions) for regions in finished.regions.values())
    )
    overlap = unfinished_bytes & finishing_bytes
    assert overlap, "the QR finishing patch should rewrite bytes scorecard_qr wrote"
    assert overlap <= prg_bytes(unfinished.regions["scorecard_qr"])


@pytest.mark.parametrize(
    "credentials, finisher", [(CREDENTIALS, "qr_credentials"), (None, "qr_disable")]
)
def test_one_stack_of_both_stages_is_refused_at_the_qr_patch(
    credentials, finisher, jp_manifest, catalog, store, vanilla
):
    steps = unfinished_steps(jp_manifest, catalog, store, vanilla)
    steps += finishing_steps(OPTIONS, jp_manifest.course.sram_magic, credentials)
    with pytest.raises(StackError, match=f"step '{finisher}'.*scorecard_qr"):
        PatchStack(steps).build(vanilla)


def test_finishing_refuses_a_bag_the_seed_forbids(jp_manifest, vanilla, unfinished):
    strict = replace(
        jp_manifest,
        course=replace(jp_manifest.course, clubs=ClubRules(banned={Club.W1})),
    )
    with pytest.raises(BuildError, match="bans 1W"):
        finish(strict, vanilla, unfinished.ips, OPTIONS)


def test_finishing_refuses_a_non_vanilla_base(jp_manifest, unfinished):
    with pytest.raises(BuildError, match="SHA-1"):
        finish(jp_manifest, unfinished.rom, unfinished.ips, OPTIONS)
