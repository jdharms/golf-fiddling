"""
QR version 5, error correction level M, byte mode encoder.

Deliberately hard-wired to one version and one EC level: that is what the ROM
will implement, and every constant below is something the 6502 port bakes in.
Stages are exposed individually (`encode_stages`) so the port can be
differentially tested one stage at a time rather than only on the final matrix.

See `docs/scorecard_qr.md` for where each constant comes from.
"""

from dataclasses import dataclass
from functools import lru_cache

from golf.qr.galois import reed_solomon

VERSION = 5
SIZE = 4 * VERSION + 17  # 37

#: Error correction level M, as the format-information field encodes it.
EC_LEVEL_FORMAT_BITS = 0b00

TOTAL_CODEWORDS = 134
DATA_CODEWORDS = 86
NUM_BLOCKS = 2
DATA_PER_BLOCK = 43
EC_PER_BLOCK = 24

#: Data-region modules, i.e. everything that is not a function pattern.
FREE_MODULES = 1079
FUNCTION_MODULES = SIZE * SIZE - FREE_MODULES  # 290
REMAINDER_BITS = FREE_MODULES - TOTAL_CODEWORDS * 8  # 7

#: Longest byte-mode payload that fits.
MAX_CHARS = 84

#: Byte mode indicator, and the character-count field width for versions 1-9.
MODE_BYTE = 0b0100
COUNT_BITS = 8

PAD_CODEWORDS = (0xEC, 0x11)

#: Sentinel for "free data module" in a static matrix.
FREE = 0xFF

#: Alignment pattern centre coordinates for version 5.
ALIGNMENT_COORDS = (6, 30)


class QrMatrix:
    """A finished 37x37 module matrix. 1 is dark, 0 is light."""

    __slots__ = ("modules", "mask", "size")

    def __init__(self, modules: bytearray, mask: int, size: int = SIZE) -> None:
        self.modules = modules
        self.mask = mask
        self.size = size

    def get(self, row: int, col: int) -> int:
        if not (0 <= row < self.size and 0 <= col < self.size):
            return 0
        return self.modules[row * self.size + col]

    def rows(self) -> list[list[int]]:
        return [
            list(self.modules[r * self.size : (r + 1) * self.size])
            for r in range(self.size)
        ]

    @property
    def dark_count(self) -> int:
        return sum(self.modules)

    def to_text(self, dark: str = "##", light: str = "  ") -> str:
        return "\n".join(
            "".join(dark if m else light for m in row) for row in self.rows()
        )


@dataclass(frozen=True)
class Stages:
    """Every intermediate the 6502 port can be checked against."""

    text: bytes
    mask: int
    data_codewords: bytes
    ec_codewords: tuple[bytes, ...]
    interleaved: bytes
    static_matrix: bytes
    walk_order: tuple[int, ...]
    matrix: QrMatrix


# --------------------------------------------------------------------------
# Stage 1: data code words
# --------------------------------------------------------------------------


def data_codewords(text: bytes) -> bytes:
    """
    Build the 86 data code words for a byte-mode payload.

    Written as the nibble-shift loop the 6502 uses rather than as a general
    bit packer: the 12-bit header (4-bit mode + 8-bit count) leaves every
    payload byte straddling two code words at a nibble boundary.
    `_data_codewords_bitwise` is the independent check on this.
    """
    n = len(text)
    if n > MAX_CHARS:
        raise ValueError(
            f"payload of {n} chars exceeds version 5-M capacity {MAX_CHARS}"
        )

    out = bytearray()
    out.append((MODE_BYTE << 4) | (n >> 4))
    carry = n & 0x0F
    for ch in text:
        out.append((carry << 4) | (ch >> 4))
        carry = ch & 0x0F
    # 4-bit terminator lands in the low nibble, leaving us byte-aligned.
    out.append(carry << 4)

    for i in range(DATA_CODEWORDS - len(out)):
        out.append(PAD_CODEWORDS[i & 1])
    assert len(out) == DATA_CODEWORDS, len(out)
    return bytes(out)


def _data_codewords_bitwise(text: bytes) -> bytes:
    """General bit-packing implementation, used only to verify the fast path."""
    bits: list[int] = []

    def push(value: int, width: int) -> None:
        for i in range(width - 1, -1, -1):
            bits.append((value >> i) & 1)

    capacity = DATA_CODEWORDS * 8
    push(MODE_BYTE, 4)
    push(len(text), COUNT_BITS)
    for ch in text:
        push(ch, 8)
    push(0, min(4, capacity - len(bits)))
    while len(bits) % 8:
        bits.append(0)

    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for bit in bits[i : i + 8]:
            byte = (byte << 1) | bit
        out.append(byte)
    for i in range(DATA_CODEWORDS - len(out)):
        out.append(PAD_CODEWORDS[i & 1])
    return bytes(out)


