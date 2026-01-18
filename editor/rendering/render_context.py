"""
NES Open Tournament Golf - Render Context

Bundles rendering resources and settings for canvas rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from editor.controllers.editor_state import EditorState

from editor.controllers.editor_state import GridMode
from editor.core.pygame_rendering import Sprite, Tileset


class RenderContext:
    """Bundles rendering resources and settings."""

    def __init__(
        self,
        tileset: Tileset,
        sprites: dict[str, Sprite | None],
        mode: str,
        grid_mode: GridMode = GridMode.TILE,
        selected_flag_index: int = 0,
        state: EditorState | None = None,
    ):
        """
        Initialize render context.

        Args:
            tileset: Tileset to use (terrain or greens)
            sprites: Dictionary of sprite objects
            mode: Current editing mode ("terrain", "palette", "greens")
            grid_mode: Grid display mode (OFF, TILE, or SUPERTILE)
            selected_flag_index: Which flag position to render (0-3)
            state: EditorState for clipboard/paste preview access
        """
        self.tileset = tileset
        self.sprites = sprites
        self.mode = mode
        self.grid_mode = grid_mode
        self.selected_flag_index = selected_flag_index
        self.state = state
