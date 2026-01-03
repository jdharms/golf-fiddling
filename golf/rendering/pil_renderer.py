"""
NES Open Tournament Golf - PIL Renderer

PIL-based rendering for generating PNG images of golf course holes.
Used by the visualize tool to create static images.
"""

from typing import Any

try:
    from PIL import Image
except ImportError:
    raise ImportError("Pillow library required. Install with: pip install Pillow")

from ..core.chr_tile import TILE_SIZE, TilesetData
from ..core.palettes import GREEN_OVERLAY_COLOR, GREEN_TILE_THRESHOLD, PALETTES
from .pil_sprite import PILSprite


def render_hole_to_image(
    hole_data: dict[str, Any],
    tileset: TilesetData,
    sprites: dict[str, PILSprite] | None = None,
    render_sprites: bool = True,
    selected_flag_index: int = 0,
) -> Image.Image:
    """
    Render a hole to a PIL Image.

    Args:
        hole_data: Hole data dictionary (from JSON)
        tileset: TilesetData instance with CHR tile data
        sprites: Dictionary of loaded PILSprite instances (optional)
        render_sprites: Whether to render sprites on the image (default: True)
        selected_flag_index: Which flag position to render (0-3, default: 0)

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
    img = Image.new("RGB", (img_width, img_height))
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

    # Render sprites if requested
    if render_sprites and sprites:
        _render_terrain_sprites(img, sprites, hole_data, selected_flag_index)

    return img


def _render_terrain_sprites(
    img: Image.Image,
    sprites: dict[str, PILSprite],
    hole_data: dict[str, Any],
    selected_flag_index: int,
):
    """
    Render flag, tee, and ball sprites on terrain view.

    Args:
        img: PIL Image to render onto (modified in-place)
        sprites: Dictionary of loaded PILSprite instances
        hole_data: Hole data dictionary (from JSON or HoleData)
        selected_flag_index: Which flag position to render (0-3)
    """
    # Support both raw JSON (top-level keys) and HoleData format (metadata dict)
    metadata = hole_data.get("metadata", hole_data)

    # Render tee sprite
    if sprites.get("tee"):
        tee = metadata.get("tee", {})
        if tee:
            tee_x = tee.get("x", 0)
            tee_y = tee.get("y", 0)
            sprites["tee"].render_to_image(img, tee_x, tee_y)

    # Render ball sprite at tee position
    if sprites.get("ball"):
        tee = metadata.get("tee", {})
        if tee:
            tee_x = tee.get("x", 0)
            tee_y = tee.get("y", 0)
            sprites["ball"].render_to_image(img, tee_x, tee_y)

    # Render flag sprite
    if sprites.get("flag"):
        flag_positions = metadata.get("flag_positions", [])
        if flag_positions and 0 <= selected_flag_index < len(flag_positions):
            flag_pos = flag_positions[selected_flag_index]
            green_flag_x = flag_pos.get("x_offset", 0)
            green_flag_y = flag_pos.get("y_offset", 0)

            # Get green position (from top-level green key)
            green = hole_data.get("green", {})
            green_x = green.get("x", 0)
            green_y = green.get("y", 0)

            # Calculate flag position (green position + flag offset in tiles)
            # Flag offsets are in 1/8th pixel units, so divide by 8 to convert to pixels
            flag_x = green_x + (green_flag_x // 8)
            flag_y = green_y + (green_flag_y // 8)

            sprites["flag"].render_to_image(img, flag_x, flag_y)
