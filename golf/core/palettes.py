"""
NES Open Tournament Golf - Color Palettes and Dimensions

Shared constants for NES color palettes and course dimensions used
across all tools (editor, visualizer, analyzer).
"""

from typing import List, Tuple

# Type alias for RGB color
RGBColor = Tuple[int, int, int]

# NES color palettes (RGB tuples)
# Each palette has 4 colors indexed 0-3
PALETTES: List[List[RGBColor]] = [
    [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0xFF, 0xFF, 0xFF), (0x64, 0xB0, 0xFF)],  # 0: HUD
    [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0x00, 0x52, 0x00), (0x5C, 0xE4, 0x30)],  # 1: Fairway/Rough
    [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0x00, 0x52, 0x00), (0xBC, 0xBE, 0x00)],  # 2: Bunker
    [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0x00, 0x52, 0x00), (0x64, 0xB0, 0xFF)],  # 3: Water
]

# Greens palette (used for putting green rendering)
GREENS_PALETTE: List[RGBColor] = [(0x00, 0x00, 0x00), (0x0C, 0x93, 0x00), (0x00, 0x52, 0x00), (0x5C, 0xE4, 0x30)]

# Putting green overlay color (for visualization)
GREEN_OVERLAY_COLOR: RGBColor = (0x00, 0x52, 0x00)

# Greens tile threshold - tiles >= this value are considered "on the putting green"
GREEN_TILE_THRESHOLD = 0x30

# Course dimensions
TERRAIN_WIDTH = 22        # Width of terrain in 8x8 tiles
TERRAIN_ROW_WIDTH = 22    # Alias for compatibility
ATTR_ROW_WIDTH = 11       # Width of attribute data (TERRAIN_WIDTH / 2)
ATTR_TOTAL_BYTES = 72     # Total attribute bytes per hole

GREENS_WIDTH = 24         # Width of greens data in pixels
GREENS_HEIGHT = 24        # Height of greens data in pixels
