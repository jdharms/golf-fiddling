"""
The QR credentials patch: the credentials themselves, where the patch writes
them, and that an image finished with them still runs.

The last test overlays what the patch would write onto the unfinished image
and runs it, which is what proves the credentials landed in the placeholders
rather than somewhere plausible-looking.
"""

import random

import pytest

from golf.core.patches import SCORECARD_QR_PATCH, QrCredentials, qr_credentials_patch
from golf.core.patches.qr_credentials import PLACEHOLDERS
from golf.core.patches.scorecard_qr import QR_BANK
from golf.qr import payload, port, sample
from golf.qr.payload import RoundPayload, verify
from golf.qr.port import layout
from golf.qr.port.sim import Machine


@pytest.fixture(scope="module")
def credentials() -> QrCredentials:
    return QrCredentials.random(random.Random(1234))


def finished_image(credentials: QrCredentials) -> bytes:
    """The unfinished image with the patch's bytes laid over it."""
    image = bytearray(SCORECARD_QR_PATCH.image)
    for sub in qr_credentials_patch(credentials).patches:
        start = sub.prg_offset - SCORECARD_QR_PATCH.image_offset
        image[start : start + len(sub.patched)] = sub.patched
    return bytes(image)


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
# The patch
# --------------------------------------------------------------------------


def test_the_patch_fills_each_placeholder_from_the_fill(credentials) -> None:
    patch = qr_credentials_patch(credentials)
    assert patch.name == "qr_credentials"
    program = port.build()
    expected = {
        "QrSeedId": credentials.seed_id,
        "QrPlayerId": b"".join(credentials.player_ids),
        "QrMacKey": b"".join(credentials.keys),
    }
    assert len(patch.patches) == len(PLACEHOLDERS)
    for sub, (suffix, symbol, length) in zip(patch.patches, PLACEHOLDERS, strict=True):
        assert sub.name == f"qr_credentials_{suffix}"
        assert sub.prg_offset == QR_BANK * 0x4000 + program.symbol(symbol) - 0x8000
        assert sub.original == bytes([port.PATCH_FILL]) * length
        assert sub.patched == expected[symbol]


def test_the_placeholders_are_contiguous_and_inside_the_image(credentials) -> None:
    patch = qr_credentials_patch(credentials)
    image_start = SCORECARD_QR_PATCH.image_offset
    image_end = image_start + len(SCORECARD_QR_PATCH.image)
    covered = []
    for sub in patch.patches:
        assert image_start <= sub.prg_offset
        assert sub.prg_offset + len(sub.patched) <= image_end
        covered.extend(range(sub.prg_offset, sub.prg_offset + len(sub.patched)))
    assert covered == list(range(covered[0], covered[0] + 8 + 8 + 16))


def test_requires_scorecard_qr(credentials) -> None:
    assert list(qr_credentials_patch(credentials).requires) == [SCORECARD_QR_PATCH]


def test_only_the_placeholders_differ_from_the_unfinished_image(credentials) -> None:
    image = finished_image(credentials)
    program = port.build()
    allowed = set()
    for _, symbol, length in PLACEHOLDERS:
        start = program.symbol(symbol) - layout.TABLE_ORIGIN
        allowed.update(range(start, start + length))
    changed = {i for i in range(len(image)) if image[i] != SCORECARD_QR_PATCH.image[i]}
    # a credential byte may coincide with the fill, so a subset, not equal
    assert changed <= allowed


# --------------------------------------------------------------------------
# The finished image, run
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
        machine.write(layout.TABLE_ORIGIN, finished_image(credentials))
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
