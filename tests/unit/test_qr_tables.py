"""
The exported ROM tables, checked against something other than the code that
built them.

The point of the export is that the ROM cannot drift from the oracle, so a
test that merely re-calls the exporter proves nothing. Each table is verified
against an independent property instead: the GF tables against carry-less
multiplication done longhand, the generator polynomial against its own roots,
the static matrix module-for-module against `qrcode`, the CHR against the
decoded pixels, the code word head against real encoded payloads.
"""

import json
import random

import pytest
import qrcode
from qrcode.constants import ERROR_CORRECT_M

from golf.qr import encoder, nes, sample, tables
from golf.qr.galois import PRIMITIVE, multiply
from golf.qr.payload import URL_PREFIX, base64url_encode
from golf.qr.submission import FIXED_MASK

#: Sizes as `docs/scorecard_qr.md` records them in the ROM budget.
EXPECTED_SIZES = {
    "antilog": 256,
    "log": 256,
    "chr": 256,
    "base64": 64,
    "codeword_head": 28,
    "generator": 25,
    "static_matrix": 1444,
}
EXPECTED_TOTAL = 2329


@pytest.fixture(scope="module")
def built() -> tuple[tables.RomTable, ...]:
    return tables.build_tables()


@pytest.fixture(scope="module")
def by_name(built) -> dict[str, tables.RomTable]:
    return {table.name: table for table in built}


@pytest.fixture(scope="module")
def urls() -> list[str]:
    rng = random.Random(31337)
    key = sample.random_key(rng)
    return [sample.random_round(rng).to_url(key) for _ in range(16)]


# --------------------------------------------------------------------------
# Sizes and identity
# --------------------------------------------------------------------------


def test_every_table_is_the_documented_size(by_name) -> None:
    assert {name: table.size for name, table in by_name.items()} == EXPECTED_SIZES


def test_total_matches_the_documented_budget(built) -> None:
    assert len(tables.blob(built)) == EXPECTED_TOTAL
    assert sum(EXPECTED_SIZES.values()) == EXPECTED_TOTAL


def test_tables_have_distinct_names_and_labels(built) -> None:
    assert len({table.name for table in built}) == len(built)
    assert len({table.label for table in built}) == len(built)
    for table in built:
        assert table.description


def test_tables_fit_the_region_with_room_for_code(built) -> None:
    remaining = tables.REGION_BYTES - EXPECTED_TOTAL
    assert tables.manifest(built)["region_remaining"] == remaining
    assert remaining > 4000  # the ROM budget's estimate for the code itself


def test_export_is_deterministic() -> None:
    assert tables.blob(tables.build_tables()) == tables.blob(tables.build_tables())


# --------------------------------------------------------------------------
# GF(256) tables
# --------------------------------------------------------------------------


def _carryless_multiply(a: int, b: int) -> int:
    """GF(256) multiplication done longhand, independent of any table."""
    result = 0
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a & 0x100:
            a ^= PRIMITIVE
    return result


def test_gf_tables_invert_each_other(by_name) -> None:
    antilog = by_name["antilog"].data
    log = by_name["log"].data
    assert antilog[0] == 1
    for exponent in range(255):
        assert log[antilog[exponent]] == exponent
    for value in range(1, 256):
        assert antilog[log[value]] == value


def test_gf_tables_reproduce_longhand_multiplication(by_name) -> None:
    antilog = by_name["antilog"].data
    log = by_name["log"].data
    for a in range(1, 256):
        for b in (1, 2, 3, 5, 27, 100, 199, 255):
            # The ROM's multiply: antilog[log a + log b], summed mod 255.
            expected = _carryless_multiply(a, b)
            assert antilog[(log[a] + log[b]) % 255] == expected
            assert multiply(a, b) == expected


