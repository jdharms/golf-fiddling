"""
The 6502 port, differentially tested against the oracle one stage at a time.

Each stage of `golf/qr/port/` is run under py65 with the exported ROM tables in
place and its output compared byte for byte with what `golf.qr` produces for
the same round: payload, MAC, URL, data code words, error correction,
interleave, module matrix, nametable. Then the finished nametable is rendered
and handed to a real decoder, so a self-consistently wrong pipeline still gets
caught.
"""

import random

import pytest

from golf.qr import encoder, nes, sample, submission, tables
from golf.qr.decode import DECODERS
from golf.qr.payload import HoleRecord, RoundPayload, verify
from golf.qr.port import build, layout, rom_bytes
from golf.qr.port.sim import Machine
from golf.qr.render import render_screen

ROUNDS = 6


@pytest.fixture(scope="module")
def program():
    return build()


@pytest.fixture(scope="module")
def rounds() -> list[tuple[RoundPayload, bytes]]:
    rng = random.Random(90210)
    return [(sample.random_round(rng), sample.random_key(rng)) for _ in range(ROUNDS)]


def staged(program, round_payload: RoundPayload, key: bytes, slot: int = 0) -> Machine:
    """A machine with the patch-time constants and one finished round staged."""
    machine = Machine(program)
    machine.write(program.symbol("QrSeedId"), round_payload.seed_id)
    player_ids = [bytes(4), bytes(4)]
    keys = [bytes(8), bytes(8)]
    player_ids[slot] = round_payload.player_id
    keys[slot] = key
    machine.write(program.symbol("QrPlayerId"), b"".join(player_ids))
    machine.write(program.symbol("QrMacKey"), b"".join(keys))
    machine.set_round(
        [(hole.strokes, hole.putts) for hole in round_payload.holes],
        player=slot,
        player_count=1 if slot else 0,
    )
    return machine


def run_all(machine: Machine, slot: int = 0) -> None:
    """Every stage in order, as `QrBuildCode` runs them."""
    machine.call("QrBuildPayload", a=slot)
    machine.call("QrBuildUrl")
    machine.call("QrBuildCodewords")
    machine.call("QrReedSolomon")
    machine.call("QrInterleaveCodewords")
    machine.call("QrCopyMatrix")
    machine.call("QrWalkMatrix")
    machine.call("QrBuildNametable")


def matrix_rows(machine: Machine) -> list[list[int]]:
    data = machine.read(layout.MATRIX, layout.MATRIX_BYTES)
    stride = layout.MATRIX_STRIDE
    return [
        [data[row * stride + col] for col in range(encoder.SIZE)]
        for row in range(encoder.SIZE)
    ]


# --------------------------------------------------------------------------
# Stage by stage
# --------------------------------------------------------------------------


def test_payload_and_mac_match_the_oracle(program, rounds) -> None:
    for round_payload, key in rounds:
        machine = staged(program, round_payload, key)
        machine.call("QrBuildPayload", a=0)
        built = machine.read(layout.PAYLOAD, 36)
        assert built == round_payload.to_bytes(key)
        assert verify(built, key)


def test_url_matches_the_oracle(program, rounds) -> None:
    for round_payload, key in rounds:
        machine = staged(program, round_payload, key)
        machine.call("QrBuildPayload", a=0)
        machine.call("QrBuildUrl")
        url = machine.read(layout.URL, 74).decode("ascii")
        assert url == round_payload.to_url(key)


def test_code_words_error_correction_and_interleave_match(program, rounds) -> None:
    for round_payload, key in rounds:
        machine = staged(program, round_payload, key)
        stages = encoder.encode_stages(round_payload.to_url(key), submission.FIXED_MASK)
        machine.call("QrBuildPayload", a=0)
        machine.call("QrBuildUrl")
        machine.call("QrBuildCodewords")
        assert machine.read(layout.DATA_CODEWORDS, 86) == stages.data_codewords
        machine.call("QrReedSolomon")
        assert machine.read(layout.EC_CODEWORDS, 48) == b"".join(stages.ec_codewords)
        machine.call("QrInterleaveCodewords")
        assert machine.read(layout.INTERLEAVED, 134) == stages.interleaved


