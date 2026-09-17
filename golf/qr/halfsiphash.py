"""
HalfSipHash-2-4, the 32-bit-word SipHash variant.

Faithful port of the reference implementation (veorq/SipHash `halfsiphash.c`),
kept deliberately close to the C so the 6502 port has an unambiguous model to
follow. Verified against the project's official test vectors for both output
lengths (`tests/unit/test_halfsiphash.py`).

The scorecard payload uses `outlen=4`. That path skips the three `$ee`/`$dd`
tweaks and the second set of finalization rounds that `outlen=8` needs, and
the 32-byte MAC'd region is exactly 8 whole words, so the tail-byte handling
below never runs on cart.
"""

MASK32 = 0xFFFFFFFF

C_ROUNDS = 2
D_ROUNDS = 4


def _rotl(x: int, b: int) -> int:
    return ((x << b) | (x >> (32 - b))) & MASK32


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def halfsiphash(data: bytes, key: bytes, outlen: int = 4) -> bytes:
    """
    Compute HalfSipHash-2-4 over `data` with an 8-byte `key`.

    Args:
        data: message bytes
        key: 8-byte key
        outlen: 4 or 8 output bytes

    Returns:
        `outlen` bytes, little-endian
    """
    if len(key) != 8:
        raise ValueError(f"key must be 8 bytes, got {len(key)}")
    if outlen not in (4, 8):
        raise ValueError(f"outlen must be 4 or 8, got {outlen}")

    k0 = _u32(key, 0)
    k1 = _u32(key, 4)

    v0 = 0
    v1 = 0
    v2 = 0x6C796765
    v3 = 0x74656462

    v3 ^= k1
    v2 ^= k0
    v1 ^= k1
    v0 ^= k0

    if outlen == 8:
        v1 ^= 0xEE

    def sipround() -> None:
        nonlocal v0, v1, v2, v3
        v0 = (v0 + v1) & MASK32
        v1 = _rotl(v1, 5)
        v1 ^= v0
        v0 = _rotl(v0, 16)
        v2 = (v2 + v3) & MASK32
        v3 = _rotl(v3, 8)
        v3 ^= v2
        v0 = (v0 + v3) & MASK32
        v3 = _rotl(v3, 7)
        v3 ^= v0
        v2 = (v2 + v1) & MASK32
        v1 = _rotl(v1, 13)
        v1 ^= v2
        v2 = _rotl(v2, 16)

    inlen = len(data)
    whole = inlen - (inlen % 4)

    for offset in range(0, whole, 4):
        m = _u32(data, offset)
        v3 ^= m
        for _ in range(C_ROUNDS):
            sipround()
        v0 ^= m

    # Tail: remaining 0-3 bytes, with the message length in the top byte.
    b = (inlen & MASK32) << 24 & MASK32
    left = inlen & 3
    if left >= 3:
        b |= data[whole + 2] << 16
    if left >= 2:
        b |= data[whole + 1] << 8
    if left >= 1:
        b |= data[whole]

    v3 ^= b
    for _ in range(C_ROUNDS):
        sipround()
    v0 ^= b

    v2 ^= 0xEE if outlen == 8 else 0xFF
    for _ in range(D_ROUNDS):
        sipround()

    out = ((v1 ^ v3) & MASK32).to_bytes(4, "little")
    if outlen == 4:
        return out

    v1 ^= 0xDD
    for _ in range(D_ROUNDS):
        sipround()
    return out + ((v1 ^ v3) & MASK32).to_bytes(4, "little")
