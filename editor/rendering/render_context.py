"""
NES Open Tournament Golf - Render Context

Bundles rendering resources and settings for canvas rendering.
"""

from typing import Dict, Optional
from editor.core.pygame_rendering import Tileset, Sprite


class RenderContext:
    """Bundles rendering resources and settings."""

    def __init__(
        self,
        tileset: Tileset,
        sprites: Dict[str, Optional[Sprite]],
        mode: str,
        show_grid: bool = True,
        show_sprites: bool = True,
        selected_flag_index: int = 0,
    ):
        """
        Initialize render context.

        Args:
            tileset: Tileset to use (terrain or greens)
            sprites: Dictionary of sprite objects
            mode: Current editing mode ("terrain", "palette", "greens")
            show_grid: Whether to show grid overlay
            show_sprites: Whether to show sprite overlays
            selected_flag_index: Which flag position to render (0-3)
        """
        self.tileset = tileset
        self.sprites = sprites
        self.mode = mode
        self.show_grid = show_grid
        self.show_sprites = show_sprites
        self.selected_flag_index = selected_flag_index
