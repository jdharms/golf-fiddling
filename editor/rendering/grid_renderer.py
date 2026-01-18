"""
NES Open Tournament Golf - Grid Renderer

Renders grid overlay on the canvas for tile alignment.
"""

import pygame
from pygame import Surface

from editor.controllers.editor_state import GridMode
from editor.controllers.view_state import ViewState
from editor.core.constants import COLOR_GRID, COLOR_GRID_SUPER


class GridRenderer:
    """Renders grid overlay on canvas."""

    @staticmethod
    def render(
        screen: Surface,
        view_state: ViewState,
        width: int,
        height: int,
        grid_mode: GridMode = GridMode.TILE,
    ):
        """
        Render grid overlay.

        Args:
            screen: Pygame surface to draw on
            view_state: Viewport camera and coordinate transformations
            width: Grid width in tiles
            height: Grid height in tiles
            grid_mode: Grid display mode (OFF, TILE, or SUPERTILE)
        """
        # Early return if grid is off
        if grid_mode == GridMode.OFF:
            return
        canvas_rect = view_state.canvas_rect
        tile_size = view_state.tile_size
        offset_x = view_state.offset_x
        offset_y = view_state.offset_y

        if grid_mode == GridMode.SUPERTILE:
            # Render 2x2 supertile grid
            supertile_size = tile_size * 2
            super_width = (width + 1) // 2
            super_height = (height + 1) // 2

            # Vertical lines
            for col in range(super_width + 1):
                x = canvas_rect.x + col * supertile_size - offset_x
                if canvas_rect.x <= x <= canvas_rect.right:
                    pygame.draw.line(
                        screen, COLOR_GRID_SUPER, (x, canvas_rect.y), (x, canvas_rect.bottom)
                    )

            # Horizontal lines
            for row in range(super_height + 1):
                y = canvas_rect.y + row * supertile_size - offset_y
                if canvas_rect.y <= y <= canvas_rect.bottom:
                    pygame.draw.line(
                        screen, COLOR_GRID_SUPER, (canvas_rect.x, y), (canvas_rect.right, y)
                    )
        else:
            # Render standard 1x1 tile grid
            # Vertical lines
            for col in range(width + 1):
                x = canvas_rect.x + col * tile_size - offset_x
                if canvas_rect.x <= x <= canvas_rect.right:
                    color = COLOR_GRID_SUPER if col % 2 == 0 else COLOR_GRID
                    pygame.draw.line(
                        screen, color, (x, canvas_rect.y), (x, canvas_rect.bottom)
                    )

            # Horizontal lines
            for row in range(height + 1):
                y = canvas_rect.y + row * tile_size - offset_y
                if canvas_rect.y <= y <= canvas_rect.bottom:
                    color = COLOR_GRID_SUPER if row % 2 == 0 else COLOR_GRID
                    pygame.draw.line(
                        screen, color, (canvas_rect.x, y), (canvas_rect.right, y)
                    )
