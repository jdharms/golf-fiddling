"""
NES Open Tournament Golf - Transform Drag State

Manages the state of an in-progress transform drag operation, including preview changes.
"""

from typing import Optional, Tuple, Dict


class TransformDragState:
    """Manages transform drag preview state."""

    def __init__(self):
        """Initialize with empty transform state."""
        self.is_active: bool = False
        self.drag_start_pos: Optional[Tuple[int, int]] = None
        self.origin_tile: Optional[Tuple[int, int]] = None
        self.preview_changes: Dict[Tuple[int, int], int] = {}
        self.direction: Optional[str] = None  # "horizontal" or "vertical"
        self.blocked: bool = False

    def start(self, mouse_pos: Tuple[int, int], tile_pos: Tuple[int, int]):
        """Begin transform drag.

        Args:
            mouse_pos: Mouse position in screen coordinates (pixels)
            tile_pos: Starting tile coordinates (row, col)
        """
        self.is_active = True
        self.drag_start_pos = mouse_pos
        self.origin_tile = tile_pos
        self.preview_changes = {}
        self.direction = None
        self.blocked = False

    def reset(self):
        """Clear all transform state."""
        self.__init__()
