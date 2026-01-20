"""
NES Open Tournament Golf - Highlight Utilities

Shared utilities for drawing tile highlighting borders in terrain and greens renderers.
"""


import pygame

# Highlighting constants
HIGHLIGHT_COLOR = (255, 215, 0)  # Gold color
INVALID_NEIGHBOR_COLOR = (255, 0, 0)  # Red color
HIGHLIGHT_BORDER_WIDTH = 2


def draw_tile_border(
    screen,
    x: int,
    y: int,
    tile_size: int,
    color: tuple[int, int, int] = HIGHLIGHT_COLOR,
    border_width: int = HIGHLIGHT_BORDER_WIDTH,
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
        tile_size + border_width * 2,
    )
    pygame.draw.rect(screen, color, border_rect, border_width)


def draw_dashed_line(
    surface,
    color: tuple[int, int, int],
    start_pos: tuple[int, int],
    end_pos: tuple[int, int],
    width: int = 1,
    dash_length: int = 5,
):
    """
    Draw a dashed line between two points.

    Args:
        surface: Pygame surface to draw on
        color: Line color (RGB tuple)
        start_pos: Starting position (x, y)
        end_pos: Ending position (x, y)
        width: Line width in pixels (default: 1)
        dash_length: Length of each dash in pixels (default: 5)
    """
    import math

    x1, y1 = start_pos
    x2, y2 = end_pos
    dx = x2 - x1
    dy = y2 - y1
    distance = math.sqrt(dx * dx + dy * dy)

    if distance == 0:
        return

    # Normalize direction
    dx /= distance
    dy /= distance

    # Draw dashes
    pos = 0
    drawing = True
    while pos < distance:
        next_pos = min(pos + dash_length, distance)
        if drawing:
            start = (int(x1 + dx * pos), int(y1 + dy * pos))
            end = (int(x1 + dx * next_pos), int(y1 + dy * next_pos))
            pygame.draw.line(surface, color, start, end, width)
        drawing = not drawing
        pos = next_pos
