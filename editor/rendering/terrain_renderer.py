"""
NES Open Tournament Golf - Terrain Renderer

Renders terrain canvas view with tiles, sprites, and overlays.
"""

from typing import Dict

from pygame import Surface, Rect

from editor.core.pygame_rendering import Tileset, Sprite
from golf.formats.hole_data import HoleData
from editor.core.constants import TILE_SIZE, TERRAIN_WIDTH
from .sprite_renderer import SpriteRenderer
from .grid_renderer import GridRenderer


class TerrainRenderer:
    """Renders terrain canvas view."""

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
        Render terrain canvas view.

        Args:
            screen: Pygame surface to draw on
            canvas_rect: Canvas area rectangle
            hole_data: Hole data to render
            tileset: Terrain tileset
            sprites: Dictionary of loaded sprites
            canvas_offset_x: Horizontal scroll offset
            canvas_offset_y: Vertical scroll offset
            canvas_scale: Current zoom scale
            show_grid: Whether to show grid overlay
            show_sprites: Whether to show sprite overlays
            selected_flag_index: Which flag position to render (0-3)
        """
        tile_size = TILE_SIZE * canvas_scale

        # Render terrain tiles
        for row_idx, row in enumerate(hole_data.terrain):
            for col_idx, tile_idx in enumerate(row):
                x = canvas_rect.x + col_idx * tile_size - canvas_offset_x
                y = canvas_rect.y + row_idx * tile_size - canvas_offset_y

                if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                    continue
                if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                    continue

                palette_idx = hole_data.get_attribute(row_idx, col_idx)
                tile_surf = tileset.render_tile(tile_idx, palette_idx, canvas_scale)
                screen.blit(tile_surf, (x, y))

        # Render green overlay
        SpriteRenderer.render_green_overlay(
            screen, canvas_rect, hole_data, canvas_scale, canvas_offset_x, canvas_offset_y
        )

        # Render sprites
        if show_sprites:
            SpriteRenderer.render_terrain_sprites(
                screen, canvas_rect, sprites, hole_data, selected_flag_index,
                canvas_scale, canvas_offset_x, canvas_offset_y
            )

        # Render grid
        if show_grid:
            GridRenderer.render(
                screen, canvas_rect, TERRAIN_WIDTH, hole_data.get_terrain_height(),
                tile_size, canvas_offset_x, canvas_offset_y
            )
