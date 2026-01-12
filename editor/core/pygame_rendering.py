"""
NES Open Tournament Golf - Pygame Rendering

Handles NES CHR format tile decoding and pygame-based rendering for both
tileset backgrounds and sprites. Uses shared tile decoding from golf.core.
"""

import json

import pygame
from pygame import Surface

from golf.core.chr_tile import BYTES_PER_TILE, TILE_SIZE, decode_tile
from golf.core.palettes import GREENS_PALETTE, PALETTES

from .constants import (
    GREENS_PALETTE_NUM,
    SPRITE_OFFSET_Y,
)


class Tileset:
    """Loads and renders NES CHR tile data using pygame."""

    def __init__(self, chr_path: str):
        with open(chr_path, "rb") as f:
            self.data = f.read()

        self.num_tiles = len(self.data) // BYTES_PER_TILE
        self._cache: dict[tuple[int, int, int], Surface] = {}

    def decode_tile(self, tile_idx: int) -> list[list[int]]:
        """
        Decode a single 8x8 tile into 2-bit pixel values.

        Uses shared decode_tile function from golf.core.chr_tile.
        """
        return decode_tile(self.data, tile_idx)

    def render_tile(self, tile_idx: int, palette_idx: int, scale: int = 1) -> Surface:
        """Render a tile to a Pygame surface with given palette."""
        cache_key = (tile_idx, palette_idx, scale)
        if cache_key in self._cache:
            return self._cache[cache_key]

        palette = PALETTES[palette_idx] if palette_idx < len(PALETTES) else PALETTES[1]
        pixels = self.decode_tile(tile_idx)

        surf = Surface((TILE_SIZE * scale, TILE_SIZE * scale))
        for y in range(8):
            for x in range(8):
                color = palette[pixels[y][x]]
                if scale == 1:
                    surf.set_at((x, y), color)
                else:
                    pygame.draw.rect(surf, color, (x * scale, y * scale, scale, scale))

        self._cache[cache_key] = surf
        return surf

    def render_tile_greens(self, tile_idx: int, scale: int = 1) -> Surface:
        """Render a tile using the greens palette."""
        cache_key = (tile_idx, GREENS_PALETTE_NUM, scale)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if tile_idx == 0x100:
            surf = _render_placeholder_tile(TILE_SIZE * scale)
        else:
            pixels = self.decode_tile(tile_idx)

            surf = Surface((TILE_SIZE * scale, TILE_SIZE * scale))
            for y in range(8):
                for x in range(8):
                    color = GREENS_PALETTE[pixels[y][x]]
                    if scale == 1:
                        surf.set_at((x, y), color)
                    else:
                        pygame.draw.rect(surf, color, (x * scale, y * scale, scale, scale))

        self._cache[cache_key] = surf
        return surf

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


class Sprite:
    """Loads and renders a sprite from JSON file with embedded CHR data."""

    def __init__(self, json_path: str):
        with open(json_path) as f:
            data = json.load(f)

        self.name = data.get("name", "unknown")

        # Parse hex tile data
        self.tiles = []
        for tile_str in data.get("tiles", []):
            tile_bytes = bytes.fromhex(tile_str.replace(" ", ""))
            self.tiles.append(tile_bytes)

        # Parse palette (convert hex colors to RGB tuples)
        palette_hex = data.get("palette", ["#000000"] * 4)
        self.palette = []
        for hex_color in palette_hex:
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            self.palette.append((r, g, b))

        # Parse sprite entries (OAM-style: tile index + offsets)
        self.sprites = data.get("sprites", [{"tile": 0, "x": 0, "y": 0}])

        self._cache: dict[tuple[int, int], Surface] = {}

    def decode_tile(self, tile_idx: int) -> list[list[int]]:
        """
        Decode a single 8x8 tile into 2-bit pixel values.

        Uses shared decode_tile function from golf.core.chr_tile.
        """
        if tile_idx >= len(self.tiles):
            return [[0] * 8 for _ in range(8)]

        return decode_tile(self.tiles[tile_idx], 0)

    def render_tile(self, tile_idx: int, scale: int = 1) -> Surface:
        """Render a sprite tile to a Pygame surface."""
        cache_key = (tile_idx, scale)
        if cache_key in self._cache:
            return self._cache[cache_key]

        pixels = self.decode_tile(tile_idx)

        surf = Surface((TILE_SIZE * scale, TILE_SIZE * scale))
        surf.set_colorkey((0, 0, 0))  # Make color 0 (black) transparent

        for y in range(8):
            for x in range(8):
                color_idx = pixels[y][x]
                if color_idx > 0:  # Skip transparent pixels
                    color = self.palette[color_idx]
                    if scale == 1:
                        surf.set_at((x, y), color)
                    else:
                        pygame.draw.rect(
                            surf, color, (x * scale, y * scale, scale, scale)
                        )

        self._cache[cache_key] = surf
        return surf

    def render(self, screen: Surface, x: int, y: int, scale: int = 1):
        """Render all sprite entries at given positions."""
        for sprite_entry in self.sprites:
            tile_idx = sprite_entry.get("tile", 0)
            offset_x = sprite_entry.get("x", 0)
            offset_y = sprite_entry.get("y", 0)

            offset_y += SPRITE_OFFSET_Y

            sx = x + offset_x * scale
            sy = y + offset_y * scale

            tile_surf = self.render_tile(tile_idx, scale)
            screen.blit(tile_surf, (sx, sy))

    def get_bounding_box(self, anchor_x: int, anchor_y: int) -> tuple[int, int, int, int]:
        """
        Calculate bounding box of all sprite tiles in game pixel space.

        Args:
            anchor_x: Anchor point X coordinate (game pixels)
            anchor_y: Anchor point Y coordinate (game pixels)

        Returns:
            Tuple of (min_x, min_y, max_x, max_y) in game pixels
        """
        if not self.sprites:
            return (anchor_x, anchor_y, anchor_x, anchor_y)

        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')

        for entry in self.sprites:
            offset_x = entry.get("x", 0)
            offset_y = entry.get("y", 0) + SPRITE_OFFSET_Y  # Apply NES scanline delay

            # Calculate tile position in game pixel space
            tile_x = anchor_x + offset_x
            tile_y = anchor_y + offset_y

            # Expand bounding box
            min_x = min(min_x, tile_x)
            min_y = min(min_y, tile_y)
            max_x = max(max_x, tile_x + TILE_SIZE)
            max_y = max(max_y, tile_y + TILE_SIZE)

        return (int(min_x), int(min_y), int(max_x), int(max_y))
