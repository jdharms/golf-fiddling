"""
NES Open Tournament Golf - Highlight State

Manages temporary visual highlights (hover, transform preview, selection).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from editor.tools.transform_tool import TransformToolState


class HighlightState:
    """Manages temporary visual highlights and previews."""

    def __init__(self):
        """Initialize with no highlights."""
        self.shift_hover_tile: int | None = None
        self.transform_state: TransformToolState | None = None
        self.show_invalid_tiles: bool = False
        self.invalid_terrain_tiles: set | None = None
        self.measure_points: list[tuple[int, int]] | None = None

    def set_picker_hover(self, tile_value: int | None):
        """
        Update the shift-hover tile highlight.

        This is called by pickers when hover state changes (callback pattern).

        Args:
            tile_value: Tile value to highlight, or None to clear
        """
        self.shift_hover_tile = tile_value

    def clear_picker_hover(self):
        """Clear shift-hover highlight."""
        self.shift_hover_tile = None
