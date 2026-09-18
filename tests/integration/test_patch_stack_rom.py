"""Integration tests: a full randomizer patch stack built on the real vanilla ROM."""

import json
import random
from pathlib import Path

import pytest

from golf.core import ips
from golf.core.patches import (
    ATTR_STREAMING_PATCH,
    COURSE_MIRRORS_PATCH,
    MULTI_BANK_CODE_PATCH,
    QR_DISABLE_PATCH,
    SCORECARD_QR_PATCH,
    WRAM_EXPANSION_PATCH,
    CompositePatch,
    CoursePatch,
    PatchStack,
    QrCredentials,
    ROMPatch,
    StackError,
    menu_trim_patch,
    mercy_tap_in_patches,
    music_import_patch,
    practice_swing_patch,
    qr_credentials_patch,
    remove_course_banner_patches,
    scorecard_course_name_patch,
    seeded_wind_patch,
    sram_defaults_patch,
)
from golf.formats.hole_data import HoleData

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)


def load_holes(course_dir: str) -> list[HoleData]:
    holes = []
    for number in range(1, 19):
        hole = HoleData()
        hole.load(f"{course_dir}/hole_{number:02d}.json")
        holes.append(hole)
    return holes


@pytest.fixture(scope="module")
def vanilla() -> bytes:
    return Path(ROM_PATH).read_bytes()


@pytest.fixture(scope="module")
def course() -> CoursePatch:
    return CoursePatch(load_holes("courses/jp/jp_uk"))


@pytest.fixture(scope="module")
def full_steps(course) -> list[ROMPatch]:
    return [
        WRAM_EXPANSION_PATCH,
        MULTI_BANK_CODE_PATCH,
        COURSE_MIRRORS_PATCH,
        ATTR_STREAMING_PATCH,
        course,
        menu_trim_patch("RANDO GOLF 0001"),
        scorecard_course_name_patch(title="RANDOMIZER 0001"),
        remove_course_banner_patches(),
        CompositePatch("mercy_tap_in", "mercy tap-in at 10", mercy_tap_in_patches(10)),
        seeded_wind_patch("stack"),
        practice_swing_patch(),
        SCORECARD_QR_PATCH,
        sram_defaults_patch(
            "RANDO", ["1W", "3W", "5I", "PW", "SW"], bgm=False, sram_magic=0x5244
        ),
        music_import_patch(
            json.loads(Path("data/music/music_jp_courses.json").read_text()), track=0x0C
        ),
    ]


class RawWrite(ROMPatch):
    def __init__(self, name: str, prg_offset: int, data: bytes):
        self.name = name
        self.description = name
        self.prg_offset = prg_offset
        self.data = data

    def can_apply(self, rom_writer) -> bool:
        return True

    def is_applied(self, rom_writer) -> bool:
        return False

    def apply(self, rom_writer) -> None:
        rom_writer.write_prg(self.prg_offset, self.data)


def test_every_patch_builds_together(vanilla, full_steps):
    result = PatchStack(full_steps).build(vanilla)

    assert set(result.regions) == {step.name for step in full_steps}
    for name, regions in result.regions.items():
        assert regions, f"{name} wrote nothing"

    bank2_terrain = range(2 * 0x4000 + 0x037F, 2 * 0x4000 + 0x2554)
    assert not any(start in bank2_terrain for start, _ in result.regions["course"])
    assert any(start in bank2_terrain for start, _ in result.regions["scorecard_qr"])


@pytest.fixture(scope="module")
def unfinished(vanilla, full_steps) -> bytes:
    return PatchStack(full_steps).build(vanilla).rom


def test_finishing_with_credentials_builds_on_the_unfinished_rom(vanilla, unfinished):
    credentials = QrCredentials.random(random.Random(1))
    finished = PatchStack([qr_credentials_patch(credentials)], base_sha1=None).build(
        unfinished
    )
    written = {
        0x10 + i
        for start, end in finished.regions["qr_credentials"]
        for i in range(start, end)
    }
    changed = {i for i in range(len(unfinished)) if unfinished[i] != finished.rom[i]}
    assert changed and changed <= written
    assert len(written) == 32


def test_finishing_as_a_guest_restores_the_vanilla_wait(vanilla, unfinished):
    guest = PatchStack([QR_DISABLE_PATCH], base_sha1=None).build(unfinished).rom
    offset = 0x10 + SCORECARD_QR_PATCH.splice_offset
    assert guest[offset : offset + 2] == vanilla[offset : offset + 2]
    changed = [i for i in range(len(guest)) if guest[i] != unfinished[i]]
    assert changed and all(offset <= i < offset + 2 for i in changed)


@pytest.mark.parametrize("finishing", ["qr_credentials", "qr_disable"])
def test_finishing_patches_overlap_scorecard_qr_in_one_stack(
    vanilla, full_steps, finishing
):
    """By design: both rewrite bytes scorecard_qr wrote, so they belong in the
    finishing stack on top of the unfinished ROM."""
    patch = (
        qr_credentials_patch(QrCredentials.random(random.Random(1)))
        if finishing == "qr_credentials"
        else QR_DISABLE_PATCH
    )
    with pytest.raises(
        StackError,
        match=f"step '{finishing}' writes .* step 'scorecard_qr' already wrote",
    ):
        PatchStack([*full_steps, patch]).build(vanilla)


def test_the_build_is_deterministic_and_its_ips_reproduces_it(vanilla, full_steps):
    stack = PatchStack(full_steps)
    first = stack.build(vanilla).rom
    assert stack.build(vanilla).rom == first
    assert ips.apply(vanilla, stack.ips(vanilla)) == first


def test_a_missing_requirement_is_reported(vanilla, course):
    with pytest.raises(
        StackError, match=r"'course' requires course_mirrors \(not in the stack\)"
    ):
        PatchStack([MULTI_BANK_CODE_PATCH, ATTR_STREAMING_PATCH, course]).build(vanilla)


def test_a_requirement_listed_too_late_is_reported(vanilla, course):
    steps = [MULTI_BANK_CODE_PATCH, ATTR_STREAMING_PATCH, course, COURSE_MIRRORS_PATCH]
    with pytest.raises(
        StackError, match=r"'course' requires course_mirrors \(listed after it\)"
    ):
        PatchStack(steps).build(vanilla)


def test_an_unchecked_write_over_course_data_is_refused(vanilla, course):
    first_write = course.writes[0]
    steps = [
        MULTI_BANK_CODE_PATCH,
        COURSE_MIRRORS_PATCH,
        ATTR_STREAMING_PATCH,
        course,
        RawWrite("stomp", first_write.prg_offset, b"\xff"),
    ]
    with pytest.raises(
        StackError,
        match="step 'stomp' writes bank 0 \\$8000 .* step 'course' already wrote",
    ):
        PatchStack(steps).build(vanilla)


def test_a_modified_base_is_refused(vanilla):
    modified = bytearray(vanilla)
    modified[-1] ^= 0xFF
    with pytest.raises(StackError, match="SHA-1"):
        PatchStack([]).build(bytes(modified))


def test_a_prepatched_base_satisfies_requirements(vanilla, course):
    base = (
        PatchStack([MULTI_BANK_CODE_PATCH, COURSE_MIRRORS_PATCH, ATTR_STREAMING_PATCH])
        .build(vanilla)
        .rom
    )
    result = PatchStack([course], base_sha1=None).build(base)
    assert result.regions["course"]
