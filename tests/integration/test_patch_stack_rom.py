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
    WRAM_EXPANSION_PATCH,
    CompositePatch,
    CoursePatch,
    PatchStack,
    QrCredentials,
    ROMPatch,
    ScorecardQrPatch,
    StackError,
    menu_trim_patch,
    mercy_tap_in_patches,
    music_import_patch,
    practice_swing_patch,
    remove_course_banner_patches,
    scorecard_course_name_patch,
    seeded_wind_patch,
)
from golf.formats.hole_data import HoleData

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present")


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
        menu_trim_patch("RANDOMIZER0001"),
        scorecard_course_name_patch(title="RANDOMIZER 0001"),
        remove_course_banner_patches(),
        CompositePatch("mercy_tap_in", "mercy tap-in at 10", mercy_tap_in_patches(10)),
        seeded_wind_patch("stack"),
        practice_swing_patch(),
        ScorecardQrPatch(QrCredentials.random(random.Random(1))),
        music_import_patch(json.loads(Path("data/music/music_jp_courses.json").read_text())),
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


def test_the_build_is_deterministic_and_its_ips_reproduces_it(vanilla, full_steps):
    stack = PatchStack(full_steps)
    first = stack.build(vanilla).rom
    assert stack.build(vanilla).rom == first
    assert ips.apply(vanilla, stack.ips(vanilla)) == first


def test_a_missing_requirement_is_reported(vanilla, course):
    with pytest.raises(StackError, match=r"'course' requires course_mirrors \(not in the stack\)"):
        PatchStack([MULTI_BANK_CODE_PATCH, ATTR_STREAMING_PATCH, course]).build(vanilla)


def test_a_requirement_listed_too_late_is_reported(vanilla, course):
    steps = [MULTI_BANK_CODE_PATCH, ATTR_STREAMING_PATCH, course, COURSE_MIRRORS_PATCH]
    with pytest.raises(StackError, match=r"'course' requires course_mirrors \(listed after it\)"):
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
    with pytest.raises(StackError, match="step 'stomp' writes bank 0 \\$8000 .* step 'course' already wrote"):
        PatchStack(steps).build(vanilla)


def test_a_modified_base_is_refused(vanilla):
    modified = bytearray(vanilla)
    modified[-1] ^= 0xFF
    with pytest.raises(StackError, match="SHA-1"):
        PatchStack([]).build(bytes(modified))


def test_a_prepatched_base_satisfies_requirements(vanilla, course):
    base = PatchStack([MULTI_BANK_CODE_PATCH, COURSE_MIRRORS_PATCH, ATTR_STREAMING_PATCH]).build(vanilla).rom
    result = PatchStack([course], base_sha1=None).build(base)
    assert result.regions["course"]
