"""
Simulated capture conditions, for deciding whether a fixed mask is safe.

The on-cart encoder uses one hard-wired mask instead of the spec's penalty
scoring. That is only defensible if every mask candidate survives realistic
capture, so these degradations stand in for the ways a player's phone actually
sees the screen: an emulator window at some integer zoom, NTSC pixel aspect,
camera blur and rotation, a Discord-grade JPEG of a screenshot, a soft capture
from a stream.

Each degradation takes the clean 256x240 render and returns what the decoder
gets to see.
"""

import io
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

#: NES pixels are not square on a real display; 8:7 is the usual correction.
PIXEL_ASPECT = 8 / 7


def _scale(image: Image.Image, factor: int) -> Image.Image:
    return image.resize(
        (image.width * factor, image.height * factor), Image.Resampling.NEAREST
    )


def native(image: Image.Image) -> Image.Image:
    return image


def scale2(image: Image.Image) -> Image.Image:
    return _scale(image, 2)


def scale3(image: Image.Image) -> Image.Image:
    return _scale(image, 3)


def aspect_corrected(image: Image.Image) -> Image.Image:
    """3x zoom with the 8:7 horizontal stretch a real display applies."""
    scaled = _scale(image, 3)
    return scaled.resize(
        (round(scaled.width * PIXEL_ASPECT), scaled.height), Image.Resampling.BICUBIC
    )


def blur_soft(image: Image.Image) -> Image.Image:
    return _scale(image, 3).filter(ImageFilter.GaussianBlur(radius=1.5))


def blur_heavy(image: Image.Image) -> Image.Image:
    return _scale(image, 3).filter(ImageFilter.GaussianBlur(radius=3.0))


def jpeg_low(image: Image.Image) -> Image.Image:
    """A screenshot that has been through a chat client."""
    buffer = io.BytesIO()
    _scale(image, 3).save(buffer, format="JPEG", quality=60)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def rotated(image: Image.Image) -> Image.Image:
    """Phone held at an angle."""
    return _scale(image, 3).rotate(
        7, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255)
    )


def soft_capture(image: Image.Image) -> Image.Image:
    """Downscaled and blown back up, as a restreamed or resized capture is."""
    scaled = _scale(image, 3)
    small = scaled.resize(
        (round(scaled.width * 0.45), round(scaled.height * 0.45)),
        Image.Resampling.LANCZOS,
    )
    return small.resize(scaled.size, Image.Resampling.BICUBIC)


def scanlines(image: Image.Image) -> Image.Image:
    """Crude CRT stand-in: darken one in every three output lines at 3x."""
    array = np.array(_scale(image, 3).convert("RGB"))
    array[::3] //= 2
    return Image.fromarray(array)


def combined_worst(image: Image.Image) -> Image.Image:
    """Aspect stretch, rotation, blur and JPEG all at once."""
    result = aspect_corrected(image)
    result = result.rotate(
        5, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255)
    )
    result = result.filter(ImageFilter.GaussianBlur(radius=1.2))
    buffer = io.BytesIO()
    result.save(buffer, format="JPEG", quality=70)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


@dataclass(frozen=True)
class Degradation:
    name: str
    apply: Callable[[Image.Image], Image.Image]


DEGRADATIONS: tuple[Degradation, ...] = (
    Degradation("native", native),
    Degradation("scale2", scale2),
    Degradation("scale3", scale3),
    Degradation("aspect", aspect_corrected),
    Degradation("blur_soft", blur_soft),
    Degradation("blur_heavy", blur_heavy),
    Degradation("jpeg_low", jpeg_low),
    Degradation("rotated", rotated),
    Degradation("soft_capture", soft_capture),
    Degradation("scanlines", scanlines),
    Degradation("combined", combined_worst),
)

DEGRADATIONS_BY_NAME = {d.name: d for d in DEGRADATIONS}
