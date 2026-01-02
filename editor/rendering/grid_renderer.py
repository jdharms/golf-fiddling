"""
NES Open Tournament Golf - Grid Renderer

Renders grid overlay on the canvas for tile alignment.
"""

import pygame
from pygame import Surface, Rect

from editor.core.constants import COLOR_GRID, COLOR_GRID_SUPER
from editor.controllers.view_state import ViewState


class GridRenderer:
    """Renders grid overlay on canvas."""

    @staticmethod
    def render(
        screen: Surface,
        view_state: ViewState,
        width: int,
        height: int,
    ):
        """
        Render grid overlay.

        Args:
            screen: Pygame surface to draw on
            view_state: Viewport camera and coordinate transformations
            width: Grid width in tiles
            height: Grid height in tiles
        """
        canvas_rect = view_state.canvas_rect
        tile_size = view_state.tile_size
        offset_x = view_state.offset_x
        offset_y = view_state.offset_y

        # Vertical lines
        for col in range(width + 1):
            x = canvas_rect.x + col * tile_size - offset_x
            if canvas_rect.x <= x <= canvas_rect.right:
                color = COLOR_GRID_SUPER if col % 2 == 0 else COLOR_GRID
                pygame.draw.line(screen, color, (x, canvas_rect.y), (x, canvas_rect.bottom))

        # Horizontal lines
        for row in range(height + 1):
            y = canvas_rect.y + row * tile_size - offset_y
            if canvas_rect.y <= y <= canvas_rect.bottom:
                color = COLOR_GRID_SUPER if row % 2 == 0 else COLOR_GRID
                pygame.draw.line(screen, color, (canvas_rect.x, y), (canvas_rect.right, y))
