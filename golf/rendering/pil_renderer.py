"""
NES Open Tournament Golf - PIL Renderer

PIL-based rendering for generating PNG images of golf course holes.
Used by the visualize tool to create static images.
"""

from typing import Dict, Any

try:
    from PIL import Image
except ImportError:
    raise ImportError("Pillow library required. Install with: pip install Pillow")

from ..core.chr_tile import TilesetData, TILE_SIZE
from ..core.palettes import PALETTES, GREEN_OVERLAY_COLOR, GREEN_TILE_THRESHOLD


def render_hole_to_image(
    hole_data: Dict[str, Any],
    tileset: TilesetData
) -> Image.Image:
    """
    Render a hole to a PIL Image.

    Args:
        hole_data: Hole data dictionary (from JSON)
        tileset: TilesetData instance with CHR tile data

    Returns:
        PIL Image object
    """
    terrain = hole_data["terrain"]
    attributes = hole_data["attributes"]

    terrain_width = terrain["width"]
    terrain_height = terrain["height"]

    # Parse terrain rows (should be pre-parsed by HoleData, but handle both cases)
    terrain_tiles = []
    for row_data in terrain["rows"]:
        if isinstance(row_data, str):
            # Hex string format
            row = [int(x, 16) for x in row_data.split()]
        else:
            # Already parsed
            row = row_data
        terrain_tiles.append(row)

    # Attribute rows are already integer arrays
    attr_rows = attributes["rows"]

    # Create image
    img_width = terrain_width * TILE_SIZE
    img_height = terrain_height * TILE_SIZE
    img = Image.new('RGB', (img_width, img_height))
    pixels = img.load()
    assert pixels is not None

    # Render each tile
    for tile_row in range(terrain_height):
        for tile_col in range(terrain_width):
            # Get tile index
            tile_idx = terrain_tiles[tile_row][tile_col]

            # Get palette index from attributes
            # Attributes are per-supertile (2x2 tiles)
            # Attribute data already has HUD column removed, so direct mapping
            attr_row = tile_row // 2
            attr_col = tile_col // 2

            if attr_row < len(attr_rows) and attr_col < len(attr_rows[attr_row]):
                palette_idx = attr_rows[attr_row][attr_col]
            else:
                palette_idx = 1  # Default to fairway/rough

            palette = PALETTES[palette_idx]

            # Decode tile
            tile_pixels = tileset.decode_tile(tile_idx)

            # Draw tile
            base_x = tile_col * TILE_SIZE
            base_y = tile_row * TILE_SIZE

            for py in range(8):
                for px in range(8):
                    color_idx = tile_pixels[py][px]
                    color = palette[color_idx]
                    pixels[base_x + px, base_y + py] = color

    # Render putting green overlay
    if "greens" in hole_data and "green" in hole_data:
        greens = hole_data["greens"]
        green_x = hole_data["green"]["x"]  # Pixel offset from top-left
        green_y = hole_data["green"]["y"]

        # Parse greens data (handle both formats)
        greens_data = []
        for row_data in greens["rows"]:
            if isinstance(row_data, str):
                # Hex string format
                row = [int(x, 16) for x in row_data.split()]
            else:
                # Already parsed
                row = row_data
            greens_data.append(row)

        # Overlay green pixels where value >= GREEN_TILE_THRESHOLD
        for gy, grow in enumerate(greens_data):
            for gx, gval in enumerate(grow):
                if gval >= GREEN_TILE_THRESHOLD:
                    px = green_x + gx
                    py = green_y + gy
                    if 0 <= px < img_width and 0 <= py < img_height:
                        pixels[px, py] = GREEN_OVERLAY_COLOR

    return img
