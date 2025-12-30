"""
NES Open Tournament Golf - Pygame Rendering

Handles NES CHR format tile decoding and pygame-based rendering for both
tileset backgrounds and sprites. Uses shared tile decoding from golf.core.
"""

import json
from typing import List, Dict, Tuple

import pygame
from pygame import Surface

from golf.core.chr_tile import decode_tile, TILE_SIZE, BYTES_PER_TILE
from golf.core.palettes import PALETTES, GREENS_PALETTE

from .constants import (
    GREENS_PALETTE_NUM,
    SPRITE_OFFSET_Y,
)


class Tileset:
    """Loads and renders NES CHR tile data using pygame."""

    def __init__(self, chr_path: str):
        with open(chr_path, 'rb') as f:
            self.data = f.read()

        self.num_tiles = len(self.data) // BYTES_PER_TILE
        self._cache: Dict[Tuple[int, int, int], Surface] = {}

    def decode_tile(self, tile_idx: int) -> List[List[int]]:
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


class Sprite:
    """Loads and renders a sprite from JSON file with embedded CHR data."""

    def __init__(self, json_path: str):
        with open(json_path, 'r') as f:
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

        self._cache: Dict[Tuple[int, int], Surface] = {}

    def decode_tile(self, tile_idx: int) -> List[List[int]]:
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
                        pygame.draw.rect(surf, color, (x * scale, y * scale, scale, scale))

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
