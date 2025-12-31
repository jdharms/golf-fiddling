"""
NES Open Tournament Golf - Editor Constants

Editor-specific configuration constants including UI layout, colors,
and pygame-specific settings.

For NES-specific constants (tile sizes, palettes, dimensions), see golf.core modules.
"""

# Import shared NES constants from golf.core
from golf.core.chr_tile import TILE_SIZE, BYTES_PER_TILE
from golf.core.palettes import (
    TERRAIN_WIDTH,
    GREENS_WIDTH,
    GREENS_HEIGHT,
    PALETTES,
    GREENS_PALETTE,
    GREEN_OVERLAY_COLOR,
)

# UI Layout
PICKER_WIDTH = 400
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

# Greens palette number (arbitrary identifier for pygame rendering)
GREENS_PALETTE_NUM = 4

# NES sprite coordinate offsets
SPRITE_OFFSET_Y = +1  # Scanline delay
