"""
The scorecard QR patch: what it builds, and that what it builds still runs.

The patch's job is to put the right bytes in the right three places, so these
tests check the bytes — and then load the image the patch would write into the
simulator and run it, which is what proves the per-build credentials landed in
the placeholders rather than somewhere plausible-looking.
"""

import random

import pytest

from golf.core.patches import PatchError, QrCredentials, ScorecardQrPatch
from golf.core.patches.scorecard_qr import (
    EXECUTE_FAR_CALL,
    QR_BANK,
    SCORECARD_WAIT,
    TRAMPOLINE_CPU_ADDR,
    TRAMPOLINE_LIMIT,
    build_image,
    build_trampoline,
)
from golf.qr import payload, port, sample
from golf.qr.payload import RoundPayload, verify
from golf.qr.port import layout
from golf.qr.port.sim import Machine


@pytest.fixture(scope="module")
def credentials() -> QrCredentials:
    return QrCredentials.random(random.Random(1234))


@pytest.fixture(scope="module")
def patch(credentials) -> ScorecardQrPatch:
    return ScorecardQrPatch(credentials)


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------


def test_random_credentials_have_the_right_shape() -> None:
    credentials = QrCredentials.random(random.Random(7))
    assert len(credentials.seed_id) == payload.SEED_ID_LEN
    assert [len(pid) for pid in credentials.player_ids] == [payload.PLAYER_ID_LEN] * 2
    assert [len(key) for key in credentials.keys] == [payload.KEY_LEN] * 2
    assert credentials.player_ids[0] != credentials.player_ids[1]
    assert credentials.keys[0] != credentials.keys[1]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed_id", bytes(7)),
        ("player_ids", (bytes(4), bytes(3))),
        ("keys", (bytes(8), bytes(9))),
    ],
)
def test_wrong_length_credentials_are_rejected(field: str, value) -> None:
    good = {
        "seed_id": bytes(8),
        "player_ids": (bytes(4), bytes(4)),
        "keys": (bytes(8), bytes(8)),
    }
    with pytest.raises(ValueError):
        QrCredentials(**{**good, field: value})


def test_the_manifest_carries_what_the_server_needs(credentials) -> None:
    manifest = credentials.manifest()
    assert manifest["seed_id"] == credentials.seed_id.hex()
    players = manifest["players"]
    assert isinstance(players, list)
    assert [entry["slot"] for entry in players] == [0, 1]
    for slot, entry in enumerate(players):
        assert entry["player_id"] == credentials.player_ids[slot].hex()
        assert entry["key"] == credentials.keys[slot].hex()
    assert manifest["url_prefix"] == payload.URL_PREFIX


# --------------------------------------------------------------------------
# The image
# --------------------------------------------------------------------------


def test_the_image_is_the_port_with_the_credentials_written_in(credentials) -> None:
    program = port.build()
    plain = port.rom_bytes()
    image = build_image(credentials)
    assert len(image) == len(plain)

    changed = {index for index in range(len(image)) if image[index] != plain[index]}
    expected = set()
    for symbol, data in (
        ("QrSeedId", credentials.seed_id),
        ("QrPlayerId", b"".join(credentials.player_ids)),
        ("QrMacKey", b"".join(credentials.keys)),
    ):
        start = program.symbol(symbol) - layout.TABLE_ORIGIN
        assert image[start : start + len(data)] == data
        expected.update(range(start, start + len(data)))
    # Only the placeholders moved — and a zero byte in a credential may
    # coincide with the fill, so `changed` is a subset rather than equal.
    assert changed <= expected


def test_the_unpatched_placeholders_are_zero() -> None:
    """An unpatched build must not look like a valid cartridge."""
    program = port.build()
    image = port.rom_bytes()
    for symbol, length in (
        ("QrSeedId", payload.SEED_ID_LEN),
        ("QrPlayerId", 2 * payload.PLAYER_ID_LEN),
        ("QrMacKey", 2 * payload.KEY_LEN),
    ):
        start = program.symbol(symbol) - layout.TABLE_ORIGIN
        assert image[start : start + length] == bytes(length)


