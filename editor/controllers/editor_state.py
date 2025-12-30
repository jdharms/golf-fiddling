"""
NES Open Tournament Golf - Editor State

Manages application state including editing mode, view settings, and canvas position.
"""

from typing import Optional, Tuple

from .transform_drag_state import TransformDragState


class EditorState:
    """Manages editor application state."""

    def __init__(self):
        # Editing mode
        self.mode: str = "terrain"  # "terrain", "palette", or "greens"

        # View settings
        self.show_grid: bool = True
        self.show_sprites: bool = True

        # Canvas position and zoom
        self.canvas_offset_x: int = 0
        self.canvas_offset_y: int = 0
        self.canvas_scale: int = 4

        # Tool settings
        self.selected_palette: int = 1  # For palette mode
        self.selected_flag_index: int = 0  # Which of 4 flag positions (0-3)

        # Mouse state
        self.mouse_down: bool = False
        self.last_paint_pos: Optional[Tuple[int, int]] = None

        # Transform drag state
        self.transform_state: TransformDragState = TransformDragState()

    def set_mode(self, mode: str):
        """Set the editing mode."""
        if mode in ("terrain", "palette", "greens"):
            self.mode = mode

    def toggle_grid(self):
        """Toggle grid visibility."""
        self.show_grid = not self.show_grid

    def toggle_sprites(self):
        """Toggle sprite visibility."""
        self.show_sprites = not self.show_sprites

    def select_flag(self, index: int):
        """Select which flag position to display (0-3)."""
        if 0 <= index <= 3:
            self.selected_flag_index = index

    def reset_canvas_position(self):
        """Reset canvas to origin."""
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
