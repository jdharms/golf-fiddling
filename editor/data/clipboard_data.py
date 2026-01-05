"""
NES Open Tournament Golf - Clipboard Data

Manages clipboard data for copy/paste operations.
"""

from golf.formats.hole_data import HoleData


class ClipboardData:
    """Stores rectangular region data for copy/paste operations."""

    def __init__(self):
        self.tiles: list[list[int | None]] = []  # None = transparent tile
        self.attributes: list[list[int]] | None = None  # Optional attribute data
        self.width: int = 0
        self.height: int = 0
        self.mode: str = "terrain"  # "terrain" or "greens"
        self.source_region: tuple[int, int, int, int] | None = (
            None  # (row, col, width, height)
        )

    def copy_region(
        self, hole_data: HoleData, rect: tuple[int, int, int, int], mode: str
    ) -> bool:
        """
        Copy a rectangular region from hole data to clipboard.

        Args:
            hole_data: Source hole data
            rect: (start_row, start_col, end_row, end_col) - inclusive bounds
            mode: "terrain" or "greens"

        Returns:
            True if successful, False if region is invalid
        """
        start_row, start_col, end_row, end_col = rect

        # Ensure correct order
        if start_row > end_row:
            start_row, end_row = end_row, start_row
        if start_col > end_col:
            start_col, end_col = end_col, start_col

        self.mode = mode
        self.width = end_col - start_col + 1
        self.height = end_row - start_row + 1

        # Copy tiles based on mode
        if mode == "terrain":
            if start_row < 0 or end_row >= len(hole_data.terrain):
                return False
            if start_col < 0 or end_col >= len(hole_data.terrain[0]):
                return False

            self.tiles = []
            for row_idx in range(start_row, end_row + 1):
                row_data = []
                for col_idx in range(start_col, end_col + 1):
                    row_data.append(hole_data.terrain[row_idx][col_idx])
                self.tiles.append(row_data)

            # Copy attributes (palette data) for terrain
            # Attributes are for 2x2 supertiles
            attr_start_row = start_row // 2
            attr_start_col = start_col // 2
            attr_end_row = end_row // 2
            attr_end_col = end_col // 2

            self.attributes = []
            for attr_row in range(attr_start_row, attr_end_row + 1):
                if attr_row < len(hole_data.attributes):
                    attr_row_data = []
                    for attr_col in range(attr_start_col, attr_end_col + 1):
                        if attr_col < len(hole_data.attributes[attr_row]):
                            attr_row_data.append(
                                hole_data.attributes[attr_row][attr_col]
                            )
                        else:
                            attr_row_data.append(1)  # Default fairway palette
                    self.attributes.append(attr_row_data)

        elif mode == "greens":
            if start_row < 0 or end_row >= len(hole_data.greens):
                return False
            if start_col < 0 or end_col >= len(hole_data.greens[0]):
                return False

            self.tiles = []
            for row_idx in range(start_row, end_row + 1):
                row_data = []
                for col_idx in range(start_col, end_col + 1):
                    row_data.append(hole_data.greens[row_idx][col_idx])
                self.tiles.append(row_data)

            # Greens don't use attributes (always same palette)
            self.attributes = None

        self.source_region = rect
        return True

    def get_tile(self, row: int, col: int) -> int | None:
        """Get tile value at clipboard position (0-indexed)."""
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.tiles[row][col]
        return None

    def clear(self):
        """Clear clipboard contents."""
        self.tiles = []
        self.attributes = None
        self.width = 0
        self.height = 0
        self.source_region = None

    def is_empty(self) -> bool:
        """Check if clipboard is empty."""
        return len(self.tiles) == 0
