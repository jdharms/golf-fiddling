#!/usr/bin/env python3
"""
NES Open Tournament Golf - Course Visualizer

Renders course holes as PNG images using tileset and palette data.
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow library required. Install with: pip install Pillow")
    sys.exit(1)


# Palettes (RGB tuples)
PALETTES = [
    [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0xFF, 0xFF, 0xFF), (0x64, 0xB0, 0xFF)],  # 0: HUD
    [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0x00, 0x52, 0x00), (0x5C, 0xE4, 0x30)],  # 1: Fairway/Rough
    [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0x00, 0x52, 0x00), (0xBC, 0xBE, 0x00)],  # 2: Bunker
    [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0x00, 0x52, 0x00), (0x64, 0xB0, 0xFF)],  # 3: Water
]

TILE_SIZE = 8
BYTES_PER_TILE = 16

# Putting green color
GREEN_COLOR = (0x00, 0x52, 0x00)


class Tileset:
    """Loads and decodes NES CHR tile data."""
    
    def __init__(self, chr_path: str):
        with open(chr_path, 'rb') as f:
            self.data = f.read()
        
        self.num_tiles = len(self.data) // BYTES_PER_TILE
        print(f"Loaded tileset: {self.num_tiles} tiles")
    
    def decode_tile(self, tile_idx: int) -> List[List[int]]:
        """
        Decode a single 8x8 tile into 2-bit pixel values.
        Returns 8x8 array of values 0-3.
        """
        if tile_idx >= self.num_tiles:
            # Return empty tile for out-of-range indices
            return [[0] * 8 for _ in range(8)]
        
        offset = tile_idx * BYTES_PER_TILE
        plane0 = self.data[offset:offset + 8]      # Low bit plane
        plane1 = self.data[offset + 8:offset + 16]  # High bit plane
        
        pixels = []
        for row in range(8):
            row_pixels = []
            for col in range(8):
                bit_mask = 0x80 >> col
                low_bit = 1 if (plane0[row] & bit_mask) else 0
                high_bit = 1 if (plane1[row] & bit_mask) else 0
                pixel = low_bit | (high_bit << 1)
                row_pixels.append(pixel)
            pixels.append(row_pixels)
        
        return pixels


def render_hole(hole_path: str, tileset: Tileset, output_path: str):
    """Render a single hole to PNG."""
    
    with open(hole_path, 'r') as f:
        hole_data = json.load(f)
    
    terrain = hole_data["terrain"]
    attributes = hole_data["attributes"]
    
    terrain_width = terrain["width"]
    terrain_height = terrain["height"]
    
    # Parse terrain rows from hex strings
    terrain_tiles = []
    for row_str in terrain["rows"]:
        row = [int(x, 16) for x in row_str.split()]
        terrain_tiles.append(row)
    
    # Attribute rows are already integer arrays
    attr_rows = attributes["rows"]
    
    # Create image
    img_width = terrain_width * TILE_SIZE
    img_height = terrain_height * TILE_SIZE
    img = Image.new('RGB', (img_width, img_height))
    pixels = img.load()
    assert(pixels is not None)
    
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
        
        # Parse greens data
        greens_data = []
        for row_str in greens["rows"]:
            row = [int(x, 16) for x in row_str.split()]
            greens_data.append(row)
        
        # Overlay green pixels where value >= $30
        for gy, grow in enumerate(greens_data):
            for gx, gval in enumerate(grow):
                if gval >= 0x30:
                    px = green_x + gx
                    py = green_y + gy
                    if 0 <= px < img_width and 0 <= py < img_height:
                        pixels[px, py] = GREEN_COLOR
    
    # Save image
    img.save(output_path)
    print(f"Saved: {output_path} ({img_width}x{img_height})")


def render_course(course_dir: str, tileset: Tileset, output_dir: str):
    """Render all holes in a course."""
    course_path = Path(course_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Find all hole files
    hole_files = sorted(course_path.glob("hole_*.json"))
    
    if not hole_files:
        print(f"No hole files found in {course_dir}")
        return
    
    print(f"Rendering {len(hole_files)} holes from {course_dir}...")
    
    for hole_file in hole_files:
        hole_name = hole_file.stem  # e.g., "hole_01"
        out_file = output_path / f"{hole_name}.png"
        render_hole(str(hole_file), tileset, str(out_file))


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Render single hole:")
        print("    python visualize.py <tileset.bin> <hole.json> [output.png]")
        print("")
        print("  Render entire course:")
        print("    python visualize.py <tileset.bin> <course_dir/> [output_dir/]")
        print("")
        print("Example:")
        print("  python visualize.py chr-ram.bin courses/japan/hole_01.json")
        print("  python visualize.py chr-ram.bin courses/japan/ renders/japan/")
        sys.exit(1)
    
    tileset_path = sys.argv[1]
    input_path = sys.argv[2]
    
    tileset = Tileset(tileset_path)
    
    # Check if input is a file or directory
    input_p = Path(input_path)
    
    if input_p.is_file():
        # Single hole
        output_path = sys.argv[3] if len(sys.argv) > 3 else input_p.stem + ".png"
        render_hole(input_path, tileset, output_path)
    
    elif input_p.is_dir():
        # Entire course
        output_dir = sys.argv[3] if len(sys.argv) > 3 else f"renders/{input_p.name}"
        render_course(input_path, tileset, output_dir)
    
    else:
        print(f"Error: {input_path} not found")
        sys.exit(1)


if __name__ == "__main__":
    main()