def test_matrix_matches_the_oracle(program, rounds) -> None:
    for round_payload, key in rounds:
        machine = staged(program, round_payload, key)
        run_all(machine)
        expected = encoder.encode(
            round_payload.to_url(key), submission.FIXED_MASK
        ).rows()
        assert matrix_rows(machine) == expected


def test_nametable_matches_the_oracle(program, rounds) -> None:
    for round_payload, key in rounds:
        machine = staged(program, round_payload, key)
        run_all(machine)
        expected = nes.build_nametable(
            encoder.encode(round_payload.to_url(key), submission.FIXED_MASK).rows(),
            base_tile=layout.TILE_BASE,
        )
        assert machine.read(layout.NAMETABLE, len(expected)) == expected


def test_the_entry_point_runs_the_same_pipeline(program, rounds) -> None:
    round_payload, key = rounds[0]
    stepwise = staged(program, round_payload, key)
    run_all(stepwise)
    whole = staged(program, round_payload, key)
    whole.call("QrBuildCode", a=0)
    assert whole.read(layout.NAMETABLE, 361) == stepwise.read(layout.NAMETABLE, 361)
    assert whole.read(layout.MATRIX, layout.MATRIX_BYTES) == stepwise.read(
        layout.MATRIX, layout.MATRIX_BYTES
    )


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------


def test_the_code_the_rom_builds_actually_decodes(program, rounds) -> None:
    """
    Straight from the 6502's own nametable through the CHR pipeline to a real
    decoder — the check that a self-consistently wrong port cannot pass.
    """
    chr_data = tables.chr_table()
    for round_payload, key in rounds:
        machine = staged(program, round_payload, key)
        run_all(machine)
        nametable = machine.read(layout.NAMETABLE, 361)
        rows = nes.render_modules(chr_data, nametable, layout.TILE_BASE)
        image = render_screen(encoder.QrMatrix(bytearray(sum(rows, [])), 0))
        assert DECODERS["zxing"](image) == round_payload.to_url(key)


# --------------------------------------------------------------------------
# The second player
# --------------------------------------------------------------------------


def test_player_slot_one_uses_its_own_id_key_and_scores(program, rounds) -> None:
    round_payload, key = rounds[1]
    slot_one = RoundPayload(
        seed_id=round_payload.seed_id,
        player_id=round_payload.player_id,
        holes=round_payload.holes,
        player_slot=1,
    )
    machine = staged(program, slot_one, key, slot=1)
    machine.call("QrBuildPayload", a=1)
    assert machine.read(layout.PAYLOAD, 36) == slot_one.to_bytes(key)


def test_the_two_slots_produce_different_codes(program, rounds) -> None:
    """Both players' arrays live at once; neither slot may read the other's."""
    round_payload, key = rounds[2]
    machine = Machine(program)
    machine.write(program.symbol("QrSeedId"), round_payload.seed_id)
    machine.write(program.symbol("QrPlayerId"), b"\x01\x02\x03\x04\x05\x06\x07\x08")
    machine.write(program.symbol("QrMacKey"), bytes(range(16)))
    first = [(4, 2)] * 18
    second = [(5, 1)] * 18
    machine.set_round(first, player=0, player_count=1)
    machine.set_round(second, player=1, player_count=1)

    machine.call("QrBuildPayload", a=0)
    payload_one = machine.read(layout.PAYLOAD, 36)
    machine.call("QrBuildPayload", a=1)
    payload_two = machine.read(layout.PAYLOAD, 36)

    assert payload_one[9:13] == b"\x01\x02\x03\x04"
    assert payload_two[9:13] == b"\x05\x06\x07\x08"
    assert payload_one[13] == 0
    assert payload_two[13] == 1
    assert payload_one[14:32] == bytes([0x32]) * 18  # strokes 4, putts 2
    assert payload_two[14:32] == bytes([0x41]) * 18  # strokes 5, putts 1
    assert verify(payload_one, bytes(range(8)))
    assert verify(payload_two, bytes(range(8, 16)))


