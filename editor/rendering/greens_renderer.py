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
        transform_state,
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
            transform_state: Transform drag state for preview rendering
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

        # Render transform preview with gold borders (ON TOP of tiles)
        if transform_state.is_active:
            GreensRenderer._render_transform_preview(
                screen, canvas_rect, hole_data, tileset,
                transform_state.preview_changes,
                transform_state.origin_tile,
                canvas_scale, canvas_offset_x, canvas_offset_y
            )

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

    @staticmethod
    def _render_transform_preview(
        screen, canvas_rect, hole_data, tileset,
        preview_changes, origin_tile, canvas_scale, canvas_offset_x, canvas_offset_y
    ):
        """Render preview tiles with their transformed values and gold borders."""
        import pygame
        tile_size = TILE_SIZE * canvas_scale
        gold_color = (255, 215, 0)  # Gold color
        border_width = 2

        # Render preview tiles with their transformed values
        for (row, col), transformed_tile_idx in preview_changes.items():
            x = canvas_rect.x + col * tile_size - canvas_offset_x
            y = canvas_rect.y + row * tile_size - canvas_offset_y

            # Cull off-screen tiles
            if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                continue
            if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                continue

            # Render the transformed tile
            tile_surf = tileset.render_tile_greens(transformed_tile_idx, canvas_scale)
            screen.blit(tile_surf, (x, y))

            # Draw gold border around tile
            border_rect = pygame.Rect(
                x - border_width,
                y - border_width,
                tile_size + border_width * 2,
                tile_size + border_width * 2
            )
            pygame.draw.rect(screen, gold_color, border_rect, border_width)

        # Render border around origin tile
        if origin_tile:
            row, col = origin_tile
            x = canvas_rect.x + col * tile_size - canvas_offset_x
            y = canvas_rect.y + row * tile_size - canvas_offset_y

            # Only render if on-screen
            if not (x + tile_size < canvas_rect.x or x > canvas_rect.right or
                    y + tile_size < canvas_rect.y or y > canvas_rect.bottom):
                border_rect = pygame.Rect(
                    x - border_width,
                    y - border_width,
                    tile_size + border_width * 2,
                    tile_size + border_width * 2
                )
                pygame.draw.rect(screen, gold_color, border_rect, border_width)
