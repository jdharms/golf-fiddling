"""
NES Open Tournament Golf - Editor State

Manages application state including editing mode, view settings, and canvas position.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from editor.data import ClipboardData

from .undo_manager import UndoManager


class EditorState:
    """Manages editor application state."""

    def __init__(self):
        # Editing mode
        self.mode: str = "terrain"  # "terrain" or "greens"

        # View settings
        self.show_grid: bool = True
        self.show_invalid_tiles: bool = False

        # Canvas position and zoom
        self.canvas_offset_x: int = 0
        self.canvas_offset_y: int = 0
        self.canvas_scale: int = 4

        # Tool settings
        self.selected_palette: int = 1  # For palette mode
        self.selected_flag_index: int = 0  # Which of 4 flag positions (0-3)
        self.tool_message: str | None = None  # Current tool status message

        # Clipboard and paste preview
        self.clipboard: ClipboardData | None = None
        self.paste_preview_active: bool = False

        # Undo/redo support
        self.undo_manager: UndoManager = UndoManager(max_undo_levels=50)

    def set_mode(self, mode: str):
        """Set the editing mode."""
        if mode in ("terrain", "greens"):
            self.mode = mode

    def toggle_grid(self):
        """Toggle grid visibility."""
        self.show_grid = not self.show_grid

    def toggle_invalid_tiles(self):
        """Toggle invalid tile highlighting."""
        self.show_invalid_tiles = not self.show_invalid_tiles

    def select_flag(self, index: int):
        """Select which flag position to display (0-3)."""
        if 0 <= index <= 3:
            self.selected_flag_index = index

    def reset_canvas_position(self):
        """Reset canvas to origin."""
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
