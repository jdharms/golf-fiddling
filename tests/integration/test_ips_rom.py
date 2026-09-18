"""Integration tests: IPS patches built from real patched ROMs."""

from pathlib import Path

import pytest

from golf.core import ips
from golf.core.patches import CoursePatch, menu_trim_patch, seeded_wind_patch
from golf.core.rom_writer import RomWriter
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


def test_patched_rom_roundtrips_through_ips(tmp_path):
    vanilla = Path(ROM_PATH).read_bytes()

    course = CoursePatch(load_holes("courses/jp/jp_uk"))
    writer = RomWriter(ROM_PATH, str(tmp_path / "unused.nes"))
    for patch in [
        *course.requires,
        course,
        seeded_wind_patch("ips"),
        menu_trim_patch("ROUND TRIP TEST"),
    ]:
        patch.apply(writer)
    patched = bytes(writer.rom_data)

    patch = ips.diff(vanilla, patched)

    assert ips.apply(vanilla, patch) == patched
    assert len(patch) < len(vanilla) // 4
    # offsets are file offsets: the first change is past the 16-byte iNES header
    assert int.from_bytes(patch[5:8], "big") >= 16
