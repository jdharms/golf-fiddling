"""
NES Open Tournament Golf - Editor Constants

All configuration constants for the editor including dimensions,
colors, palettes, and layout values.
"""

# Constants
TILE_SIZE = 8
BYTES_PER_TILE = 16
TERRAIN_WIDTH = 22
GREENS_WIDTH = 24
GREENS_HEIGHT = 24

# UI Layout
PICKER_WIDTH = 200
TOOLBAR_HEIGHT = 40
STATUS_HEIGHT = 30
CANVAS_OFFSET_X = PICKER_WIDTH
CANVAS_OFFSET_Y = TOOLBAR_HEIGHT

# Colors
COLOR_BG = (48, 48, 48)
COLOR_TOOLBAR = (32, 32, 32)
COLOR_STATUS = (32, 32, 32)
COLOR_PICKER_BG = (40, 40, 40)
COLOR_GRID = (80, 80, 80)
COLOR_GRID_SUPER = (120, 120, 120)
COLOR_SELECTION = (255, 255, 0)
COLOR_TEXT = (255, 255, 255)
COLOR_BUTTON = (64, 64, 64)
COLOR_BUTTON_HOVER = (80, 80, 80)
COLOR_BUTTON_ACTIVE = (100, 100, 200)

# Palettes (RGB tuples)
PALETTES = [
    [(0, 0, 0), (12, 147, 0), (255, 255, 255), (100, 176, 255)],  # 0: HUD (unused)
    [(0, 0, 0), (12, 147, 0), (0, 82, 0), (92, 228, 48)],         # 1: Fairway/Rough
    [(0, 0, 0), (12, 147, 0), (0, 82, 0), (188, 190, 0)],         # 2: Bunker
    [(0, 0, 0), (12, 147, 0), (0, 82, 0), (100, 176, 255)],       # 3: Water
]

# Greens palette (single palette for greens view)
GREENS_PALETTE = [(0, 0, 0), (12, 147, 0), (0, 82, 0), (92, 228, 48)]
GREENS_PALETTE_NUM = 4  # arbitrary

# Putting green overlay color
GREEN_OVERLAY_COLOR = (0, 82, 0)

# NES sprite coordinate offsets
SPRITE_OFFSET_Y = +1  # Scanline delay
