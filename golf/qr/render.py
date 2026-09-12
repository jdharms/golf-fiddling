"""
PNG rendering of the QR screen, in NES colours.

Everything here renders from the CHR + nametable rather than straight from the
module matrix, so a preview image is an honest simulation of what the PPU will
put on screen — a mistake in the tile pipeline shows up in the picture.
"""

import numpy as np
from PIL import Image

from golf.core.palettes import NES_SYSTEM_PALETTE
from golf.qr import nes
from golf.qr.encoder import SIZE, QrMatrix


def _colorize(indices: np.ndarray, light: int, dark: int) -> Image.Image:
    palette = np.array(
        [NES_SYSTEM_PALETTE[light], NES_SYSTEM_PALETTE[dark]], dtype=np.uint8
    )
    return Image.fromarray(palette[indices], mode="RGB")


def render_screen(
    matrix: QrMatrix,
    scale: int = 1,
    light: int = nes.COLOR_LIGHT,
    dark: int = nes.COLOR_DARK,
) -> Image.Image:
    """The whole 256x240 screen, optionally integer-scaled."""
    image = _colorize(nes.screen_pixels(matrix.rows()), light, dark)
    if scale != 1:
        image = image.resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
    return image


def render_code(
    matrix: QrMatrix,
    scale: int = 1,
    quiet_modules: int = nes.QUIET_MODULES,
    light: int = nes.COLOR_LIGHT,
    dark: int = nes.COLOR_DARK,
) -> Image.Image:
    """
    Just the code plus its quiet zone — 180x180 at 4 px per module with the
    spec's 4-module quiet zone. Cropped out of the real screen placement.
    """
    margins = nes.quiet_zone_margins()
    quiet_px = quiet_modules * nes.MODULE_PX
    if min(margins.values()) < quiet_px:
        raise ValueError(f"screen placement leaves too little quiet zone: {margins}")

    screen = nes.screen_pixels(matrix.rows())
    origin_x = nes.SCREEN_TILE_ORIGIN[0] * nes.TILE_PX
    origin_y = nes.SCREEN_TILE_ORIGIN[1] * nes.TILE_PX
    code_px = SIZE * nes.MODULE_PX
    cropped = screen[
        origin_y - quiet_px : origin_y + code_px + quiet_px,
        origin_x - quiet_px : origin_x + code_px + quiet_px,
    ]
    image = _colorize(cropped, light, dark)
    if scale != 1:
        image = image.resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
    return image
