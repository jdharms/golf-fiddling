"""
NES Open Tournament Golf - Highlight Utilities

Shared utilities for drawing tile highlighting borders in terrain and greens renderers.
"""

from typing import Tuple

import pygame


# Gold highlighting constants
HIGHLIGHT_COLOR = (255, 215, 0)  # Gold color
HIGHLIGHT_BORDER_WIDTH = 2


def draw_tile_border(
    screen,
    x: int,
    y: int,
    tile_size: int,
    color: Tuple[int, int, int] = HIGHLIGHT_COLOR,
    border_width: int = HIGHLIGHT_BORDER_WIDTH
):
    """
    Draw a colored border around a tile at the specified screen position.

    Args:
        screen: Pygame surface to draw on
        x: Screen x coordinate of tile
        y: Screen y coordinate of tile
        tile_size: Rendered size of tile in pixels
        color: Border color (default: gold)
        border_width: Border width in pixels (default: 2)
    """
    border_rect = pygame.Rect(
        x - border_width,
        y - border_width,
        tile_size + border_width * 2,
        tile_size + border_width * 2
    )
    pygame.draw.rect(screen, color, border_rect, border_width)
