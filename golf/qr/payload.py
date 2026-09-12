"""
The 36-byte scorecard submission payload and its URL encoding.

Layout (see `docs/scorecard_qr.md`):

    byte  0      protocol version
    bytes 1-8    seed ID
    bytes 9-12   player ID
    byte  13     flags (bits 0-1 player slot, 2-7 reserved)
    bytes 14-31  hole records, one per hole, holes 1-18
    bytes 32-35  HalfSipHash-2-4-32 over bytes 0-31

A hole record packs `strokes - 1` in the high nibble and `putts` in the low
nibble, so strokes are representable 1-16 and putts 0-15. Both clamp; whether
clamping happened is exposed rather than swallowed, since a clamped stroke
count makes the round total wrong.
"""

from dataclasses import dataclass

from golf.qr.halfsiphash import halfsiphash

PROTOCOL_VERSION = 1

URL_PREFIX = "https://nesopengolf.com/s/"

SEED_ID_LEN = 8
PLAYER_ID_LEN = 4
KEY_LEN = 8
HOLE_COUNT = 18

MAC_LEN = 4
BODY_LEN = 32
PAYLOAD_LEN = BODY_LEN + MAC_LEN

#: Length of the base64url text, and of the whole URL. Both are constants the
#: 6502 port bakes in, so they are asserted rather than computed on cart.
BASE64_LEN = 48
URL_LEN = len(URL_PREFIX) + BASE64_LEN

#: How the hole-record byte is split. 4 gives strokes 1-16 and putts 0-15; 5
#: would give strokes 1-32 and putts 0-7. This is the only place the split is
#: decided — see the open question in `docs/scorecard_qr.md`.
STROKE_BITS = 4
PUTT_BITS = 8 - STROKE_BITS

MAX_STROKES = 1 << STROKE_BITS
MAX_PUTTS = (1 << PUTT_BITS) - 1

_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def pack_hole(strokes: int, putts: int, stroke_bits: int = STROKE_BITS) -> int:
    """
    Pack one hole into a byte: `strokes - 1` in the high bits, putts in the
    low. Both clamp, which is what the ROM will do.
    """
    putt_bits = 8 - stroke_bits
    strokes = min(strokes, 1 << stroke_bits)
    putts = min(putts, (1 << putt_bits) - 1)
    return ((strokes - 1) << putt_bits) | putts


def unpack_hole(value: int, stroke_bits: int = STROKE_BITS) -> tuple[int, int]:
    """Inverse of `pack_hole`, as (strokes, putts)."""
    putt_bits = 8 - stroke_bits
    return ((value >> putt_bits) + 1, value & ((1 << putt_bits) - 1))


def base64url_encode(data: bytes) -> str:
    """
    Unpadded base64url. Written out longhand rather than via `base64` so the
    6502 port has a direct model; the payload length is always a multiple of 3
    so there is no partial-group path.
    """
    if len(data) % 3 != 0:
        raise ValueError(
            f"payload length must be a multiple of 3 to stay pad-free, got {len(data)}"
        )
    out = []
    for i in range(0, len(data), 3):
        group = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
        out.append(_B64_ALPHABET[(group >> 18) & 0x3F])
        out.append(_B64_ALPHABET[(group >> 12) & 0x3F])
        out.append(_B64_ALPHABET[(group >> 6) & 0x3F])
        out.append(_B64_ALPHABET[group & 0x3F])
    return "".join(out)


def base64url_decode(text: str) -> bytes:
    if len(text) % 4 != 0:
        raise ValueError(
            f"base64url text must be a multiple of 4 chars, got {len(text)}"
        )
    lookup = {c: i for i, c in enumerate(_B64_ALPHABET)}
    out = bytearray()
    for i in range(0, len(text), 4):
        group = 0
        for j in range(4):
            try:
                group = (group << 6) | lookup[text[i + j]]
            except KeyError:
                raise ValueError(
                    f"invalid base64url character {text[i + j]!r}"
                ) from None
        out += bytes(((group >> 16) & 0xFF, (group >> 8) & 0xFF, group & 0xFF))
    return bytes(out)


@dataclass(frozen=True)
class HoleRecord:
    """One hole's result. `strokes` includes the putts."""

    strokes: int
    putts: int

    def __post_init__(self) -> None:
        if self.strokes < 1:
            raise ValueError(f"strokes must be at least 1, got {self.strokes}")
        if self.putts < 0:
            raise ValueError(f"putts cannot be negative, got {self.putts}")
        if self.putts > self.strokes:
            raise ValueError(
                f"putts ({self.putts}) cannot exceed strokes ({self.strokes})"
            )

    @property
    def strokes_clamped(self) -> bool:
        return self.strokes > MAX_STROKES

    @property
    def putts_clamped(self) -> bool:
        return self.putts > MAX_PUTTS

    def pack(self) -> int:
        return pack_hole(self.strokes, self.putts)


