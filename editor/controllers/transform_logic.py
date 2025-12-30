"""
NES Open Tournament Golf - Transform Logic

Applies compression table transformations to tile values.
"""

from typing import Dict, List


class TransformLogic:
    """Applies compression table transformations."""

    def __init__(self, tables: Dict):
        """Initialize with compression tables.

        Args:
            tables: Compression tables dict with "terrain" and "greens" keys
        """
        self.terrain_horiz: List[int] = tables["terrain"]["horizontal_table"]
        self.terrain_vert: List[int] = tables["terrain"]["vertical_table"]
        self.greens_horiz: List[int] = tables["greens"]["horizontal_table"]
        self.greens_vert: List[int] = tables["greens"]["vertical_table"]

    def apply_horizontal(self, tile_value: int, mode: str) -> int:
        """Apply horizontal table transformation to a tile value.

        Args:
            tile_value: Current tile value (0-255)
            mode: "terrain" or "greens"

        Returns:
            Transformed tile value (or original if out of bounds)
        """
        table = self.terrain_horiz if mode == "terrain" else self.greens_horiz
        if 0 <= tile_value < len(table):
            return table[tile_value]
        return tile_value

    def apply_vertical(self, tile_value: int, mode: str) -> int:
        """Apply vertical table transformation to a tile value.

        Args:
            tile_value: Current tile value (0-255)
            mode: "terrain" or "greens"

        Returns:
            Transformed tile value (or original if out of bounds)
        """
        table = self.terrain_vert if mode == "terrain" else self.greens_vert
        if 0 <= tile_value < len(table):
            return table[tile_value]
        return tile_value