def test_the_image_fits_the_reclaimed_region(patch) -> None:
    end = layout.TABLE_ORIGIN + len(patch.image) - 1
    assert layout.REGION_START <= layout.TABLE_ORIGIN
    assert end <= layout.REGION_END
    assert layout.REGION_END - end > 4000  # room left for whatever comes next


# --------------------------------------------------------------------------
# The trampoline and the splice
# --------------------------------------------------------------------------


def test_the_trampoline_waits_then_far_calls(patch) -> None:
    assert patch.trampoline == bytes(
        [
            0x20,
            SCORECARD_WAIT & 0xFF,
            SCORECARD_WAIT >> 8,
            0x20,
            EXECUTE_FAR_CALL & 0xFF,
            EXECUTE_FAR_CALL >> 8,
            QR_BANK,
            patch.entry & 0xFF,
            patch.entry >> 8,
            0x60,
        ]
    )
    assert len(patch.trampoline) == 10


def test_the_trampoline_carries_whatever_entry_point_it_is_given() -> None:
    trampoline = build_trampoline(0xABCD)
    assert trampoline[6:9] == bytes([QR_BANK, 0xCD, 0xAB])
    assert len(trampoline) == 10


def test_the_trampoline_fits_below_the_seeded_wind_one(patch) -> None:
    assert TRAMPOLINE_CPU_ADDR + len(patch.trampoline) <= TRAMPOLINE_LIMIT
    assert TRAMPOLINE_LIMIT == 0xBFAF  # seeded_wind's trampoline starts here


def test_the_splice_repoints_the_wait_at_the_trampoline(patch) -> None:
    assert patch.vanilla_splice_bytes == bytes(
        [SCORECARD_WAIT & 0xFF, SCORECARD_WAIT >> 8]
    )
    assert patch.splice_bytes == bytes(
        [TRAMPOLINE_CPU_ADDR & 0xFF, TRAMPOLINE_CPU_ADDR >> 8]
    )


def test_the_offsets_are_where_those_banks_live(patch) -> None:
    assert patch.image_offset == 2 * 0x4000 + (layout.TABLE_ORIGIN - 0x8000)
    assert patch.trampoline_offset == 13 * 0x4000 + (TRAMPOLINE_CPU_ADDR - 0x8000)
    assert patch.splice_offset == 13 * 0x4000 + (0x852E - 0x8000)


def test_a_trampoline_entry_point_is_inside_the_region(patch) -> None:
    assert layout.REGION_START <= patch.entry <= layout.REGION_END
    assert patch.entry == port.build().symbol("QrShowCodes")


# --------------------------------------------------------------------------
# The image, run
# --------------------------------------------------------------------------


def test_the_patched_image_builds_a_verifiable_payload(credentials) -> None:
    """
    Load what the patch would write, run it, and check the code it produces
    against the credentials the patch put in — the end of the chain the server
    sees.
    """
    rng = random.Random(99)
    round_payload = sample.random_round(rng)

    for slot in (0, 1):
        machine = Machine()
        machine.write(layout.TABLE_ORIGIN, build_image(credentials))
        machine.set_round(
            [(hole.strokes, hole.putts) for hole in round_payload.holes],
            player=slot,
            player_count=1,
        )
        machine.call("QrBuildPayload", a=slot)
        built = machine.read(layout.PAYLOAD, payload.PAYLOAD_LEN)

        expected = RoundPayload(
            seed_id=credentials.seed_id,
            player_id=credentials.player_ids[slot],
            holes=round_payload.holes,
            player_slot=slot,
        )
        assert built == expected.to_bytes(credentials.keys[slot])
        assert verify(built, credentials.keys[slot])
        assert not verify(built, credentials.keys[1 - slot])


def test_an_image_that_would_not_fit_is_refused(monkeypatch, credentials) -> None:
    """Moving the origin near the end of the region has to fail loudly."""
    monkeypatch.setattr(layout, "TABLE_ORIGIN", layout.REGION_END - 100)
    with pytest.raises(PatchError):
        ScorecardQrPatch(credentials)
