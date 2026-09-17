"""
Two independent QR decoders, used to check what a scanner actually reads.

Two rather than one on purpose: they disagree about marginal images, and a
fixed mask is only safe if both of them read every payload under every
simulated capture condition. zxing-cpp is the closest stand-in for what phone
scanners run; OpenCV's detector is stricter and catches images that are merely
borderline.

**Development-only.** Both decoders are dev dependencies, so nothing outside
the tests and `golf-qr-validate` may import this module — `golf.qr` itself
does not, and must not start.
"""

from collections.abc import Callable

import cv2
import numpy as np
import zxingcpp
from PIL import Image


def decode_zxing(image: Image.Image) -> str | None:
    for result in zxingcpp.read_barcodes(image):
        if result.valid and result.format == zxingcpp.BarcodeFormat.QRCode:
            return result.text
    return None


def decode_opencv(image: Image.Image) -> str | None:
    array = np.array(image.convert("L"))
    text, _points, _straight = cv2.QRCodeDetector().detectAndDecode(array)
    return text or None


DECODERS: dict[str, Callable[[Image.Image], str | None]] = {
    "zxing": decode_zxing,
    "opencv": decode_opencv,
}
