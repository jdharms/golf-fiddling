"""
NES Open Tournament Golf - View State

Manages viewport camera position, zoom, and coordinate transformations.
"""

from typing import Optional, Tuple
from pygame import Rect

from editor.core.constants import TILE_SIZE


class ViewState:
    """Manages viewport camera and coordinate transformations."""

    def __init__(self, canvas_rect: Rect, offset_x: int = 0, offset_y: int = 0, scale: int = 4):
        """
        Initialize view state.

        Args:
            canvas_rect: The canvas drawing area (screen coordinates)
            offset_x: Horizontal scroll offset in pixels
            offset_y: Vertical scroll offset in pixels
            scale: Zoom scale multiplier (1-8)
        """
        self.canvas_rect = canvas_rect
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.scale = scale

    @property
    def tile_size(self) -> int:
        """Get the current tile size in pixels (based on scale)."""
        return TILE_SIZE * self.scale

    def screen_to_tile(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """
        Convert screen position to tile coordinates.

        Args:
            screen_pos: Screen position (x, y) in pixels

        Returns:
            Tile coordinates (row, col), or None if outside canvas
        """
        if not self.canvas_rect.collidepoint(screen_pos):
            return None

        local_x = screen_pos[0] - self.canvas_rect.x + self.offset_x
        local_y = screen_pos[1] - self.canvas_rect.y + self.offset_y

        tile_col = local_x // self.tile_size
        tile_row = local_y // self.tile_size

        return (tile_row, tile_col)

    def screen_to_supertile(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """
        Convert screen position to supertile (2x2) coordinates.

        Args:
            screen_pos: Screen position (x, y) in pixels

        Returns:
            Supertile coordinates (row, col), or None if outside canvas
        """
        tile = self.screen_to_tile(screen_pos)
        if tile is None:
            return None
        return (tile[0] // 2, tile[1] // 2)

    def tile_to_screen(self, tile_pos: Tuple[int, int]) -> Tuple[int, int]:
        """
        Convert tile coordinates to screen position (top-left corner).

        Args:
            tile_pos: Tile coordinates (row, col)

        Returns:
            Screen position (x, y) in pixels
        """
        row, col = tile_pos
        x = self.canvas_rect.x + col * self.tile_size - self.offset_x
        y = self.canvas_rect.y + row * self.tile_size - self.offset_y
        return (x, y)

    def is_tile_visible(self, tile_pos: Tuple[int, int]) -> bool:
        """
        Check if a tile is visible in the current viewport.

        Args:
            tile_pos: Tile coordinates (row, col)

        Returns:
            True if tile is visible in viewport
        """
        x, y = self.tile_to_screen(tile_pos)
        tile_size = self.tile_size

        return not (
            x + tile_size < self.canvas_rect.x or x > self.canvas_rect.right or
            y + tile_size < self.canvas_rect.y or y > self.canvas_rect.bottom
        )
