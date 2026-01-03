"""
NES Open Tournament Golf - PIL Sprite Rendering

PIL-based sprite loading and rendering for generating static images.
Mirrors the pygame sprite system but uses PIL for rendering.
"""

import json
from typing import List, Dict, Tuple

try:
    from PIL import Image
except ImportError:
    raise ImportError("Pillow library required. Install with: pip install Pillow")

from ..core.chr_tile import decode_tile, TILE_SIZE
from ..core.palettes import SPRITE_OFFSET_Y


class PILSprite:
    """Loads and renders a sprite from JSON file with embedded CHR data."""

    def __init__(self, json_path: str):
        with open(json_path, "r") as f:
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
        # IMPORTANT: These offsets are from the original NES ROM and must be preserved exactly
        self.sprites = data.get("sprites", [{"tile": 0, "x": 0, "y": 0}])

        self._cache: Dict[Tuple[int, int], Image.Image] = {}

    def decode_tile(self, tile_idx: int) -> List[List[int]]:
        """
        Decode a single 8x8 tile into 2-bit pixel values.

        Uses shared decode_tile function from golf.core.chr_tile.
        """
        if tile_idx >= len(self.tiles):
            return [[0] * 8 for _ in range(8)]

        return decode_tile(self.tiles[tile_idx], 0)

    def render_tile(self, tile_idx: int, scale: int = 1) -> Image.Image:
        """Render a sprite tile to a PIL RGBA image with transparency."""
        cache_key = (tile_idx, scale)
        if cache_key in self._cache:
            return self._cache[cache_key]

        pixels = self.decode_tile(tile_idx)

        # Create RGBA image (with alpha channel for transparency)
        img = Image.new("RGBA", (TILE_SIZE * scale, TILE_SIZE * scale), (0, 0, 0, 0))
        img_pixels = img.load()
        assert img_pixels is not None

        for y in range(8):
            for x in range(8):
                color_idx = pixels[y][x]
                if color_idx == 0:
                    # Color index 0 is transparent
                    color = (0, 0, 0, 0)
                else:
                    # Non-transparent pixels get full alpha
                    r, g, b = self.palette[color_idx]
                    color = (r, g, b, 255)

                # Apply scaling by filling scale x scale region
                if scale == 1:
                    img_pixels[x, y] = color
                else:
                    for sy in range(scale):
                        for sx in range(scale):
                            img_pixels[x * scale + sx, y * scale + sy] = color

        self._cache[cache_key] = img
        return img

    def render_to_image(self, base_image: Image.Image, x: int, y: int, scale: int = 1):
        """
        Render all sprite entries onto the base image.

        This method applies the sprite offsets from the JSON file (which were extracted
        from the original NES ROM) to position each tile relative to the anchor point (x, y).

        Args:
            base_image: PIL Image to render onto (modified in-place)
            x: Anchor X position in pixels
            y: Anchor Y position in pixels
            scale: Scaling factor (default: 1)
        """
        for sprite_entry in self.sprites:
            tile_idx = sprite_entry.get("tile", 0)
            offset_x = sprite_entry.get("x", 0)
            offset_y = sprite_entry.get("y", 0)

            # Apply NES scanline delay offset
            offset_y += SPRITE_OFFSET_Y

            # Calculate final position
            final_x = x + offset_x * scale
            final_y = y + offset_y * scale

            # Render tile
            tile_img = self.render_tile(tile_idx, scale)

            # Paste with alpha compositing (third argument is the alpha mask)
            base_image.paste(tile_img, (final_x, final_y), tile_img)