def test_generator_polynomial_has_the_right_roots(by_name) -> None:
    """
    The generator for n EC code words is the product of (x - 2^i) for
    i = 0..n-1, so evaluating it at each of those points must give zero.
    """
    poly = by_name["generator"].data
    assert len(poly) == encoder.EC_PER_BLOCK + 1
    assert poly[0] == 1
    antilog = by_name["antilog"].data
    for i in range(encoder.EC_PER_BLOCK):
        root = antilog[i]
        value = 0
        for coefficient in poly:  # Horner, highest power first
            value = _carryless_multiply(value, root) ^ coefficient
        assert value == 0, f"2^{i} is not a root"


def test_generator_table_drives_the_rom_lfsr(by_name, urls) -> None:
    """
    The EC stage the 6502 runs, written against the exported bytes only, must
    match the reference encoder's output.
    """
    antilog = by_name["antilog"].data
    log = by_name["log"].data
    gen = by_name["generator"].data[1:]

    def ec(block: bytes) -> bytes:
        remainder = [0] * encoder.EC_PER_BLOCK
        for byte in block:
            factor = byte ^ remainder[0]
            remainder = remainder[1:] + [0]
            if factor:
                log_factor = log[factor]
                for i, coefficient in enumerate(gen):
                    remainder[i] ^= antilog[(log[coefficient] + log_factor) % 255]
        return bytes(remainder)

    for url in urls:
        data = encoder.data_codewords(url.encode())
        blocks = [
            data[i * encoder.DATA_PER_BLOCK : (i + 1) * encoder.DATA_PER_BLOCK]
            for i in range(encoder.NUM_BLOCKS)
        ]
        assert tuple(ec(block) for block in blocks) == encoder.ec_codewords(data)


# --------------------------------------------------------------------------
# Static matrix
# --------------------------------------------------------------------------


def _reference_matrix(text: str, mask: int) -> list[list[int]]:
    code = qrcode.QRCode(
        version=encoder.VERSION,
        error_correction=ERROR_CORRECT_M,
        border=0,
        mask_pattern=mask,
    )
    code.add_data(text, optimize=0)
    code.make(fit=False)
    return [[1 if value else 0 for value in row] for row in code.modules]


def _cell(data: bytes, row: int, col: int) -> int:
    return data[row * tables.ROM_MATRIX_STRIDE + col]


@pytest.mark.parametrize("mask", range(8))
def test_static_matrix_function_modules_match_an_independent_encoder(
    mask: int, urls
) -> None:
    """
    Every fixed cell — finders, separators, timing, alignment, dark module and
    both copies of the format information — must agree with `qrcode`.
    """
    static = tables.static_matrix_table(mask)
    reference = _reference_matrix(urls[0], mask)
    free = 0
    for row in range(encoder.SIZE):
        for col in range(encoder.SIZE):
            value = _cell(static, row, col)
            if value >= tables.FREE_MASK_OFF:
                free += 1
            else:
                assert value == reference[row][col], f"({row}, {col}), mask {mask}"
    assert free == encoder.FREE_MODULES


@pytest.mark.parametrize("mask", range(8))
def test_free_cells_carry_the_mask_bit(mask: int) -> None:
    """
    The ROM's one trick: bit 0 of a free cell is the mask, so the walker never
    evaluates a mask predicate. Checked against the predicate itself.
    """
    static = tables.static_matrix_table(mask)
    reference = encoder.build_static_matrix(mask)
    predicate = encoder.MASK_PREDICATES[mask]
    for row in range(encoder.SIZE):
        for col in range(encoder.SIZE):
            value = _cell(static, row, col)
            if reference[row * encoder.SIZE + col] == encoder.FREE:
                assert value in (tables.FREE_MASK_OFF, tables.FREE_MASK_ON)
                assert bool(value & 1) == bool(predicate(row, col))
            else:
                assert value < tables.FREE_MASK_OFF


def test_static_matrix_is_padded_to_an_even_grid(by_name) -> None:
    """The padding row and column are what let the tile builder skip bounds tests."""
    data = by_name["static_matrix"].data
    assert len(data) == tables.ROM_MATRIX_STRIDE * tables.ROM_MATRIX_ROWS
    for index in range(encoder.SIZE, tables.ROM_MATRIX_STRIDE):
        for row in range(tables.ROM_MATRIX_ROWS):
            assert _cell(data, row, index) == 0
        for col in range(tables.ROM_MATRIX_STRIDE):
            assert _cell(data, index, col) == 0


