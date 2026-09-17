"""
GF(256) arithmetic for Reed-Solomon, in the field QR codes use.

Primitive polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11D), generator element 2.
The antilog/log tables built here are exactly the 512 bytes the 6502 port
carries in ROM, and `generator_poly` produces the 25-byte coefficient table
for the 24 EC code words version 5-M needs.
"""

PRIMITIVE = 0x11D
FIELD_SIZE = 256


def _build_tables() -> tuple[list[int], list[int]]:
    exp = [0] * 512
    log = [0] * FIELD_SIZE
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= PRIMITIVE
    # Duplicate so exp[a + b] needs no modulo for a, b < 255.
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


EXP, LOG = _build_tables()

#: Antilog table as the ROM carries it: 256 bytes, index = exponent.
ANTILOG_TABLE = bytes(EXP[:256])
#: Log table as the ROM carries it: 256 bytes, index = field element.
#: `LOG[0]` is undefined in the field; it is never read because multiply
#: short-circuits on a zero operand.
LOG_TABLE = bytes(LOG)


def multiply(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def _poly_multiply(a: list[int], b: list[int]) -> list[int]:
    """Multiply two polynomials given lowest-power-first."""
    out = [0] * (len(a) + len(b) - 1)
    for i, ai in enumerate(a):
        if ai:
            for j, bj in enumerate(b):
                if bj:
                    out[i + j] ^= multiply(ai, bj)
    return out


def generator_poly(degree: int) -> list[int]:
    """
    Coefficients of (x - 2^0)(x - 2^1)...(x - 2^(degree-1)), highest power
    first, with the leading 1 included — so the result is `degree + 1` long.
    """
    poly = [1]
    for i in range(degree):
        # In GF(256) subtraction is XOR, so (x - 2^i) is (x + 2^i).
        poly = _poly_multiply(poly, [EXP[i], 1])
    return poly[::-1]


def reed_solomon(data: bytes, ec_count: int) -> bytes:
    """
    Compute `ec_count` Reed-Solomon error correction code words for `data`.

    This is the LFSR formulation the 6502 uses: keep a remainder register
    `ec_count` bytes wide, and for each data byte take the feedback term,
    shift, and XOR in the generator polynomial scaled by that term.
    """
    gen = generator_poly(ec_count)[1:]  # drop the leading 1
    remainder = [0] * ec_count
    for byte in data:
        factor = byte ^ remainder[0]
        remainder = remainder[1:] + [0]
        if factor:
            log_factor = LOG[factor]
            for i, coefficient in enumerate(gen):
                if coefficient:
                    remainder[i] ^= EXP[LOG[coefficient] + log_factor]
    return bytes(remainder)
