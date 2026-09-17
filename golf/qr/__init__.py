"""
Scorecard QR submission: payload, MAC, QR encoding and NES rendering.

This package is the reference implementation ("the oracle") for the on-cart
QR generator described in `docs/scorecard_qr.md`. Everything here is written
to produce byte-for-byte the same code word stream and module matrix the 6502
port will produce, so the port can be differentially tested against it.
"""

from golf.qr.halfsiphash import halfsiphash
from golf.qr.payload import (
    MAC_LEN,
    PAYLOAD_LEN,
    PROTOCOL_VERSION,
    URL_PREFIX,
    HoleRecord,
    RoundPayload,
    base64url_decode,
    base64url_encode,
)

__all__ = [
    "MAC_LEN",
    "PAYLOAD_LEN",
    "PROTOCOL_VERSION",
    "URL_PREFIX",
    "HoleRecord",
    "RoundPayload",
    "base64url_decode",
    "base64url_encode",
    "halfsiphash",
]