# --------------------------------------------------------------------------
# Hole records at the edges
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("strokes", "putts", "expected"),
    [
        (1, 0, 0x00),
        (4, 2, 0x32),
        (16, 15, 0xFF),
        (17, 2, 0xF2),  # strokes clamp at 16
        (50, 20, 0xFF),  # both clamp
        (0xFF, 0, 0xF0),  # an unplayed hole reads $FF and clamps like any other
        (0, 0, 0x00),  # a zero can only come from corrupt RAM; treat it as 1
    ],
)
def test_hole_records_clamp_the_way_the_oracle_does(
    program, strokes: int, putts: int, expected: int
) -> None:
    machine = Machine(program)
    machine.write(program.symbol("QrMacKey"), bytes(16))
    machine.set_round([(strokes, putts)] * 18)
    machine.call("QrBuildPayload", a=0)
    assert machine.read(layout.PAYLOAD + 14, 18) == bytes([expected]) * 18

    if 1 <= strokes <= 16 and putts <= 15:
        assert HoleRecord(strokes, min(putts, strokes)).pack() == expected


def test_a_clamped_round_still_matches_the_oracle(program) -> None:
    """A disastrous round is where the ROM and the oracle could disagree."""
    holes = tuple(HoleRecord(strokes=20, putts=9) for _ in range(18))
    round_payload = RoundPayload(
        seed_id=bytes(range(8)), player_id=bytes(range(4)), holes=holes
    )
    key = bytes(range(100, 108))
    machine = staged(program, round_payload, key)
    machine.call("QrBuildPayload", a=0)
    assert machine.read(layout.PAYLOAD, 36) == round_payload.to_bytes(key)


# --------------------------------------------------------------------------
# The build itself
# --------------------------------------------------------------------------


def test_the_routine_fits_the_region_with_the_tables(program) -> None:
    image = rom_bytes()
    total = len(image)
    assert layout.TABLE_ORIGIN >= layout.REGION_START
    assert layout.TABLE_ORIGIN + total <= layout.REGION_END
    # The whole feature, tables included, against the budget in the doc.
    assert total < 5000, total


def test_scratch_ram_stays_inside_the_reclaimed_block() -> None:
    highest = max(
        layout.MATRIX + layout.MATRIX_BYTES,
        layout.NAMETABLE + 361,
        layout.INTERLEAVED + 134,
        layout.RS_REMAINDER + 24,
    )
    assert layout.MATRIX >= layout.SCRATCH_START
    assert highest <= layout.SCRATCH_END + 1


def test_the_nametable_deliberately_overlays_the_dead_buffers() -> None:
    """
    The one RAM trick in the port, asserted so a future edit cannot quietly
    break it: the nametable reuses the payload, URL and code word buffers, all
    of which are dead by the time it is built. The matrix is not among them.
    """
    assert layout.NAMETABLE == layout.PAYLOAD
    assert layout.NAMETABLE + 361 > layout.INTERLEAVED
    assert layout.NAMETABLE >= layout.MATRIX + layout.MATRIX_BYTES


def test_assembling_twice_gives_the_same_bytes() -> None:
    assert build(origin=0x8E00).code == build.__wrapped__(origin=0x8E00).code


def test_every_stage_entry_point_exists(program) -> None:
    for name in (
        "QrBuildCode",
        "QrBuildPayload",
        "QrBuildUrl",
        "QrHashMac",
        "QrBuildCodewords",
        "QrReedSolomon",
        "QrInterleaveCodewords",
        "QrCopyMatrix",
        "QrWalkMatrix",
        "QrBuildNametable",
    ):
        assert layout.REGION_START <= program.symbol(name) <= layout.REGION_END
