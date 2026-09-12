"""
The ROM tables the 6502 QR generator carries, exported from the oracle.

Phase 3 of `docs/scorecard_qr.md`. Everything here is *derived* from the
reference implementation rather than transcribed alongside it: the static
matrix comes out of `encoder.build_static_matrix`, the GF tables out of
`galois`, the constant code word head out of `encoder.data_codewords` run on a
dummy URL. A change to the encoder therefore changes the exported tables, and
cannot leave the ROM carrying a stale copy.

Seven tables, 2,329 bytes, in the blob order below:

    QrAntilogTable      256   GF(256) antilog, index = exponent
    QrLogTable          256   GF(256) log, index = field element
    QrChrTiles          256   the 16 QR CHR tiles
    QrBase64Alphabet     64   base64url, index order
    QrCodewordHead       28   data code words 0-27, invariant across payloads
    QrGeneratorPoly      25   RS generator for 24 EC code words
    QrStaticMatrix    1,444   function patterns + format info + mask, 38x38

The two 256-byte GF tables lead so that a page-aligned blob origin makes both
of them page-aligned, which is the one layout constraint the 6502 side cares
about. `layout()` reports whether that actually held.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from golf.qr import nes
from golf.qr.encoder import (
    DATA_CODEWORDS,
    EC_PER_BLOCK,
    FREE,
    MASK_PREDICATES,
    SIZE,
    build_static_matrix,
    data_codewords,
)
from golf.qr.galois import ANTILOG_TABLE, LOG_TABLE, generator_poly
from golf.qr.payload import B64_ALPHABET, PROTOCOL_VERSION, URL_LEN, URL_PREFIX
from golf.qr.submission import FIXED_MASK

#: Data code words 0-27 do not depend on the payload: code words 0-26 and the
#: top nibble of 27 come from the 26-character URL prefix, and the rest of 27
#: plus the top of 28 come from the first base64 character, which is always
#: `A` because it carries the top six bits of the protocol version byte.
CONSTANT_CODEWORDS = 28

#: The static matrix's shape on cart: 37 modules plus a row and column of
#: padding, so the grid is even and the tile builder needs no bounds tests.
ROM_MATRIX_STRIDE = 38
ROM_MATRIX_ROWS = 38

#: Free-module sentinels in the ROM table, carrying the mask bit in bit 0.
FREE_MASK_ON = 0xFF
FREE_MASK_OFF = 0xFE

#: Free bytes in the region this feature lives in — bank 2, `$837F`-`$A553`
#: (see `docs/terrain_data_locations.md`). Reported so the export says how much
#: of the budget the tables alone consume.
REGION_BYTES = 8661

#: Bytes per `.byte` line in the assembler output, for the flat tables. The
#: static matrix uses one line per QR row instead.
ASM_BYTES_PER_LINE = 16


@dataclass(frozen=True)
class RomTable:
    """One table as the ROM carries it."""

    name: str
    label: str
    description: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


# --------------------------------------------------------------------------
# The tables
# --------------------------------------------------------------------------


def static_matrix_table(mask: int = FIXED_MASK) -> bytes:
    """
    The function-pattern layer in the shape the ROM uses it: a 38x38 grid the
    walker copies to RAM verbatim and then fills in.

    Two differences from `encoder.build_static_matrix`, both of which buy code
    on the 6502 side:

    * **The mask is baked into the free cells.** A free module is `$FF` where
      the mask inverts it and `$FE` where it does not, so the walker places a
      bit with `cell & 1` xor the data bit and never evaluates a mask
      predicate. Fixed modules stay `$00` light / `$01` dark, and `cell >= $FE`
      is the whole free-module test.
    * **One row and one column of padding**, `$00`, so 37 (odd) becomes an even
      38. The tile builder reads 2x2 blocks of modules with no bounds checks,
      and the walker's vertical step is a constant 38.
    """
    reference = build_static_matrix(mask)
    predicate = MASK_PREDICATES[mask]
    out = bytearray(ROM_MATRIX_STRIDE * ROM_MATRIX_ROWS)
    for row in range(SIZE):
        for col in range(SIZE):
            cell = reference[row * SIZE + col]
            if cell == FREE:
                cell = FREE_MASK_ON if predicate(row, col) else FREE_MASK_OFF
            out[row * ROM_MATRIX_STRIDE + col] = cell
    return bytes(out)


def antilog_table() -> bytes:
    """GF(256) antilog, 256 bytes, index = exponent."""
    return ANTILOG_TABLE


def log_table() -> bytes:
    """
    GF(256) log, 256 bytes, index = field element.

    Entry 0 is undefined in the field and is never read: multiply
    short-circuits on a zero operand.
    """
    return LOG_TABLE


def generator_table() -> bytes:
    """
    The Reed-Solomon generator polynomial for 24 EC code words, highest power
    first, 25 bytes.

    Byte 0 is the leading coefficient (always 1); the LFSR in the ROM consumes
    bytes 1-24 in order, one per remainder register byte.
    """
    poly = bytes(generator_poly(EC_PER_BLOCK))
    if poly[0] != 1 or 0 in poly:
        raise ValueError(f"unexpected generator polynomial {poly.hex()}")
    return poly


def chr_table() -> bytes:
    """The 16 QR CHR tiles, 256 bytes, tile n holding quadrant pattern n."""
    return nes.build_chr()


def base64_alphabet_table() -> bytes:
    """The base64url alphabet in index order, 64 bytes."""
    alphabet = B64_ALPHABET.encode("ascii")
    if len(alphabet) != 64 or len(set(alphabet)) != 64:
        raise ValueError("base64url alphabet must be 64 distinct characters")
    return alphabet


def _dummy_url(filler: str) -> bytes:
    """
    A full-length URL whose only fixed part is what the ROM can rely on: the
    prefix and the always-`A` first base64 character.
    """
    tail = filler * (URL_LEN - len(URL_PREFIX) - 1)
    return (URL_PREFIX + "A" + tail).encode("ascii")


def codeword_head() -> bytes:
    """
    Data code words 0-27, which are the same for every payload.

    Derived by encoding two URLs that differ in every variable character and
    taking what they agree on, so the length is checked rather than assumed:
    the code word just past the head must differ between the two.
    """
    if PROTOCOL_VERSION >> 2:
        raise ValueError(
            f"protocol version {PROTOCOL_VERSION} does not leave the first "
            "base64 character constant; the code word head is no longer fixed"
        )
    first = data_codewords(_dummy_url("B"))
    second = data_codewords(_dummy_url("_"))
    head = first[:CONSTANT_CODEWORDS]
    if head != second[:CONSTANT_CODEWORDS]:
        raise ValueError("code words 0-27 are not invariant")
    if first[CONSTANT_CODEWORDS] == second[CONSTANT_CODEWORDS]:
        raise ValueError("the invariant code word head is longer than expected")
    return head


def build_tables(mask: int = FIXED_MASK) -> tuple[RomTable, ...]:
    """Every ROM table, in blob order."""
    return (
        RomTable(
            name="antilog",
            label="QrAntilogTable",
            description="GF(256) antilog, index = exponent",
            data=antilog_table(),
        ),
        RomTable(
            name="log",
            label="QrLogTable",
            description="GF(256) log, index = field element (entry 0 unused)",
            data=log_table(),
        ),
        RomTable(
            name="chr",
            label="QrChrTiles",
            description="16 QR CHR tiles, 2x2 modules each, plane 1 empty",
            data=chr_table(),
        ),
        RomTable(
            name="base64",
            label="QrBase64Alphabet",
            description="base64url alphabet, index order",
            data=base64_alphabet_table(),
        ),
        RomTable(
            name="codeword_head",
            label="QrCodewordHead",
            description=f"data code words 0-{CONSTANT_CODEWORDS - 1}, payload-invariant",
            data=codeword_head(),
        ),
        RomTable(
            name="generator",
            label="QrGeneratorPoly",
            description=(
                f"RS generator for {EC_PER_BLOCK} EC code words, highest power "
                "first; the LFSR reads bytes 1-24"
            ),
            data=generator_table(),
        ),
        RomTable(
            name="static_matrix",
            label="QrStaticMatrix",
            description=(
                f"{ROM_MATRIX_ROWS}x{ROM_MATRIX_STRIDE} function patterns and "
                f"format info, mask {mask} baked in: $00 light, $01 dark, "
                f"${FREE_MASK_OFF:02X}/${FREE_MASK_ON:02X} free with the mask "
                "bit in bit 0"
            ),
            data=static_matrix_table(mask),
        ),
    )


# --------------------------------------------------------------------------
# Layout, blob, manifest
# --------------------------------------------------------------------------


def blob(tables: tuple[RomTable, ...]) -> bytes:
    """The tables concatenated, in order, with no padding."""
    return b"".join(table.data for table in tables)


@dataclass(frozen=True)
class Placement:
    """Where one table sits in the blob, and at what CPU address."""

    table: RomTable
    offset: int
    address: int | None = None

    @property
    def page_aligned(self) -> bool | None:
        """
        Whether the table starts on a page boundary — what the 6502 cares
        about for the two 256-byte GF tables, which are indexed on their
        whole range. `None` when no origin was given.
        """
        return None if self.address is None else self.address % 0x100 == 0

    @property
    def address_hex(self) -> str | None:
        return None if self.address is None else f"${self.address:04X}"

    def to_dict(self) -> dict[str, object]:
        entry: dict[str, object] = {
            "name": self.table.name,
            "label": self.table.label,
            "description": self.table.description,
            "size": self.table.size,
            "offset": self.offset,
            "sha256": self.table.sha256,
        }
        if self.address is not None:
            entry["address"] = self.address
            entry["address_hex"] = self.address_hex
            entry["page_aligned"] = self.page_aligned
        return entry


def layout(
    tables: tuple[RomTable, ...], origin: int | None = None
) -> tuple[Placement, ...]:
    """Per-table placement within the blob, with CPU addresses if given."""
    out = []
    offset = 0
    for table in tables:
        out.append(
            Placement(
                table=table,
                offset=offset,
                address=None if origin is None else origin + offset,
            )
        )
        offset += table.size
    return tuple(out)


def manifest(
    tables: tuple[RomTable, ...],
    mask: int = FIXED_MASK,
    origin: int | None = None,
) -> dict[str, object]:
    """Everything a consumer needs to place and check the blob."""
    data = blob(tables)
    return {
        "tool": "golf-qr-tables",
        "source": "golf.qr.tables",
        "mask": mask,
        "url_prefix": URL_PREFIX,
        "url_length": URL_LEN,
        "protocol_version": PROTOCOL_VERSION,
        "data_codewords": DATA_CODEWORDS,
        "ec_codewords_per_block": EC_PER_BLOCK,
        "matrix_size": SIZE,
        "free_module_sentinels": [FREE_MASK_OFF, FREE_MASK_ON],
        "matrix_stride": ROM_MATRIX_STRIDE,
        "matrix_rows": ROM_MATRIX_ROWS,
        "total_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "region_bytes": REGION_BYTES,
        "region_remaining": REGION_BYTES - len(data),
        "origin": origin,
        "origin_hex": None if origin is None else f"${origin:04X}",
        "tables": [placement.to_dict() for placement in layout(tables, origin)],
    }


# --------------------------------------------------------------------------
# Assembler output
# --------------------------------------------------------------------------


def _byte_lines(data: bytes, per_line: int) -> list[str]:
    return [
        "    .byte " + ",".join(f"${b:02X}" for b in data[i : i + per_line])
        for i in range(0, len(data), per_line)
    ]


def _table_asm(table: RomTable) -> list[str]:
    lines = [f"; {table.description}", f"; {table.size} bytes", f"{table.label}:"]
    if table.name == "static_matrix":
        # One grid row per line, so the table reads as the picture it is.
        lines += _byte_lines(table.data, ROM_MATRIX_STRIDE)
    else:
        lines += _byte_lines(table.data, ASM_BYTES_PER_LINE)
    lines.append(f"{table.label}End:")
    return lines


def to_asm(
    tables: tuple[RomTable, ...],
    mask: int = FIXED_MASK,
    origin: int | None = None,
) -> str:
    """
    The tables as `.byte` directives with one label per table (and a matching
    `...End` label), preceded by a header of the constants they were built
    from. Deliberately free of timestamps so the output is reproducible and
    diffable.
    """
    data = blob(tables)
    header = [
        "; QR scorecard submission tables - generated by golf-qr-tables.",
        "; Do not edit: regenerate from golf/qr/tables.py.",
        ";",
        f"; mask            {mask}",
        f"; url prefix      {URL_PREFIX}",
        f"; url length      {URL_LEN}",
        f"; total bytes     {len(data)}",
        f"; sha256          {hashlib.sha256(data).hexdigest()}",
    ]
    if origin is not None:
        header.append(f"; origin          ${origin:04X}")
    header.append(";")
    header.append("; offset  size  label")
    width = max(len(table.label) for table in tables)
    for placement in layout(tables, origin):
        address = "" if placement.address_hex is None else f"  {placement.address_hex}"
        header.append(
            f";  ${placement.offset:04X}  {placement.table.size:5d}"
            f"  {placement.table.label:<{width}}{address}"
        )

    lines = header + [""]
    if origin is not None:
        lines += [f"    .org ${origin:04X}", ""]
    for table in tables:
        lines += _table_asm(table) + [""]

    text = "\n".join(lines).rstrip("\n") + "\n"
    if not text.isascii():
        raise ValueError("assembler output must stay ASCII")
    return text


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def write_tables(
    out_dir: Path,
    tables: tuple[RomTable, ...],
    mask: int = FIXED_MASK,
    origin: int | None = None,
    split: bool = True,
) -> list[Path]:
    """
    Write `qr_tables.bin`, `qr_tables.inc`, `qr_tables.json` and (by default)
    one `.bin` per table. Returns the paths written, in order.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    blob_path = out_dir / "qr_tables.bin"
    blob_path.write_bytes(blob(tables))
    written.append(blob_path)

    asm_path = out_dir / "qr_tables.inc"
    asm_path.write_text(to_asm(tables, mask, origin))
    written.append(asm_path)

    json_path = out_dir / "qr_tables.json"
    json_path.write_text(json.dumps(manifest(tables, mask, origin), indent=2) + "\n")
    written.append(json_path)

    if split:
        for table in tables:
            path = out_dir / f"{table.name}.bin"
            path.write_bytes(table.data)
            written.append(path)

    return written
