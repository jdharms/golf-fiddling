"""
Selection renderer - renders selection rectangles and paste previews.
"""

import pygame

from editor.controllers.highlight_state import HighlightState
from editor.core.constants import CANVAS_OFFSET_X, CANVAS_OFFSET_Y, TILE_SIZE


class SelectionRenderer:
    """Renders selection rectangles and paste previews."""

    # Gold color for selection border
    SELECTION_COLOR = (255, 215, 0)  # Gold
    PASTE_PREVIEW_ALPHA = 128  # Semi-transparent

    @staticmethod
    def render_selection_rect(
        screen: pygame.Surface,
        highlight_state: HighlightState,
        canvas_offset_x: int,
        canvas_offset_y: int,
        scale: int,
    ):
        """
        Render selection rectangle with dashed gold border.

        Args:
            screen: Pygame surface to draw on
            highlight_state: Highlight state containing selection rectangle
            canvas_offset_x: Canvas viewport X offset
            canvas_offset_y: Canvas viewport Y offset
            scale: Zoom scale (1-8)
        """
        if highlight_state.selection_rect is None:
            return

        row, col, width, height = highlight_state.selection_rect
        tile_size = TILE_SIZE * scale

        # Calculate screen position (add canvas rect offset)
        x = CANVAS_OFFSET_X + col * tile_size - canvas_offset_x
        y = CANVAS_OFFSET_Y + row * tile_size - canvas_offset_y
        rect_width = width * tile_size
        rect_height = height * tile_size

        # Draw dashed rectangle border (2px thick)
        SelectionRenderer._draw_dashed_rect(
            screen,
            SelectionRenderer.SELECTION_COLOR,
            pygame.Rect(x, y, rect_width, rect_height),
            width=2,
            dash_length=8,
        )

    @staticmethod
    def render_paste_preview(
        screen: pygame.Surface,
        highlight_state: HighlightState,
        clipboard_data,
        hole_data,
        tileset,
        canvas_offset_x: int,
        canvas_offset_y: int,
        scale: int,
        mode: str,
    ):
        """
        Render paste preview with semi-transparent tiles.

        Args:
            screen: Pygame surface to draw on
            highlight_state: Highlight state containing paste preview position
            clipboard_data: ClipboardData with tiles to preview
            hole_data: HoleData for getting palette indices
            tileset: Tileset for rendering tiles
            canvas_offset_x: Canvas viewport X offset
            canvas_offset_y: Canvas viewport Y offset
            scale: Zoom scale (1-8)
            mode: "terrain" or "greens"
        """
        if highlight_state.paste_preview_pos is None or clipboard_data is None:
            return

        if clipboard_data.is_empty():
            return

        paste_row, paste_col = highlight_state.paste_preview_pos
        tile_size = TILE_SIZE * scale

        # Render each tile in clipboard with semi-transparency
        for row_offset in range(clipboard_data.height):
            for col_offset in range(clipboard_data.width):
                tile_value = clipboard_data.get_tile(row_offset, col_offset)

                # Skip transparent tiles
                if tile_value is None:
                    continue

                target_row = paste_row + row_offset
                target_col = paste_col + col_offset

                # Calculate screen position (add canvas rect offset)
                x = CANVAS_OFFSET_X + target_col * tile_size - canvas_offset_x
                y = CANVAS_OFFSET_Y + target_row * tile_size - canvas_offset_y

                # Get palette index for this tile
                if mode == "terrain":
                    palette_idx = hole_data.get_attribute(target_row, target_col)
                else:  # greens
                    palette_idx = 0  # Greens always use palette 0

                # Render tile and make a copy to avoid modifying cached surface
                tile_surf = tileset.render_tile(tile_value, palette_idx, scale).copy()

                # Apply semi-transparency (safe because we're working on a copy)
                tile_surf.set_alpha(SelectionRenderer.PASTE_PREVIEW_ALPHA)

                # Blit tile
                screen.blit(tile_surf, (x, y))

        # Draw border around entire paste region
        paste_width = clipboard_data.width * tile_size
        paste_height = clipboard_data.height * tile_size
        paste_x = CANVAS_OFFSET_X + paste_col * tile_size - canvas_offset_x
        paste_y = CANVAS_OFFSET_Y + paste_row * tile_size - canvas_offset_y

        SelectionRenderer._draw_dashed_rect(
            screen,
            SelectionRenderer.SELECTION_COLOR,
            pygame.Rect(paste_x, paste_y, paste_width, paste_height),
            width=2,
            dash_length=8,
        )

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
