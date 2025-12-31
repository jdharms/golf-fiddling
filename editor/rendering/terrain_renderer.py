"""
NES Open Tournament Golf - Terrain Renderer

Renders terrain canvas view with tiles, sprites, and overlays.
"""

from typing import Dict, Optional

import pygame
from pygame import Surface, Rect

from editor.core.pygame_rendering import Tileset, Sprite
from golf.formats.hole_data import HoleData
from editor.core.constants import TILE_SIZE, TERRAIN_WIDTH
from .sprite_renderer import SpriteRenderer
from .grid_renderer import GridRenderer
from .highlight_utils import draw_tile_border, INVALID_NEIGHBOR_COLOR


def _render_placeholder_tile(size: int) -> Surface:
    """Render the placeholder tile (0x100) with a distinctive pattern."""
    surf = Surface((size, size))
    # Gray checkerboard pattern to indicate meta/placeholder tile
    gray1 = (100, 100, 100)
    gray2 = (140, 140, 140)
    checker_size = size // 4

    for row in range(4):
        for col in range(4):
            color = gray1 if (row + col) % 2 == 0 else gray2
            rect = (col * checker_size, row * checker_size, checker_size, checker_size)
            pygame.draw.rect(surf, color, rect)

    return surf


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
        transform_state,
        shift_hover_tile: Optional[int],
        show_invalid_tiles: bool,
        invalid_terrain_tiles: Optional[set] = None,
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
            transform_state: Transform drag state for preview rendering
            shift_hover_tile: Tile value to highlight (None if not highlighting)
            show_invalid_tiles: Whether to show invalid tile highlighting
            invalid_terrain_tiles: Set of (row, col) tuples with invalid neighbors (None if none)
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

                # Render tile - use special rendering for placeholder (0x100)
                if tile_idx == 0x100:
                    tile_surf = _render_placeholder_tile(tile_size)
                else:
                    palette_idx = hole_data.get_attribute(row_idx, col_idx)
                    tile_surf = tileset.render_tile(tile_idx, palette_idx, canvas_scale)
                screen.blit(tile_surf, (x, y))

        # Render shift-hover highlights (AFTER base tiles, BEFORE transform preview)
        if shift_hover_tile is not None:
            TerrainRenderer._render_shift_hover_highlights(
                screen, canvas_rect, hole_data,
                shift_hover_tile, canvas_scale, canvas_offset_x, canvas_offset_y
            )

        # Render invalid neighbor highlights (red borders)
        if show_invalid_tiles and invalid_terrain_tiles:
            TerrainRenderer._render_invalid_neighbor_highlights(
                screen, canvas_rect, hole_data, invalid_terrain_tiles,
                canvas_scale, canvas_offset_x, canvas_offset_y
            )

        # Render transform preview with gold borders (ON TOP of tiles)
        if transform_state.is_active:
            TerrainRenderer._render_transform_preview(
                screen, canvas_rect, hole_data, tileset,
                transform_state.preview_changes,
                transform_state.origin_tile,
                canvas_scale, canvas_offset_x, canvas_offset_y
            )

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

    @staticmethod
    def _render_transform_preview(
        screen, canvas_rect, hole_data, tileset,
        preview_changes, origin_tile, canvas_scale, canvas_offset_x, canvas_offset_y
    ):
        """Render preview tiles with their transformed values and gold borders."""
        tile_size = TILE_SIZE * canvas_scale

        # Render preview tiles with their transformed values
        for (row, col), transformed_tile_idx in preview_changes.items():
            x = canvas_rect.x + col * tile_size - canvas_offset_x
            y = canvas_rect.y + row * tile_size - canvas_offset_y

            # Cull off-screen tiles
            if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                continue
            if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                continue

            # Render the transformed tile - use special rendering for placeholder (0x100)
            if transformed_tile_idx == 0x100:
                tile_surf = _render_placeholder_tile(tile_size)
            else:
                palette_idx = hole_data.get_attribute(row, col)
                tile_surf = tileset.render_tile(transformed_tile_idx, palette_idx, canvas_scale)
            screen.blit(tile_surf, (x, y))

            # Draw gold border around tile
            draw_tile_border(screen, x, y, tile_size)

        # Render border around origin tile
        if origin_tile:
            row, col = origin_tile
            x = canvas_rect.x + col * tile_size - canvas_offset_x
            y = canvas_rect.y + row * tile_size - canvas_offset_y

            # Only render if on-screen
            if not (x + tile_size < canvas_rect.x or x > canvas_rect.right or
                    y + tile_size < canvas_rect.y or y > canvas_rect.bottom):
                draw_tile_border(screen, x, y, tile_size)

    @staticmethod
    def _render_shift_hover_highlights(
        screen, canvas_rect, hole_data, highlight_tile_value,
        canvas_scale, canvas_offset_x, canvas_offset_y
    ):
        """Render gold borders around all tiles matching the shift-hovered tile value."""
        tile_size = TILE_SIZE * canvas_scale

        for row_idx, row in enumerate(hole_data.terrain):
            for col_idx, tile_idx in enumerate(row):
                # Only highlight if tile matches the hovered value
                if tile_idx != highlight_tile_value:
                    continue

                x = canvas_rect.x + col_idx * tile_size - canvas_offset_x
                y = canvas_rect.y + row_idx * tile_size - canvas_offset_y

                # Cull off-screen tiles
                if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                    continue
                if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                    continue

                # Draw gold border
                draw_tile_border(screen, x, y, tile_size)

    @staticmethod
    def _render_invalid_neighbor_highlights(
        screen, canvas_rect, hole_data, invalid_tiles,
        canvas_scale, canvas_offset_x, canvas_offset_y
    ):
        """Render red borders around tiles with invalid neighbor relationships."""
        tile_size = TILE_SIZE * canvas_scale

        for row_idx, col_idx in invalid_tiles:
            x = canvas_rect.x + col_idx * tile_size - canvas_offset_x
            y = canvas_rect.y + row_idx * tile_size - canvas_offset_y

            # Cull off-screen tiles
            if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                continue
            if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                continue

            # Draw red border
            draw_tile_border(screen, x, y, tile_size, color=INVALID_NEIGHBOR_COLOR)