def _unpack_hole(value: int) -> HoleRecord:
    """
    Decode a hole record. Bypasses `HoleRecord`'s validation: a clamped record
    can legitimately decode to putts > strokes, and the server needs to see
    what the cart actually sent rather than get an exception.
    """
    strokes, putts = unpack_hole(value)
    record = object.__new__(HoleRecord)
    object.__setattr__(record, "strokes", strokes)
    object.__setattr__(record, "putts", putts)
    return record


@dataclass(frozen=True)
class RoundPayload:
    """A completed 18-hole round, ready to be signed and encoded."""

    seed_id: bytes
    player_id: bytes
    holes: tuple[HoleRecord, ...]
    player_slot: int = 0
    protocol_version: int = PROTOCOL_VERSION
    #: Bits 2-7 of the flags byte. Always zero in protocol version 1, but
    #: carried so a parsed payload re-serializes to the exact bytes received.
    reserved_flags: int = 0

    def __post_init__(self) -> None:
        if len(self.seed_id) != SEED_ID_LEN:
            raise ValueError(
                f"seed_id must be {SEED_ID_LEN} bytes, got {len(self.seed_id)}"
            )
        if len(self.player_id) != PLAYER_ID_LEN:
            raise ValueError(
                f"player_id must be {PLAYER_ID_LEN} bytes, got {len(self.player_id)}"
            )
        if len(self.holes) != HOLE_COUNT:
            raise ValueError(f"expected {HOLE_COUNT} holes, got {len(self.holes)}")
        if not 0 <= self.player_slot <= 3:
            raise ValueError(f"player_slot must fit 2 bits, got {self.player_slot}")
        if not 0 <= self.reserved_flags <= 0x3F:
            raise ValueError(
                f"reserved_flags must fit 6 bits, got {self.reserved_flags}"
            )
        if not 0 <= self.protocol_version <= 0xFF:
            raise ValueError(
                f"protocol_version must be a byte, got {self.protocol_version}"
            )

    @property
    def flags(self) -> int:
        return ((self.reserved_flags & 0x3F) << 2) | (self.player_slot & 0x03)

    @property
    def clamped_holes(self) -> tuple[int, ...]:
        """1-based hole numbers whose strokes or putts did not fit the nibble."""
        return tuple(
            i + 1
            for i, hole in enumerate(self.holes)
            if hole.strokes_clamped or hole.putts_clamped
        )

    @property
    def total_strokes(self) -> int:
        return sum(hole.strokes for hole in self.holes)

    @property
    def total_putts(self) -> int:
        return sum(hole.putts for hole in self.holes)

    def body(self) -> bytes:
        """Bytes 0-31: everything the MAC covers."""
        out = bytearray()
        out.append(self.protocol_version)
        out += self.seed_id
        out += self.player_id
        out.append(self.flags)
        out += bytes(hole.pack() for hole in self.holes)
        assert len(out) == BODY_LEN, len(out)
        return bytes(out)

    def mac(self, key: bytes) -> bytes:
        if len(key) != KEY_LEN:
            raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
        return halfsiphash(self.body(), key, outlen=MAC_LEN)

    def to_bytes(self, key: bytes) -> bytes:
        out = self.body() + self.mac(key)
        assert len(out) == PAYLOAD_LEN, len(out)
        return out

    def to_url(self, key: bytes) -> str:
        url = URL_PREFIX + base64url_encode(self.to_bytes(key))
        assert len(url) == URL_LEN, len(url)
        return url

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple["RoundPayload", bytes]:
        """
        Parse a payload. Returns the round and the MAC as sent; the caller
        recomputes the MAC to verify it.
        """
        if len(data) != PAYLOAD_LEN:
            raise ValueError(f"payload must be {PAYLOAD_LEN} bytes, got {len(data)}")
        payload = cls(
            protocol_version=data[0],
            seed_id=data[1:9],
            player_id=data[9:13],
            player_slot=data[13] & 0x03,
            reserved_flags=(data[13] >> 2) & 0x3F,
            holes=tuple(_unpack_hole(b) for b in data[14:32]),
        )
        return payload, data[32:36]

    @classmethod
    def from_url(cls, url: str) -> tuple["RoundPayload", bytes]:
        if not url.startswith(URL_PREFIX):
            raise ValueError(f"URL does not start with {URL_PREFIX!r}")
        return cls.from_bytes(base64url_decode(url[len(URL_PREFIX) :]))


def verify(data: bytes, key: bytes) -> bool:
    """
    MAC check on a received payload.

    Deliberately hashes the literal bytes received rather than re-serializing
    a parsed payload: anything the parser would normalize away — reserved flag
    bits, a future protocol version's fields — has to stay covered by the MAC.
    """
    if len(data) != PAYLOAD_LEN:
        raise ValueError(f"payload must be {PAYLOAD_LEN} bytes, got {len(data)}")
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    expected = halfsiphash(data[:BODY_LEN], key, outlen=MAC_LEN)
    diff = 0
    for a, b in zip(data[BODY_LEN:], expected, strict=True):
        diff |= a ^ b
    return diff == 0