# --------------------------------------------------------------------------
# Stage 2: error correction and interleaving
# --------------------------------------------------------------------------


def ec_codewords(data: bytes) -> tuple[bytes, ...]:
    if len(data) != DATA_CODEWORDS:
        raise ValueError(f"expected {DATA_CODEWORDS} data code words, got {len(data)}")
    return tuple(
        reed_solomon(data[i * DATA_PER_BLOCK : (i + 1) * DATA_PER_BLOCK], EC_PER_BLOCK)
        for i in range(NUM_BLOCKS)
    )


def interleave(data: bytes, ec: tuple[bytes, ...]) -> bytes:
    """
    Interleave the two blocks. Both blocks are the same length in 5-M, so this
    is a plain alternating copy with no ragged-block handling.
    """
    out = bytearray()
    for i in range(DATA_PER_BLOCK):
        for block in range(NUM_BLOCKS):
            out.append(data[block * DATA_PER_BLOCK + i])
    for i in range(EC_PER_BLOCK):
        for block in range(NUM_BLOCKS):
            out.append(ec[block][i])
    assert len(out) == TOTAL_CODEWORDS, len(out)
    return bytes(out)


# --------------------------------------------------------------------------
# Stage 3: the static matrix (function patterns + format information)
# --------------------------------------------------------------------------


