"""
NES Open Tournament Golf - Greens Renderer

Renders greens editing canvas view.
"""

from typing import Dict

from pygame import Surface, Rect

from editor.core.pygame_rendering import Tileset, Sprite
from golf.formats.hole_data import HoleData
from editor.core.constants import TILE_SIZE, GREENS_WIDTH, GREENS_HEIGHT
from .sprite_renderer import SpriteRenderer
from .grid_renderer import GridRenderer


class GreensRenderer:
    """Renders greens editing canvas view."""

    @staticmethod
    def render(
        screen: Surface,
        canvas_rect: Rect,
        hole_data: HoleData,
        tileset: Tileset,
        sprites: Dict[str, Sprite],
        canvas_offset_x: int,
        canvas_offset_y: int,
        canvas_scale: int,
        show_grid: bool,
        show_sprites: bool,
        selected_flag_index: int,
    ):
        """
        Render greens editing view.

        Args:
            screen: Pygame surface to draw on
            canvas_rect: Canvas area rectangle
            hole_data: Hole data to render
            tileset: Greens tileset
            sprites: Dictionary of loaded sprites
            canvas_offset_x: Horizontal scroll offset
            canvas_offset_y: Vertical scroll offset
            canvas_scale: Current zoom scale
            show_grid: Whether to show grid overlay
            show_sprites: Whether to show sprite overlays
            selected_flag_index: Which flag position to render (0-3)
        """
        if not hole_data.greens:
            return

        tile_size = TILE_SIZE * canvas_scale

        # Render greens tiles
        for row_idx, row in enumerate(hole_data.greens):
            for col_idx, tile_idx in enumerate(row):
                x = canvas_rect.x + col_idx * tile_size - canvas_offset_x
                y = canvas_rect.y + row_idx * tile_size - canvas_offset_y

                if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                    continue
                if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                    continue

                tile_surf = tileset.render_tile_greens(tile_idx, canvas_scale)
                screen.blit(tile_surf, (x, y))

        # Render flag-cup sprite
        if show_sprites:
            SpriteRenderer.render_greens_sprites(
                screen, canvas_rect, sprites, hole_data, selected_flag_index,
                canvas_scale, canvas_offset_x, canvas_offset_y
            )

        # Render grid
        if show_grid:
            GridRenderer.render(
                screen, canvas_rect, GREENS_WIDTH, GREENS_HEIGHT,
                tile_size, canvas_offset_x, canvas_offset_y
            )
