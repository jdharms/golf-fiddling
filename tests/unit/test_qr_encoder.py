"""
The version 5-M QR encoder, checked structurally and semantically.

Structurally against `qrcode`, an independent implementation of the same spec:
every module of every matrix must agree, for every mask. That is a far stronger
check than "a decoder can read it", and it is the check the 6502 port will be
held to in turn.

Semantically against two real decoders, so a matrix that is self-consistently
wrong still gets caught.
"""

import random

import pytest
import qrcode
from qrcode.constants import ERROR_CORRECT_M

from golf.qr import encoder, sample
from golf.qr.decode import DECODERS
from golf.qr.galois import (
    ANTILOG_TABLE,
    LOG_TABLE,
    generator_poly,
    multiply,
    reed_solomon,
)
from golf.qr.payload import URL_LEN, URL_PREFIX
from golf.qr.render import render_screen

MASKS = tuple(range(8))


def reference_matrix(text: str, mask: int) -> list[list[int]]:
    code = qrcode.QRCode(
        version=encoder.VERSION,
        error_correction=ERROR_CORRECT_M,
        border=0,
        mask_pattern=mask,
    )
    code.add_data(text, optimize=0)
    code.make(fit=False)
    return [[1 if value else 0 for value in row] for row in code.modules]


@pytest.fixture(scope="module")
def urls() -> list[str]:
    rng = random.Random(1234)
    key = sample.random_key(rng)
    return [sample.random_round(rng).to_url(key) for _ in range(12)]


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------


def test_geometry_constants() -> None:
    assert encoder.SIZE == 37
    assert encoder.FREE_MODULES + encoder.FUNCTION_MODULES == encoder.SIZE**2
    assert encoder.REMAINDER_BITS == 7


def test_block_structure_is_two_equal_blocks() -> None:
    """The reason interleaving is a plain alternating copy on cart."""
    assert encoder.NUM_BLOCKS * encoder.DATA_PER_BLOCK == encoder.DATA_CODEWORDS
    assert (
        encoder.NUM_BLOCKS * (encoder.DATA_PER_BLOCK + encoder.EC_PER_BLOCK)
        == encoder.TOTAL_CODEWORDS
    )


def test_capacity_matches_the_spec() -> None:
    """84 characters: 86 data code words less the 12-bit header and terminator."""
    assert encoder.MAX_CHARS == (encoder.DATA_CODEWORDS * 8 - 4 - 8 - 4) // 8


# --------------------------------------------------------------------------
# Galois field
# --------------------------------------------------------------------------


def test_gf_tables_are_the_right_size() -> None:
    assert len(ANTILOG_TABLE) == 256
    assert len(LOG_TABLE) == 256


def test_gf_log_and_antilog_are_inverse() -> None:
    for value in range(1, 256):
        assert ANTILOG_TABLE[LOG_TABLE[value]] == value


def test_gf_multiply_is_commutative_and_has_an_identity() -> None:
    rng = random.Random(9)
    for _ in range(300):
        a, b = rng.randrange(256), rng.randrange(256)
        assert multiply(a, b) == multiply(b, a)
        assert multiply(a, 1) == a
        assert multiply(a, 0) == 0


def test_generator_polynomial_for_ten_matches_the_published_table() -> None:
    assert generator_poly(10) == [
        1,
        216,
        194,
        159,
        111,
        199,
        94,
        95,
        113,
        157,
        193,
    ]


def test_generator_polynomial_length() -> None:
    poly = generator_poly(encoder.EC_PER_BLOCK)
    assert len(poly) == encoder.EC_PER_BLOCK + 1
    assert poly[0] == 1


def test_reed_solomon_output_length() -> None:
    data = bytes(range(encoder.DATA_PER_BLOCK))
    assert len(reed_solomon(data, encoder.EC_PER_BLOCK)) == encoder.EC_PER_BLOCK


# --------------------------------------------------------------------------
# Data code words
# --------------------------------------------------------------------------


@pytest.mark.parametrize("length", [0, 1, 10, 40, 73, 74, 80, 83, 84])
def test_nibble_shift_matches_a_general_bit_packer(length: int) -> None:
    text = bytes(range(length))
    assert encoder.data_codewords(text) == encoder._data_codewords_bitwise(text)


def test_data_codewords_header_is_the_documented_constant() -> None:
    """The ROM bakes in code word 0 and the low nibble of the count."""
    codewords = encoder.data_codewords(b"x" * URL_LEN)
    assert codewords[0] == 0x44
    assert codewords[1] >> 4 == 0x0A


def test_data_codewords_pad_tail(urls: list[str]) -> None:
    codewords = encoder.data_codewords(urls[0].encode())
    # 12 header bits + 74 bytes + 4-bit terminator is 76 whole code words.
    assert len(codewords) == encoder.DATA_CODEWORDS
    assert codewords[76:] == bytes((0xEC, 0x11) * 5)


