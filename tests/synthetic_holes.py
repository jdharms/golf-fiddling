"""Made-up holes, for tests that need hole data but not a real course's.

Vanilla holes come from `golf-rehydrate` through the fixtures in `tests/conftest.py` and
are absent on a fresh clone; these always exist.
"""

from pathlib import Path

from golf.core.palettes import GREENS_WIDTH, TERRAIN_WIDTH
from golf.formats.hole_data import HoleData


def synthetic_hole(number: int = 1) -> HoleData:
    """A made-up hole: any hole will do where the content, not the course, is tested."""
    hole = HoleData()
    # Few distinct tiles, so that 18 of them compress into a course
    hole.terrain = [
        [0xA0 + (row + col) % 4 for col in range(TERRAIN_WIDTH)] for row in range(30)
    ]
    hole.terrain[0][0] = number
    hole.terrain_height = 30
    hole.attributes = [[number % 4] * 11 for _ in range(15)]
    # The rough's checkerboard, as the real greens are around their putting surface
    hole.greens = [
        [(0x29, 0x2C)[(row + col) % 2] for col in range(GREENS_WIDTH)]
        for row in range(24)
    ]
    hole.green_x, hole.green_y = 100, 80
    hole.metadata = {
        "hole": number,
        "par": 3 + number % 3,
        "distance": 300 + number,
        "handicap": number,
        "scroll_limit": 20,
        "tee": {"x": 88, "y": 300},
        "flag_positions": [{"x_offset": 64 + i, "y_offset": 64} for i in range(4)],
        "_debug": {},
    }
    return hole


def write_courses(root: Path, *courses: str) -> Path:
    """Write 18 synthetic holes per course where the store looks for the US ROM's."""
    for course in courses:
        (root / course).mkdir(parents=True)
        for number in range(1, 19):
            synthetic_hole(number).save(str(root / course / f"hole_{number:02d}.json"))
    return root
