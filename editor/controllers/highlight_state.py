"""
NES Open Tournament Golf - Highlight State

Manages temporary visual highlights (hover, transform preview, selection).
"""

from typing import Optional
from .transform_drag_state import TransformDragState


class HighlightState:
    """Manages temporary visual highlights and previews."""

    def __init__(self):
        """Initialize with no highlights."""
        self.shift_hover_tile: Optional[int] = None
        self.transform_state: TransformDragState = TransformDragState()
        self.show_invalid_tiles: bool = False
        self.invalid_terrain_tiles: Optional[set] = None

    def set_picker_hover(self, tile_value: Optional[int]):
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
