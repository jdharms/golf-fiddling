"""
QR credentials patch: finish a scorecard QR image with one player's seed ID,
player IDs and MAC keys.

`scorecard_qr` installs the QR screen with its placeholders (`QrSeedId`,
`QrPlayerId`, `QrMacKey`) left holding `port.PATCH_FILL`. A randomized ROM is
built in two stages (`docs/randomizer_devplan.md`): the unfinished ROM, QR
image included, is built once per seed, and this patch writes the credentials
per download, in the finishing stack.

Three byte patches, one per placeholder. Each expects the fill as its original
bytes, so:

- finishing can only land on an unfinished image, one `scorecard_qr` wrote;
- a ROM already finished with other credentials is refused rather than
  overwritten;
- finishing twice with the same credentials writes nothing.

A credential byte equal to the fill writes nothing either. An all-zero seed ID
or player ID is what an unfinished ROM submits, and the server rejects it.

The IDs are public. **The keys are not**: they are what stops a player
submitting a scorecard as somebody else, they live server-side keyed to
(seed, player, slot), and they never appear in a manifest or a report.
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

from golf.qr import payload, port

from .byte_patch import BytePatch
from .composite import CompositePatch
from .scorecard_qr import QR_BANK, SCORECARD_QR_PATCH, _prg_offset


@dataclass(frozen=True)
class QrCredentials:
    """
    What finishing writes into each ROM: the seed this cartridge plays, and one
    player ID and MAC key per player slot.
    """

    seed_id: bytes
    player_ids: tuple[bytes, bytes]
    keys: tuple[bytes, bytes]

    def __post_init__(self) -> None:
        if len(self.seed_id) != payload.SEED_ID_LEN:
            raise ValueError(f"seed_id must be {payload.SEED_ID_LEN} bytes")
        for player_id in self.player_ids:
            if len(player_id) != payload.PLAYER_ID_LEN:
                raise ValueError(f"player_id must be {payload.PLAYER_ID_LEN} bytes")
        for key in self.keys:
            if len(key) != payload.KEY_LEN:
                raise ValueError(f"key must be {payload.KEY_LEN} bytes")

    @classmethod
    def random(cls, rng: random.Random | None = None) -> "QrCredentials":
        source = rng or random.SystemRandom()

        def draw(count: int) -> bytes:
            return bytes(source.randrange(256) for _ in range(count))

        return cls(
            seed_id=draw(payload.SEED_ID_LEN),
            player_ids=(draw(payload.PLAYER_ID_LEN), draw(payload.PLAYER_ID_LEN)),
            keys=(draw(payload.KEY_LEN), draw(payload.KEY_LEN)),
        )

    def manifest(self) -> dict[str, object]:
        """Everything the server needs to verify this cartridge's submissions."""
        return {
            "seed_id": self.seed_id.hex(),
            "players": [
                {"slot": slot, "player_id": pid.hex(), "key": key.hex()}
                for slot, (pid, key) in enumerate(
                    zip(self.player_ids, self.keys, strict=True)
                )
            ],
            "url_prefix": payload.URL_PREFIX,
            "protocol_version": payload.PROTOCOL_VERSION,
        }

    @classmethod
    def from_manifest(cls, data) -> "QrCredentials":
        """Read credentials back from what `manifest()` wrote."""
        try:
            players = sorted(data["players"], key=lambda player: player["slot"])
            if [player["slot"] for player in players] != [0, 1]:
                raise ValueError("credentials need player slots 0 and 1")
            return cls(
                seed_id=bytes.fromhex(data["seed_id"]),
                player_ids=(
                    bytes.fromhex(players[0]["player_id"]),
                    bytes.fromhex(players[1]["player_id"]),
                ),
                keys=(
                    bytes.fromhex(players[0]["key"]),
                    bytes.fromhex(players[1]["key"]),
                ),
            )
        except (KeyError, TypeError) as error:
            raise ValueError(
                f"not a credentials file: missing or malformed {error}"
            ) from error


def load_credentials(path) -> QrCredentials:
    """Credentials from a JSON file written by `golf-qr-credentials`."""
    return QrCredentials.from_manifest(json.loads(Path(path).read_text()))


#: (sub-patch suffix, assembler symbol, length) for each placeholder, in the
#: order the port lays them out.
PLACEHOLDERS = (
    ("seed_id", "QrSeedId", payload.SEED_ID_LEN),
    ("player_ids", "QrPlayerId", 2 * payload.PLAYER_ID_LEN),
    ("mac_keys", "QrMacKey", 2 * payload.KEY_LEN),
)


def placeholder_offset(symbol: str) -> int:
    """A placeholder's PRG offset in bank 2."""
    return _prg_offset(port.build().symbol(symbol), QR_BANK)


def qr_credentials_patch(credentials: QrCredentials) -> CompositePatch:
    """Write `credentials` over the fill `scorecard_qr` left in its placeholders."""
    values = {
        "seed_id": credentials.seed_id,
        "player_ids": b"".join(credentials.player_ids),
        "mac_keys": b"".join(credentials.keys),
    }
    patches = []
    for suffix, symbol, length in PLACEHOLDERS:
        data = values[suffix]
        if len(data) != length:
            raise ValueError(f"{symbol} is {length} bytes; got {len(data)}")
        patches.append(
            BytePatch(
                name=f"qr_credentials_{suffix}",
                description=f"Write {symbol} into the scorecard QR image",
                prg_offset=placeholder_offset(symbol),
                original=bytes([port.PATCH_FILL]) * length,
                patched=data,
            )
        )
    return CompositePatch(
        name="qr_credentials",
        description="Write a seed ID, player IDs and MAC keys into the scorecard QR image",
        patches=patches,
        requires=(SCORECARD_QR_PATCH,),
    )
