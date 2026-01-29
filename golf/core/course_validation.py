"""
NES Open Tournament Golf - Course Validation

Validates course data before writing to ROM or saving.
Catches issues like placeholder tiles that would cause compression failures.
"""

from dataclasses import dataclass

from . import rom_utils
from ..formats.hole_data import HoleData


@dataclass
class InvalidTile:
    """A single invalid tile location."""

    row: int
    col: int
    value: int

    def __str__(self) -> str:
        if self.value == 0x100:
            return f"Row {self.row}, Col {self.col}: 0x{self.value:X} (placeholder - unfilled tile)"
        return f"Row {self.row}, Col {self.col}: 0x{self.value:X}"


class InvalidTileError(Exception):
    """Raised when a hole contains invalid tile values (e.g., placeholder tiles)."""

    def __init__(
        self,
        hole_index: int,
        mode: str,
        invalid_tiles: list[InvalidTile],
    ):
        self.hole_index = hole_index
        self.hole_number = (hole_index % rom_utils.HOLES_PER_COURSE) + 1  # 1-indexed
        self.course_number = (hole_index // rom_utils.HOLES_PER_COURSE) + 1  # 1-indexed
        self.mode = mode
        self.invalid_tiles = invalid_tiles
        super().__init__(str(self))

    def __str__(self) -> str:
        lines = [
            f"Course {self.course_number}, Hole {self.hole_number} has invalid {self.mode} tiles:",
            f"  Found {len(self.invalid_tiles)} tile(s) with values outside valid range (0-255):",
        ]

        for tile in self.invalid_tiles[:10]:
            lines.append(f"    {tile}")

        if len(self.invalid_tiles) > 10:
            lines.append(f"    ... and {len(self.invalid_tiles) - 10} more")

        lines.append("")
        lines.append(
            "  Fix: Open this hole in the editor and replace placeholder tiles with valid tiles."
        )

        return "\n".join(lines)


class CourseValidator:
    """Validates course data for ROM writing compatibility.

    Checks that all tile values are valid NES byte values (0-255).
    Placeholder tiles (0x100) used by the editor must be replaced
    before writing to ROM.
    """

    def validate_hole(self, hole_index: int, hole_data: HoleData) -> None:
        """Validate all tiles in a hole are valid byte values (0-255).

        Args:
            hole_index: Global hole index (0-17 for 1 course, 0-35 for 2)
            hole_data: The hole data to validate

        Raises:
            InvalidTileError: If any tiles are outside valid range
        """
        self._validate_terrain(hole_index, hole_data)
        self._validate_greens(hole_index, hole_data)

    def validate_course(self, course_index: int, holes: list[HoleData]) -> None:
        """Validate all holes in a course.

        Args:
            course_index: Course index (0 or 1)
            holes: List of 18 HoleData objects

        Raises:
            InvalidTileError: If any hole has invalid tiles
        """
        base_index = course_index * rom_utils.HOLES_PER_COURSE
        for i, hole_data in enumerate(holes):
            self.validate_hole(base_index + i, hole_data)

    def validate_courses(self, courses: list[list[HoleData]]) -> None:
        """Validate all courses.

        Args:
            courses: List of 1 or 2 course hole lists

        Raises:
            InvalidTileError: If any hole has invalid tiles
        """
        for course_idx, holes in enumerate(courses):
            self.validate_course(course_idx, holes)

    def _validate_terrain(self, hole_index: int, hole_data: HoleData) -> None:
        """Check terrain tiles are valid bytes."""
        invalid: list[InvalidTile] = []

        for row_idx, row in enumerate(hole_data.terrain[: hole_data.terrain_height]):
            for col_idx, tile in enumerate(row):
                if tile < 0 or tile > 255:
                    invalid.append(InvalidTile(row_idx, col_idx, tile))

        if invalid:
            raise InvalidTileError(hole_index, "terrain", invalid)

    def _validate_greens(self, hole_index: int, hole_data: HoleData) -> None:
        """Check greens tiles are valid bytes."""
        invalid: list[InvalidTile] = []

        for row_idx, row in enumerate(hole_data.greens):
            for col_idx, tile in enumerate(row):
                if tile < 0 or tile > 255:
                    invalid.append(InvalidTile(row_idx, col_idx, tile))

        if invalid:
            raise InvalidTileError(hole_index, "greens", invalid)