def test_static_matrix_is_the_fixed_mask(by_name) -> None:
    assert by_name["static_matrix"].data == tables.static_matrix_table(FIXED_MASK)


def test_static_matrix_holds_only_the_four_legal_values(by_name) -> None:
    assert set(by_name["static_matrix"].data) == {
        0x00,
        0x01,
        tables.FREE_MASK_OFF,
        tables.FREE_MASK_ON,
    }


# --------------------------------------------------------------------------
# CHR
# --------------------------------------------------------------------------


def test_chr_tiles_decode_to_their_own_index(by_name) -> None:
    tiles = nes.decode_chr(by_name["chr"].data)
    assert tiles.shape == (nes.QR_TILE_COUNT, 8, 8)
    for index, tile in enumerate(tiles):
        quadrants = (
            (tile[0][0], 3),  # top-left
            (tile[0][7], 2),  # top-right
            (tile[7][0], 1),  # bottom-left
            (tile[7][7], 0),  # bottom-right
        )
        for pixel, bit in quadrants:
            assert pixel == (index >> bit) & 1
        # Each quadrant is solid, and nothing uses colour 2 or 3.
        assert set(tile.flatten().tolist()) <= {0, 1}
        for row_start in (0, 4):
            for col_start in (0, 4):
                block = tile[row_start : row_start + 4, col_start : col_start + 4]
                assert len(set(block.flatten().tolist())) == 1


def test_chr_second_plane_is_empty(by_name) -> None:
    data = by_name["chr"].data
    for index in range(nes.QR_TILE_COUNT):
        assert data[index * 16 + 8 : index * 16 + 16] == bytes(8)


# --------------------------------------------------------------------------
# base64url alphabet and code word head
# --------------------------------------------------------------------------


def test_base64_alphabet_matches_the_encoder(by_name) -> None:
    alphabet = by_name["base64"].data
    for index in range(64):
        # A group whose first sextet is `index` and whose rest is zero.
        assert base64url_encode(bytes([index << 2, 0, 0]))[0] == chr(alphabet[index])


def test_codeword_head_is_what_real_payloads_encode_to(by_name, urls) -> None:
    head = by_name["codeword_head"].data
    for url in urls:
        assert encoder.data_codewords(url.encode())[: len(head)] == head


def test_codeword_head_stops_at_the_first_variable_code_word(urls) -> None:
    """One past the head must actually vary, or the head is being cut short."""
    position = tables.CONSTANT_CODEWORDS
    seen = {encoder.data_codewords(url.encode())[position] for url in urls}
    assert len(seen) > 1


def test_codeword_head_starts_with_the_documented_constants(by_name) -> None:
    head = by_name["codeword_head"].data
    # Mode indicator 0100 plus the high nibble of the 74-character count.
    assert head[0] == 0x44
    assert head[1] == 0xA0 | (ord(URL_PREFIX[0]) >> 4)
    assert head[2] == ((ord(URL_PREFIX[0]) & 0x0F) << 4) | (ord(URL_PREFIX[1]) >> 4)


# --------------------------------------------------------------------------
# Blob, layout and manifest
# --------------------------------------------------------------------------


def test_blob_is_the_tables_concatenated_in_order(built) -> None:
    data = tables.blob(built)
    offset = 0
    for table in built:
        assert data[offset : offset + table.size] == table.data
        offset += table.size
    assert offset == len(data)


def test_layout_offsets_are_contiguous(built) -> None:
    expected = 0
    for placement in tables.layout(built):
        assert placement.offset == expected
        assert placement.address is None
        assert placement.page_aligned is None
        assert "address" not in placement.to_dict()
        expected += placement.table.size


