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
from ..core.palettes import (
    GREEN_OVERLAY_COLOR,
    GREEN_TILE_THRESHOLD,
    GREENS_HEIGHT,
    GREENS_PALETTE,
    GREENS_WIDTH,
    PALETTES,
)
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


def render_greens_to_image(
    hole_data: dict[str, Any],
    greens_tileset: TilesetData,
    scale: int = 1,
) -> Image.Image:
    """
    Render the greens tile grid to a PIL Image.

    Args:
        hole_data: Hole data dictionary (from JSON)
        greens_tileset: TilesetData for greens CHR tiles
        scale: Pixel scale factor (default: 1)

    Returns:
        PIL Image (192x192 pixels at scale=1)
    """
    greens = hole_data["greens"]

    # Parse greens rows (handle both formats)
    greens_tiles = []
    for row_data in greens["rows"]:
        if isinstance(row_data, str):
            # Hex string format
            row = [int(x, 16) for x in row_data.split()]
        else:
            # Already parsed
            row = row_data
        greens_tiles.append(row)

    # Create image
    img_width = GREENS_WIDTH * TILE_SIZE * scale
    img_height = GREENS_HEIGHT * TILE_SIZE * scale
    img = Image.new("RGB", (img_width, img_height))
    pixels = img.load()
    assert pixels is not None

    # Render each tile
    for tile_row in range(GREENS_HEIGHT):
        for tile_col in range(GREENS_WIDTH):
            # Get tile index
            tile_idx = greens_tiles[tile_row][tile_col]

            # Decode tile
            tile_pixels = greens_tileset.decode_tile(tile_idx)

            # Draw tile with scaling
            base_x = tile_col * TILE_SIZE * scale
            base_y = tile_row * TILE_SIZE * scale

            for py in range(8):
                for px in range(8):
                    color_idx = tile_pixels[py][px]
                    color = GREENS_PALETTE[color_idx]
                    # Apply scaling
                    for sy in range(scale):
                        for sx in range(scale):
                            pixels[base_x + px * scale + sx, base_y + py * scale + sy] = (
                                color
                            )

    return img


def render_flag_to_image(
    hole_data: dict[str, Any],
    flag_sprite: PILSprite,
    flag_index: int,
    greens_size: int = GREENS_WIDTH * TILE_SIZE,
    scale: int = 1,
    debug_background: bool = False,
    cup_sprite: PILSprite | None = None,
) -> Image.Image:
    """
    Render a single flag position on transparent background.

    The output image matches the greens image dimensions so it can be
    layered directly over the greens render.

    Args:
        hole_data: Hole data dictionary
        flag_sprite: The flag PILSprite instance (green-flag.json)
        flag_index: Which flag position (0-3)
        greens_size: Size of greens image in pixels (192 at scale=1)
        scale: Pixel scale factor
        debug_background: If True, use gray (#808080) background instead of transparent
        cup_sprite: The cup PILSprite instance (green-cup.json), optional

    Returns:
        PIL RGBA Image with transparent (or gray debug) background + flag sprite
    """
    # Create image matching greens dimensions
    img_size = greens_size * scale
    if debug_background:
        # Gray background for debugging flag positioning
        img = Image.new("RGBA", (img_size, img_size), (128, 128, 128, 255))
    else:
        # Transparent background
        img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))

    # Get flag position from metadata
    # Support both raw JSON (top-level keys) and nested metadata format
    metadata = hole_data.get("metadata", hole_data)
    flag_positions = metadata.get("flag_positions", [])

    if not flag_positions or flag_index >= len(flag_positions):
        return img  # Return empty transparent image if no flag position

    flag_pos = flag_positions[flag_index]
    # Flag offsets are pixel coordinates within the 24x24 greens grid
    # (no division needed - unlike terrain view which uses 1/8th pixel units)
    flag_x = flag_pos.get("x_offset", 0)
    flag_y = flag_pos.get("y_offset", 0)

    # Render cup first (below flag), then flag on top - matching editor behavior
    if cup_sprite:
        cup_sprite.render_to_image(img, flag_x * scale, flag_y * scale, scale)
    flag_sprite.render_to_image(img, flag_x * scale, flag_y * scale, scale)

    return img


def render_all_flags_to_images(
    hole_data: dict[str, Any],
    flag_sprite: PILSprite,
    greens_size: int = GREENS_WIDTH * TILE_SIZE,
    scale: int = 1,
    debug_background: bool = False,
    cup_sprite: PILSprite | None = None,
) -> list[Image.Image]:
    """
    Render all 4 flag positions as separate transparent images.

    Args:
        hole_data: Hole data dictionary
        flag_sprite: The flag PILSprite instance
        greens_size: Size of greens image in pixels (192 at scale=1)
        scale: Pixel scale factor
        debug_background: If True, use gray (#808080) background instead of transparent
        cup_sprite: The cup PILSprite instance (green-cup.json), optional

    Returns:
        List of 4 PIL RGBA Images
    """
    return [
        render_flag_to_image(
            hole_data, flag_sprite, i, greens_size, scale, debug_background, cup_sprite
        )
        for i in range(4)
    ]
