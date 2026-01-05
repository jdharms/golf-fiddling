"""
Stamp renderer - renders stamp previews with transparency indication.
"""

import pygame

from editor.controllers.highlight_state import HighlightState
from editor.core.constants import CANVAS_OFFSET_X, CANVAS_OFFSET_Y, TILE_SIZE


class StampRenderer:
    """Renders stamp previews."""

    # Gold color for stamp border
    STAMP_COLOR = (255, 215, 0)  # Gold
    STAMP_PREVIEW_ALPHA = 128  # Semi-transparent
    TRANSPARENT_COLOR1 = (100, 100, 100)  # Checkered pattern colors
    TRANSPARENT_COLOR2 = (140, 140, 140)

    @staticmethod
    def render_stamp_preview(
        screen: pygame.Surface,
        highlight_state: HighlightState,
        hole_data,
        tileset,
        canvas_offset_x: int,
        canvas_offset_y: int,
        scale: int,
        mode: str,
    ):
        """
        Render stamp preview with semi-transparent tiles and checkered pattern for transparent tiles.

        Args:
            screen: Pygame surface to draw on
            highlight_state: Highlight state containing stamp preview position and stamp
            hole_data: HoleData for getting palette indices
            tileset: Tileset for rendering tiles
            canvas_offset_x: Canvas viewport X offset
            canvas_offset_y: Canvas viewport Y offset
            scale: Zoom scale (1-8)
            mode: "terrain" or "greens"
        """
        if highlight_state.stamp_preview_pos is None or highlight_state.current_stamp is None:
            return

        stamp = highlight_state.current_stamp
        preview_row, preview_col = highlight_state.stamp_preview_pos
        tile_size = TILE_SIZE * scale

        # Render each tile in stamp
        for row_offset in range(stamp.height):
            for col_offset in range(stamp.width):
                tile_value = stamp.get_tile(row_offset, col_offset)
                target_row = preview_row + row_offset
                target_col = preview_col + col_offset

                # Calculate screen position (add canvas rect offset)
                x = CANVAS_OFFSET_X + target_col * tile_size - canvas_offset_x
                y = CANVAS_OFFSET_Y + target_row * tile_size - canvas_offset_y

                if tile_value is None:
                    # Transparent tile - show underlying tile (no overlay)
                    # The underlying tile is already rendered in the base layer
                    pass
                else:
                    # Regular tile - render with transparency
                    # Get palette index for this tile
                    if mode == "terrain":
                        palette_idx = hole_data.get_attribute(target_row, target_col)
                    else:  # greens
                        palette_idx = 0  # Greens always use palette 0

                    # Render tile and make a copy to avoid modifying cached surface
                    tile_surf = tileset.render_tile(tile_value, palette_idx, scale).copy()

                    # Apply semi-transparency
                    tile_surf.set_alpha(StampRenderer.STAMP_PREVIEW_ALPHA)

                    # Blit tile
                    screen.blit(tile_surf, (x, y))

        # Draw border around entire stamp
        stamp_width = stamp.width * tile_size
        stamp_height = stamp.height * tile_size
        stamp_x = CANVAS_OFFSET_X + preview_col * tile_size - canvas_offset_x
        stamp_y = CANVAS_OFFSET_Y + preview_row * tile_size - canvas_offset_y

        StampRenderer._draw_dashed_rect(
            screen,
            StampRenderer.STAMP_COLOR,
            pygame.Rect(stamp_x, stamp_y, stamp_width, stamp_height),
            width=2,
            dash_length=8,
        )

    @staticmethod
    def _draw_checkered_tile(surface: pygame.Surface, x: int, y: int, size: int):
        """
        Draw a checkered pattern to indicate transparent tile.

        Args:
            surface: Pygame surface to draw on
            x: X position
            y: Y position
            size: Tile size
        """
        checker_size = max(size // 4, 2)

        for row in range(0, size, checker_size):
            for col in range(0, size, checker_size):
                # Alternate colors in checkerboard pattern
                if (row // checker_size + col // checker_size) % 2 == 0:
                    color = StampRenderer.TRANSPARENT_COLOR1
                else:
                    color = StampRenderer.TRANSPARENT_COLOR2

                rect = pygame.Rect(x + col, y + row, checker_size, checker_size)
                pygame.draw.rect(surface, color, rect)

    @staticmethod
    def _draw_dashed_rect(
        surface: pygame.Surface,
        color: tuple[int, int, int],
        rect: pygame.Rect,
        width: int = 1,
        dash_length: int = 5,
    ):
        """
        Draw a dashed rectangle border.

        Args:
            surface: Pygame surface to draw on
            color: RGB color tuple
            rect: Rectangle to draw
            width: Line width
            dash_length: Length of dashes
        """
        x, y, w, h = rect.x, rect.y, rect.width, rect.height

        # Draw dashed lines for each side
        # Top
        for i in range(0, w, dash_length * 2):
            end_x = min(x + i + dash_length, x + w)
            pygame.draw.line(surface, color, (x + i, y), (end_x, y), width)

        # Bottom
        for i in range(0, w, dash_length * 2):
            end_x = min(x + i + dash_length, x + w)
            pygame.draw.line(surface, color, (x + i, y + h), (end_x, y + h), width)

        # Left
        for i in range(0, h, dash_length * 2):
            end_y = min(y + i + dash_length, y + h)
            pygame.draw.line(surface, color, (x, y + i), (x, end_y), width)

        # Right
        for i in range(0, h, dash_length * 2):
            end_y = min(y + i + dash_length, y + h)
            pygame.draw.line(surface, color, (x + w, y + i), (x + w, end_y), width)