def test_gf_tables_are_page_aligned_at_a_page_aligned_origin(built) -> None:
    placements = {p.table.name: p for p in tables.layout(built, origin=0x8400)}
    assert placements["antilog"].address == 0x8400
    assert placements["log"].address == 0x8500
    assert placements["antilog"].page_aligned
    assert placements["log"].page_aligned
    assert not placements["codeword_head"].page_aligned


def test_manifest_describes_the_blob(built) -> None:
    import hashlib

    manifest = tables.manifest(built, origin=0x8400)
    data = tables.blob(built)
    assert manifest["total_bytes"] == len(data)
    assert manifest["sha256"] == hashlib.sha256(data).hexdigest()
    assert manifest["mask"] == FIXED_MASK
    assert manifest["url_prefix"] == URL_PREFIX
    assert manifest["origin_hex"] == "$8400"
    entries = manifest["tables"]
    assert isinstance(entries, list)
    assert [entry["name"] for entry in entries] == [table.name for table in built]


# --------------------------------------------------------------------------
# Assembler output
# --------------------------------------------------------------------------


def _parse_asm(text: str) -> dict[str, bytes]:
    """Read `.byte` directives back out of the include, keyed by label."""
    out: dict[str, bytearray] = {}
    label = None
    for line in text.splitlines():
        line = line.split(";")[0].strip()
        if not line:
            continue
        if line.endswith(":"):
            name = line[:-1]
            if name.endswith("End"):
                label = None
            else:
                label = name
                out[label] = bytearray()
            continue
        if line.startswith(".byte"):
            assert label is not None, "bytes outside a label"
            for item in line[len(".byte") :].split(","):
                item = item.strip()
                assert item.startswith("$"), item
                out[label].append(int(item[1:], 16))
    return {name: bytes(data) for name, data in out.items()}


def test_asm_round_trips_to_the_same_bytes(built) -> None:
    parsed = _parse_asm(tables.to_asm(built))
    assert parsed == {table.label: table.data for table in built}


def test_asm_static_matrix_is_one_grid_row_per_line(built) -> None:
    text = tables.to_asm(built)
    body = text.split("QrStaticMatrix:\n", 1)[1].split("QrStaticMatrixEnd:", 1)[0]
    lines = [line for line in body.splitlines() if line.strip()]
    assert len(lines) == tables.ROM_MATRIX_ROWS
    for line in lines:
        assert len(line.split(",")) == tables.ROM_MATRIX_STRIDE


def test_asm_header_carries_the_constants(built) -> None:
    text = tables.to_asm(built, origin=0x8400)
    assert f"mask            {FIXED_MASK}" in text
    assert URL_PREFIX in text
    assert "$8400" in text
    assert ".org $8400" in text


def test_asm_stays_ascii(built) -> None:
    """Assemblers are not reliably UTF-8 aware; the include must not need it."""
    assert tables.to_asm(built, origin=0x8400).isascii()


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def test_write_tables_emits_blob_include_manifest_and_parts(tmp_path, built) -> None:
    written = tables.write_tables(tmp_path, built, origin=0x8400)
    names = {path.name for path in written}
    assert {"qr_tables.bin", "qr_tables.inc", "qr_tables.json"} <= names
    assert {f"{table.name}.bin" for table in built} <= names

    assert (tmp_path / "qr_tables.bin").read_bytes() == tables.blob(built)
    for table in built:
        assert (tmp_path / f"{table.name}.bin").read_bytes() == table.data

    manifest = json.loads((tmp_path / "qr_tables.json").read_text())
    assert manifest["total_bytes"] == EXPECTED_TOTAL
    assert manifest["origin"] == 0x8400

    parsed = _parse_asm((tmp_path / "qr_tables.inc").read_text())
    assert parsed == {table.label: table.data for table in built}


def test_write_tables_can_skip_the_per_table_binaries(tmp_path, built) -> None:
    written = tables.write_tables(tmp_path, built, split=False)
    assert {path.name for path in written} == {
        "qr_tables.bin",
        "qr_tables.inc",
        "qr_tables.json",
    }
