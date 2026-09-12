"""
The 36-byte submission payload, its MAC, and its URL encoding.

Several of these assert properties the ROM depends on being constant — payload
length, URL length, the multiple-of-3 and multiple-of-4 rules — so a future
layout change that breaks the on-cart assumptions fails here first.
"""

import random

import pytest

from golf.qr import encoder, sample
from golf.qr.payload import (
    BASE64_LEN,
    BODY_LEN,
    HOLE_COUNT,
    MAC_LEN,
    MAX_PUTTS,
    MAX_STROKES,
    PAYLOAD_LEN,
    PROTOCOL_VERSION,
    STROKE_BITS,
    URL_LEN,
    URL_PREFIX,
    HoleRecord,
    RoundPayload,
    base64url_decode,
    base64url_encode,
    pack_hole,
    unpack_hole,
    verify,
)

KEY = bytes(range(8))
SEED_ID = bytes.fromhex("0123456789abcdef")
PLAYER_ID = bytes.fromhex("deadbeef")


def make_round(**overrides) -> RoundPayload:
    defaults = {
        "seed_id": SEED_ID,
        "player_id": PLAYER_ID,
        "holes": tuple(HoleRecord(4, 2) for _ in range(HOLE_COUNT)),
    }
    return RoundPayload(**{**defaults, **overrides})


# --------------------------------------------------------------------------
# Invariants the ROM bakes in
# --------------------------------------------------------------------------


def test_payload_length_is_a_multiple_of_three() -> None:
    """Keeps base64 pad-free, which keeps the QR character count constant."""
    assert PAYLOAD_LEN % 3 == 0


def test_maced_region_is_a_multiple_of_four() -> None:
    """
    HalfSipHash consumes 32-bit words; a whole number of them means the 6502
    implementation needs no partial-word tail path.
    """
    assert BODY_LEN % 4 == 0


def test_url_fits_the_qr_with_headroom() -> None:
    assert URL_LEN == 74
    assert URL_LEN < encoder.MAX_CHARS


def test_headroom_allows_growth_to_forty_two_bytes() -> None:
    """
    42 bytes is the documented ceiling: the next multiple of 3 above it needs
    60 base64 characters, which overflows version 5-M.
    """
    assert len(URL_PREFIX) + 42 // 3 * 4 <= encoder.MAX_CHARS
    assert len(URL_PREFIX) + 45 // 3 * 4 > encoder.MAX_CHARS


def test_lengths_are_self_consistent() -> None:
    assert PAYLOAD_LEN == BODY_LEN + MAC_LEN
    assert BASE64_LEN == PAYLOAD_LEN // 3 * 4
    assert len(URL_PREFIX) + BASE64_LEN == URL_LEN


# --------------------------------------------------------------------------
# base64url
# --------------------------------------------------------------------------


def test_base64url_round_trips() -> None:
    rng = random.Random(1)
    for _ in range(200):
        data = bytes(rng.randrange(256) for _ in range(PAYLOAD_LEN))
        assert base64url_decode(base64url_encode(data)) == data


def test_base64url_matches_stdlib() -> None:
    import base64

    rng = random.Random(2)
    for _ in range(50):
        data = bytes(rng.randrange(256) for _ in range(PAYLOAD_LEN))
        expected = base64.urlsafe_b64encode(data).decode().rstrip("=")
        assert base64url_encode(data) == expected


def test_base64url_output_is_pad_free_and_url_safe() -> None:
    rng = random.Random(3)
    for _ in range(100):
        text = base64url_encode(bytes(rng.randrange(256) for _ in range(PAYLOAD_LEN)))
        assert len(text) == BASE64_LEN
        assert "=" not in text
        assert "+" not in text
        assert "/" not in text


def test_base64url_rejects_lengths_that_would_need_padding() -> None:
    with pytest.raises(ValueError, match="multiple of 3"):
        base64url_encode(b"ab")


def test_base64url_rejects_bad_characters() -> None:
    with pytest.raises(ValueError, match="invalid base64url character"):
        base64url_decode("AAA!")


# --------------------------------------------------------------------------
# Hole records
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("strokes", "putts", "packed"),
    [
        (1, 0, 0x00),
        (4, 2, 0x32),
        (16, 15, 0xFF),
        (10, 3, 0x93),
    ],
)
def test_hole_record_packing(strokes: int, putts: int, packed: int) -> None:
    assert HoleRecord(strokes, putts).pack() == packed


def test_hole_record_clamps_strokes_above_sixteen() -> None:
    record = HoleRecord(strokes=22, putts=3)
    assert record.strokes_clamped
    assert record.pack() == ((16 - 1) << 4) | 3


def test_hole_record_clamps_putts_above_fifteen() -> None:
    record = HoleRecord(strokes=20, putts=16)
    assert record.putts_clamped
    assert record.pack() & 0x0F == 15


def test_hole_record_rejects_impossible_values() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        HoleRecord(0, 0)
    with pytest.raises(ValueError, match="cannot be negative"):
        HoleRecord(4, -1)
    with pytest.raises(ValueError, match="cannot exceed strokes"):
        HoleRecord(2, 3)


