"""
NES Open Tournament Golf - Tile Pickers

Tile selection panels for terrain and greens editing.
"""

from typing import Tuple, List

import pygame
from pygame import Surface, Rect

from editor.core.pygame_rendering import Tileset
from editor.core.constants import (
    TILE_SIZE,
    COLOR_PICKER_BG,
    COLOR_SELECTION,
)


def _range_to_list(min: int, max: int) -> List[int]:
    return list(range(min, max))


class TilePicker:
    """Tile selection panel."""

    def __init__(self, tileset: Tileset, rect: Rect):
        self.tileset = tileset
        self.rect = rect
        self.scroll_y = 0
        self.selected_tile = 0x25  # Default to rough
        self.tiles_per_row = (rect.width - 20) // (TILE_SIZE * 2 + 2)
        self.tile_scale = 2
        self.tile_spacing = 2

        # Build list of tile indices to show (skip empty tiles at start)
        # self.tile_indices = list(range(0x25, 0xE0))
        self.tile_indices = (
            [0x25, 0x27] + _range_to_list(0x35, 0x3D) + _range_to_list(0x3E, 0xC0) + [0xDF]
        )

        # Track tile currently under mouse
        self.hovered_tile = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if handled."""
        if event.type == pygame.MOUSEMOTION:
            # Update hovered tile (doesn't consume event)
            if self.rect.collidepoint(event.pos):
                self.hovered_tile = self._tile_at_position(event.pos)
            else:
                self.hovered_tile = None
            # Don't return True - let event propagate to buttons

        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if event.button == 1:  # Left click
                    self._select_at(event.pos)
                    return True
                elif event.button == 4:  # Scroll up
                    self.scroll_y = max(0, self.scroll_y - 20)
                    return True
                elif event.button == 5:  # Scroll down
                    self.scroll_y += 20
                    return True
        return False

    def _select_at(self, pos: Tuple[int, int]):
        """Select tile at screen position."""
        tile = self._tile_at_position(pos)
        if tile is not None:
            self.selected_tile = tile

    def _tile_at_position(self, pos: Tuple[int, int]) -> int | None:
        """Get tile index at screen position, or None if invalid."""
        local_x = pos[0] - self.rect.x - 10
        local_y = pos[1] - self.rect.y - 10 + self.scroll_y

        tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing
        col = local_x // tile_size
        row = local_y // tile_size

        idx = row * self.tiles_per_row + col
        if 0 <= idx < len(self.tile_indices):
            return self.tile_indices[idx]
        return None

    def get_hovered_tile(self) -> int | None:
        """Get the tile value currently under mouse, or None."""
        return self.hovered_tile

    def render(self, screen: Surface, palette_idx: int = 1):
        """Render the tile picker."""
        # Background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        # Create clipping rect
        clip_rect = self.rect.copy()
        clip_rect.y += 5
        clip_rect.height -= 10

        tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing

        for i, tile_idx in enumerate(self.tile_indices):
            col = i % self.tiles_per_row
            row = i // self.tiles_per_row

            x = self.rect.x + 10 + col * tile_size
            y = self.rect.y + 10 + row * tile_size - self.scroll_y

            # Skip if outside visible area
            if y + tile_size < clip_rect.y or y > clip_rect.bottom:
                continue

            # Render tile
            tile_surf = self.tileset.render_tile(tile_idx, palette_idx, self.tile_scale)
            screen.blit(tile_surf, (x, y))

            # Selection highlight
            if tile_idx == self.selected_tile:
                pygame.draw.rect(screen, COLOR_SELECTION,
                               (x - 1, y - 1, TILE_SIZE * self.tile_scale + 2, TILE_SIZE * self.tile_scale + 2), 2)


class GreensTilePicker(TilePicker):
    """Tile picker for greens editing."""

    def __init__(self, tileset: Tileset, rect: Rect):
        super().__init__(tileset, rect)
        # Greens use different tile range
        self.tile_indices = [0x29, 0x2C] + _range_to_list(0x30, 0xA0) + [0xB0]
        self.selected_tile = 0x30

    def render(self, screen: Surface, palette_idx: int = 1):
        """Render the tile picker with greens palette."""
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing

        for i, tile_idx in enumerate(self.tile_indices):
            col = i % self.tiles_per_row
            row = i // self.tiles_per_row

            x = self.rect.x + 10 + col * tile_size
            y = self.rect.y + 10 + row * tile_size - self.scroll_y

            if y + tile_size < self.rect.y or y > self.rect.bottom:
                continue

            tile_surf = self.tileset.render_tile_greens(tile_idx, self.tile_scale)
            screen.blit(tile_surf, (x, y))

            if tile_idx == self.selected_tile:
                pygame.draw.rect(screen, COLOR_SELECTION,
                               (x - 1, y - 1, TILE_SIZE * self.tile_scale + 2, TILE_SIZE * self.tile_scale + 2), 2)