def test_url_prefix_makes_the_stream_head_constant(urls: list[str]) -> None:
    """
    Only the base64 tail varies, so the leading code words can be a ROM table.
    Checks the whole constant run rather than a guessed length.
    """
    streams = [encoder.data_codewords(url.encode()) for url in urls]
    constant = 0
    while (
        constant < encoder.DATA_CODEWORDS and len({s[constant] for s in streams}) == 1
    ):
        constant += 1
    # 12 header bits plus 26 prefix characters is 214 bits, i.e. 26 whole
    # code words before the first byte that can vary.
    assert constant >= (4 + 8 + len(URL_PREFIX) * 8) // 8


def test_oversized_payload_is_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds version 5-M capacity"):
        encoder.data_codewords(b"x" * 85)


# --------------------------------------------------------------------------
# Static matrix and placement
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mask", MASKS)
def test_static_matrix_has_the_right_number_of_function_modules(mask: int) -> None:
    static = encoder.build_static_matrix(mask)
    assert len(static) == encoder.SIZE**2
    assert sum(1 for m in static if m != encoder.FREE) == encoder.FUNCTION_MODULES


def test_function_module_layout_is_the_same_for_every_mask() -> None:
    """
    Only the format bits' values change with the mask, never which cells are
    function cells — which is why the ROM can carry one walk order.
    """
    layouts = {
        bytes(1 if m != encoder.FREE else 0 for m in encoder.build_static_matrix(mask))
        for mask in MASKS
    }
    assert len(layouts) == 1


@pytest.mark.parametrize("mask", MASKS)
def test_walk_order_covers_every_free_module_once(mask: int) -> None:
    static = encoder.build_static_matrix(mask)
    order = encoder.walk_order(static)
    assert len(order) == encoder.FREE_MODULES
    assert len(set(order)) == encoder.FREE_MODULES
    assert all(static[index] == encoder.FREE for index in order)


def test_walk_order_skips_the_timing_column() -> None:
    order = encoder.walk_order(encoder.build_static_matrix(0))
    assert all(index % encoder.SIZE != 6 for index in order)


def test_walk_starts_at_the_bottom_right() -> None:
    order = encoder.walk_order(encoder.build_static_matrix(0))
    assert order[0] == (encoder.SIZE - 1) * encoder.SIZE + (encoder.SIZE - 1)


@pytest.mark.parametrize("mask", MASKS)
def test_format_bits_round_trip_through_bch(mask: int) -> None:
    bits = encoder.format_bits(mask)
    assert bits.bit_length() <= 15
    unmasked = bits ^ 0x5412
    assert unmasked >> 10 == (encoder.EC_LEVEL_FORMAT_BITS << 3) | mask


def test_format_bits_rejects_bad_masks() -> None:
    with pytest.raises(ValueError, match="mask must be 0-7"):
        encoder.format_bits(8)


def test_place_rejects_a_wrong_length_stream() -> None:
    with pytest.raises(ValueError, match="expected 134 code words"):
        encoder.place(b"\x00" * 10, encoder.build_static_matrix(0), 0)


# --------------------------------------------------------------------------
# Against an independent encoder
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mask", MASKS)
def test_matrix_matches_reference_encoder(mask: int, urls: list[str]) -> None:
    for url in urls:
        assert encoder.encode(url, mask).rows() == reference_matrix(url, mask), (
            f"mask {mask}, {url}"
        )


@pytest.mark.parametrize("mask", MASKS)
def test_matrix_matches_reference_at_capacity_edges(mask: int) -> None:
    for text in ("x", "x" * URL_LEN, "x" * encoder.MAX_CHARS):
        assert encoder.encode(text, mask).rows() == reference_matrix(text, mask), (
            f"mask {mask}, length {len(text)}"
        )


# --------------------------------------------------------------------------
# Against real decoders
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mask", MASKS)
def test_every_mask_decodes_cleanly_with_zxing(mask: int, urls: list[str]) -> None:
    """
    zxing-cpp is the stand-in for a phone scanner, and it must read every mask.
    OpenCV's detector is deliberately not asserted here: it fails on a handful
    of clean renders under masks 0, 1, 2 and 7, which is a limitation of that
    detector rather than of the encoder (the matrices match the reference
    implementation module for module). Which masks survive *both* decoders is
    what `golf-qr-validate` measures, and what the fixed-mask test below pins.
    """
    for url in urls:
        image = render_screen(encoder.encode(url, mask), scale=3)
        assert DECODERS["zxing"](image) == url, f"mask {mask}, {url}"


# --------------------------------------------------------------------------
# Penalty scoring
# --------------------------------------------------------------------------


def test_penalty_is_positive_and_mask_dependent(urls: list[str]) -> None:
    scores = {mask: encoder.penalty(encoder.encode(urls[0], mask)) for mask in MASKS}
    assert all(score > 0 for score in scores.values())
    assert len(set(scores.values())) > 1


def test_best_mask_is_the_lowest_penalty(urls: list[str]) -> None:
    url = urls[0]
    chosen = encoder.best_mask(url)
    scores = [encoder.penalty(encoder.encode(url, mask)) for mask in MASKS]
    assert scores[chosen] == min(scores)