def test_clamped_holes_are_reported() -> None:
    holes = [HoleRecord(4, 2) for _ in range(HOLE_COUNT)]
    holes[6] = HoleRecord(19, 2)
    payload = make_round(holes=tuple(holes))
    assert payload.clamped_holes == (7,)


def test_unclamped_round_reports_nothing() -> None:
    assert make_round().clamped_holes == ()


# --------------------------------------------------------------------------
# Payload assembly
# --------------------------------------------------------------------------


def test_body_layout() -> None:
    body = make_round(player_slot=1).body()
    assert len(body) == BODY_LEN
    assert body[0] == PROTOCOL_VERSION
    assert body[1:9] == SEED_ID
    assert body[9:13] == PLAYER_ID
    assert body[13] == 0x01
    assert body[14:32] == bytes([0x32] * HOLE_COUNT)


def test_player_slot_occupies_two_bits() -> None:
    assert make_round(player_slot=0).flags == 0
    assert make_round(player_slot=1).flags == 1
    with pytest.raises(ValueError, match="2 bits"):
        make_round(player_slot=4)


def test_totals() -> None:
    payload = make_round()
    assert payload.total_strokes == 4 * HOLE_COUNT
    assert payload.total_putts == 2 * HOLE_COUNT


def test_payload_round_trips_through_url() -> None:
    rng = random.Random(4)
    for _ in range(100):
        original = sample.random_round(rng)
        key = sample.random_key(rng)
        url = original.to_url(key)
        assert len(url) == URL_LEN
        parsed, mac = RoundPayload.from_url(url)
        assert parsed.body() == original.body()
        assert mac == original.mac(key)


def test_round_trip_preserves_unclamped_scores() -> None:
    rng = random.Random(5)
    original = sample.random_round(rng, disaster_chance=0.0)
    parsed, _ = RoundPayload.from_bytes(original.to_bytes(KEY))
    assert [(h.strokes, h.putts) for h in parsed.holes] == [
        (h.strokes, h.putts) for h in original.holes
    ]


def test_clamped_round_decodes_to_the_clamped_value() -> None:
    holes = [HoleRecord(4, 2) for _ in range(HOLE_COUNT)]
    holes[0] = HoleRecord(30, 2)
    parsed, _ = RoundPayload.from_bytes(make_round(holes=tuple(holes)).to_bytes(KEY))
    assert parsed.holes[0].strokes == 16


def test_wrong_length_payload_is_rejected() -> None:
    with pytest.raises(ValueError, match=f"must be {PAYLOAD_LEN} bytes"):
        RoundPayload.from_bytes(b"\x00" * 10)


def test_url_with_wrong_prefix_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not start with"):
        RoundPayload.from_url("https://example.com/s/" + "A" * BASE64_LEN)


# --------------------------------------------------------------------------
# MAC
# --------------------------------------------------------------------------


def test_mac_verifies() -> None:
    assert verify(make_round().to_bytes(KEY), KEY)


def test_mac_fails_with_the_wrong_key() -> None:
    assert not verify(make_round().to_bytes(KEY), bytes(range(1, 9)))


def test_every_body_byte_is_covered_by_the_mac() -> None:
    """A one-bit change anywhere in bytes 0-31 must invalidate the MAC."""
    payload = make_round().to_bytes(KEY)
    for index in range(BODY_LEN):
        for bit in range(8):
            tampered = bytearray(payload)
            tampered[index] ^= 1 << bit
            assert not verify(bytes(tampered), KEY), f"byte {index} bit {bit}"


def test_mac_is_four_bytes() -> None:
    assert len(make_round().mac(KEY)) == MAC_LEN == 4


def test_mac_key_length_is_validated() -> None:
    with pytest.raises(ValueError, match="key must be 8 bytes"):
        make_round().mac(b"short")


def test_different_seeds_give_different_macs() -> None:
    a = make_round(seed_id=bytes(8)).mac(KEY)
    b = make_round(seed_id=bytes(range(8))).mac(KEY)
    assert a != b


# --------------------------------------------------------------------------
# The stroke/putt split, which is still an open question
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stroke_bits", [4, 5])
def test_either_split_round_trips_within_range(stroke_bits: int) -> None:
    """
    Both candidate splits are exercised so switching `STROKE_BITS` is a
    one-line change rather than a hunt for hardcoded nibbles.
    """
    max_strokes = 1 << stroke_bits
    max_putts = (1 << (8 - stroke_bits)) - 1
    for strokes in range(1, max_strokes + 1):
        for putts in range(0, max_putts + 1):
            packed = pack_hole(strokes, putts, stroke_bits)
            assert 0 <= packed <= 0xFF
            assert unpack_hole(packed, stroke_bits) == (strokes, putts)


@pytest.mark.parametrize("stroke_bits", [4, 5])
def test_either_split_clamps_rather_than_overflowing(stroke_bits: int) -> None:
    max_strokes = 1 << stroke_bits
    max_putts = (1 << (8 - stroke_bits)) - 1
    packed = pack_hole(50, 40, stroke_bits)
    assert unpack_hole(packed, stroke_bits) == (max_strokes, max_putts)


def test_current_split_is_four_four() -> None:
    """Pins the decision recorded in docs/scorecard_qr.md."""
    assert STROKE_BITS == 4
    assert MAX_STROKES == 16
    assert MAX_PUTTS == 15