def format_bits(mask: int) -> int:
    """The 15-bit format information field for level M and the given mask."""
    if not 0 <= mask <= 7:
        raise ValueError(f"mask must be 0-7, got {mask}")
    data = (EC_LEVEL_FORMAT_BITS << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


@lru_cache(maxsize=8)
def build_static_matrix(mask: int) -> bytes:
    """
    The function-pattern layer, one byte per module: 0 light, 1 dark, and
    `FREE` ($FF) for a data module. The mask's format-information bits are
    baked in, which is what lets the ROM carry this as a single flat table.
    """
    matrix = bytearray([FREE]) * (SIZE * SIZE)

    def put(row: int, col: int, dark: int) -> None:
        matrix[row * SIZE + col] = 1 if dark else 0

    # Timing patterns first; the finders overwrite their ends.
    for i in range(SIZE):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)

    # Finder patterns, drawn 9x9 so the separators come along for free.
    # Chebyshev distance from the centre: 0-1 is the dark core, 2 the light
    # ring, 3 the dark ring, 4 the light separator.
    for centre_row, centre_col in ((3, 3), (3, SIZE - 4), (SIZE - 4, 3)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                row, col = centre_row + dy, centre_col + dx
                if 0 <= row < SIZE and 0 <= col < SIZE:
                    distance = max(abs(dx), abs(dy))
                    put(row, col, distance not in (2, 4))

    # Alignment patterns, minus the three that collide with the finders.
    for centre_row in ALIGNMENT_COORDS:
        for centre_col in ALIGNMENT_COORDS:
            if (centre_row, centre_col) in (
                (ALIGNMENT_COORDS[0], ALIGNMENT_COORDS[0]),
                (ALIGNMENT_COORDS[0], ALIGNMENT_COORDS[-1]),
                (ALIGNMENT_COORDS[-1], ALIGNMENT_COORDS[0]),
            ):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(centre_row + dy, centre_col + dx, max(abs(dx), abs(dy)) != 1)

    # Format information, both copies.
    bits = format_bits(mask)

    def bit(i: int) -> int:
        return (bits >> i) & 1

    for i in range(6):
        put(i, 8, bit(i))
    put(7, 8, bit(6))
    put(8, 8, bit(7))
    put(8, 7, bit(8))
    for i in range(9, 15):
        put(8, 14 - i, bit(i))

    # The second copy runs the other way round: bits 14-8 climb col 8 from the
    # bottom edge, bits 7-0 run right along row 8, with the always-dark module
    # wedged between the two runs.
    for i in range(7):
        put(SIZE - 1 - i, 8, bit(14 - i))
    for i in range(8):
        put(8, SIZE - 8 + i, bit(7 - i))

    # The always-dark module, at (4 * version + 9, 8).
    put(SIZE - 8, 8, 1)

    function_count = sum(1 for m in matrix if m != FREE)
    assert function_count == FUNCTION_MODULES, function_count
    return bytes(matrix)


# --------------------------------------------------------------------------
# Stage 4: placement
# --------------------------------------------------------------------------


@lru_cache(maxsize=8)
def walk_order(static_matrix: bytes) -> tuple[int, ...]:
    """
    Flat module indices in placement order: column pairs right to left,
    skipping the vertical timing pattern, alternating upward and downward,
    right column before left within a pair, function modules skipped.

    Identical for every mask (the function-pattern *layout* does not depend on
    the mask, only the format bits' values do), so the ROM can treat this as a
    property of the static table.
    """
    order: list[int] = []
    right = SIZE - 1
    while right >= 1:
        if right == 6:
            right = 5
        upward = ((right + 1) & 2) == 0
        for vert in range(SIZE):
            for j in range(2):
                col = right - j
                row = (SIZE - 1 - vert) if upward else vert
                index = row * SIZE + col
                if static_matrix[index] == FREE:
                    order.append(index)
        right -= 2
    assert len(order) == FREE_MODULES, len(order)
    return tuple(order)


#: The eight mask predicates, by mask number: True means the module is
#: inverted. Public because the ROM table bakes the chosen one in (see
#: `golf.qr.tables`).
MASK_PREDICATES = (
    lambda row, col: (row + col) % 2 == 0,
    lambda row, col: row % 2 == 0,
    lambda row, col: col % 3 == 0,
    lambda row, col: (row + col) % 3 == 0,
    lambda row, col: (row // 2 + col // 3) % 2 == 0,
    lambda row, col: (row * col) % 2 + (row * col) % 3 == 0,
    lambda row, col: ((row * col) % 2 + (row * col) % 3) % 2 == 0,
    lambda row, col: ((row + col) % 2 + (row * col) % 3) % 2 == 0,
)


def place(codewords: bytes, static_matrix: bytes, mask: int) -> QrMatrix:
    """
    Walk the data region, placing code word bits and applying the mask as it
    goes. The 7 remainder bits past the last code word stay light before
    masking, as the spec requires.
    """
    if len(codewords) != TOTAL_CODEWORDS:
        raise ValueError(f"expected {TOTAL_CODEWORDS} code words, got {len(codewords)}")

    modules = bytearray(1 if m == 1 else 0 for m in static_matrix)
    predicate = MASK_PREDICATES[mask]
    total_bits = TOTAL_CODEWORDS * 8

    for bit_index, index in enumerate(walk_order(static_matrix)):
        if bit_index < total_bits:
            byte = codewords[bit_index >> 3]
            value = (byte >> (7 - (bit_index & 7))) & 1
        else:
            value = 0
        row, col = divmod(index, SIZE)
        if predicate(row, col):
            value ^= 1
        modules[index] = value

    return QrMatrix(modules, mask)


# --------------------------------------------------------------------------
# Top level
# --------------------------------------------------------------------------


def encode_stages(text: str | bytes, mask: int) -> Stages:
    raw = text.encode("ascii") if isinstance(text, str) else bytes(text)
    data = data_codewords(raw)
    ec = ec_codewords(data)
    codewords = interleave(data, ec)
    static = build_static_matrix(mask)
    return Stages(
        text=raw,
        mask=mask,
        data_codewords=data,
        ec_codewords=ec,
        interleaved=codewords,
        static_matrix=static,
        walk_order=walk_order(static),
        matrix=place(codewords, static, mask),
    )


def encode(text: str | bytes, mask: int) -> QrMatrix:
    return encode_stages(text, mask).matrix


# --------------------------------------------------------------------------
# Mask penalty scoring
#
# Advisory only: the ROM uses a fixed mask. This exists so the validation
# harness can report which mask the spec would have chosen, and how far the
# fixed one is from it.
# --------------------------------------------------------------------------

_FINDER_PATTERNS = (
    (1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0),
    (0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1),
)


def _penalty_runs(lines: list[list[int]]) -> int:
    total = 0
    for line in lines:
        run_value = line[0]
        run_length = 1
        for module in line[1:]:
            if module == run_value:
                run_length += 1
            else:
                if run_length >= 5:
                    total += 3 + (run_length - 5)
                run_value = module
                run_length = 1
        if run_length >= 5:
            total += 3 + (run_length - 5)
    return total


def _penalty_finders(lines: list[list[int]]) -> int:
    total = 0
    width = len(_FINDER_PATTERNS[0])
    for line in lines:
        for i in range(len(line) - width + 1):
            window = tuple(line[i : i + width])
            if window in _FINDER_PATTERNS:
                total += 40
    return total


def penalty(matrix: QrMatrix) -> int:
    rows = matrix.rows()
    cols = [list(col) for col in zip(*rows, strict=True)]

    score = _penalty_runs(rows) + _penalty_runs(cols)

    for r in range(matrix.size - 1):
        for c in range(matrix.size - 1):
            block = (rows[r][c], rows[r][c + 1], rows[r + 1][c], rows[r + 1][c + 1])
            if block[0] == block[1] == block[2] == block[3]:
                score += 3

    score += _penalty_finders(rows) + _penalty_finders(cols)

    dark_ratio = matrix.dark_count * 100 / (matrix.size * matrix.size)
    score += 10 * (int(abs(dark_ratio - 50)) // 5)

    return score


def best_mask(text: str | bytes) -> int:
    """The mask the spec would choose. Reference only; the ROM is fixed-mask."""
    return min(range(8), key=lambda mask: penalty(encode(text, mask)))
