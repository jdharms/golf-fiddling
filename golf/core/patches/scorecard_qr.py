"""
Scorecard QR patch: draw a submission QR code when a round ends.

Phase 6 of `docs/scorecard_qr.md`. Three writes:

1. **The feature itself** — the table blob and the assembled routine from
   `golf.qr.port` — into bank 2's reclaimed region, from `$8400`. That region
   is the vacated UK course: a randomized ROM carries one course, and with
   course mirroring and menu trimming there is no way to play a round on
   course 3, so nothing reads it.

2. **A trampoline** in bank 13's tail padding (`$BF83`), ten bytes:

       JSR $85BA              ; the scorecard's own wait-for-A/B
       JSR ExecuteFarCall     ; .db $02, <QrShowCodes, >QrShowCodes
       RTS

3. **A two-byte splice**: the `JSR $85BA` at bank 13 `$852D` — the wait that
   follows the post-round scorecard — is repointed at that trampoline. `$85BA`
   is also called from `$8599` on the tournament path; only this call site
   moves.

Unlike `BytePatch`, this does not verify the bytes it overwrites. The region
write is nearly four kilobytes of vanilla course data, and carrying a copy of
that to compare against would be absurd. What it *does* verify is the splice
site itself and the six-byte far call to `DrawScorecardScreen` just above it,
which is a precise enough anchor to catch a wrong or already-modified ROM, plus
that the trampoline's ten bytes are still padding.

(A future "reclaim" patch that fills the freed region with `$FF` would let this
one assert on the region too. See the note in the doc.)
"""

import random
from dataclasses import dataclass

from golf.core.asm6502 import assemble
from golf.qr import payload, port
from golf.qr.port import layout

from .base import PatchError, ROMPatch

# --- Splice site ------------------------------------------------------------

QR_BANK = 2
HOOK_BANK = 13

#: `JSR $85BA` at bank 13 `$852D`; only its operand moves.
SPLICE_CPU_ADDR = 0x852D
SPLICE_OPERAND_CPU_ADDR = SPLICE_CPU_ADDR + 1
SCORECARD_WAIT = 0x85BA

#: The far call to `DrawScorecardScreen` immediately above the splice. Six
#: bytes that pin both the ROM version and the fact that nothing else has
#: rearranged this routine.
ANCHOR_CPU_ADDR = 0x8523
ANCHOR_BYTES = bytes([0x20, 0x72, 0xD3, 0x02, 0x76, 0xAE])

#: Bank 13 tail padding. `$BF83`-`$BFAE` is free; the seeded-wind patch's own
#: trampoline starts at `$BFAF`.
TRAMPOLINE_CPU_ADDR = 0xBF83
TRAMPOLINE_LIMIT = 0xBFAF

EXECUTE_FAR_CALL = 0xD372

PRG_BANK_SIZE = 0x4000


def _prg_offset(cpu_addr: int, bank: int) -> int:
    """A switchable-bank address as an offset into PRG, header excluded —
    which is what `RomWriter.read_prg` and `write_prg` take."""
    return bank * PRG_BANK_SIZE + (cpu_addr - 0x8000)


# --- Per-build credentials --------------------------------------------------


@dataclass(frozen=True)
class QrCredentials:
    """
    What the randomizer writes into each ROM: the seed this cartridge plays,
    and one player ID and MAC key per player slot.

    The IDs are public; **the keys are not** — they are what stops a player
    submitting a scorecard as somebody else, and they live server-side keyed to
    (seed, player).
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


def build_image(credentials: QrCredentials) -> bytes:
    """
    The bytes that go into bank 2 from `layout.TABLE_ORIGIN`: tables, then the
    routine, with this build's seed, player IDs and keys written into the
    placeholders the assembler reserved.
    """
    program = port.build()
    try:
        image = bytearray(port.rom_bytes())
    except ValueError as error:  # an origin that cannot hold the tables
        raise PatchError(str(error)) from error

    def put(symbol: str, data: bytes) -> None:
        offset = program.symbol(symbol) - layout.TABLE_ORIGIN
        if not 0 <= offset <= len(image) - len(data):
            raise PatchError(f"{symbol} is outside the image")
        image[offset : offset + len(data)] = data

    put("QrSeedId", credentials.seed_id)
    put("QrPlayerId", b"".join(credentials.player_ids))
    put("QrMacKey", b"".join(credentials.keys))
    return bytes(image)


def build_trampoline(entry: int) -> bytes:
    """The ten bytes in bank 13 that the spliced `JSR` now reaches."""
    source = f"""
        jsr ${SCORECARD_WAIT:04X}
        jsr ${EXECUTE_FAR_CALL:04X}
        .byte ${QR_BANK:02X}, ${entry & 0xFF:02X}, ${entry >> 8:02X}
        rts
    """
    return assemble(source, TRAMPOLINE_CPU_ADDR).code


# --- The patch --------------------------------------------------------------


class ScorecardQrPatch(ROMPatch):
    """Install the QR screen and hook it onto the end of a round."""

    name = "scorecard_qr"
    description = "Draw a scorecard submission QR code after the post-round scorecard"

    def __init__(self, credentials: QrCredentials):
        self.credentials = credentials
        self.image = build_image(credentials)
        self.entry = port.build().symbol("QrShowCodes")
        self.trampoline = build_trampoline(self.entry)

        end = layout.TABLE_ORIGIN + len(self.image) - 1
        if layout.TABLE_ORIGIN < layout.REGION_START or end > layout.REGION_END:
            raise PatchError(
                f"the image spans ${layout.TABLE_ORIGIN:04X}-${end:04X}, outside "
                f"the reclaimed region ${layout.REGION_START:04X}-"
                f"${layout.REGION_END:04X}"
            )
        if TRAMPOLINE_CPU_ADDR + len(self.trampoline) > TRAMPOLINE_LIMIT:
            raise PatchError("the trampoline does not fit bank 13's tail padding")

    # -- addresses --------------------------------------------------------

    @property
    def image_offset(self) -> int:
        return _prg_offset(layout.TABLE_ORIGIN, QR_BANK)

    @property
    def trampoline_offset(self) -> int:
        return _prg_offset(TRAMPOLINE_CPU_ADDR, HOOK_BANK)

    @property
    def splice_offset(self) -> int:
        return _prg_offset(SPLICE_OPERAND_CPU_ADDR, HOOK_BANK)

    @property
    def splice_bytes(self) -> bytes:
        return bytes([TRAMPOLINE_CPU_ADDR & 0xFF, TRAMPOLINE_CPU_ADDR >> 8])

    @property
    def vanilla_splice_bytes(self) -> bytes:
        return bytes([SCORECARD_WAIT & 0xFF, SCORECARD_WAIT >> 8])

    # -- ROMPatch ---------------------------------------------------------

    def can_apply(self, rom_writer) -> bool:
        """
        The splice site must be vanilla and the trampoline space still padding.
        The region the image goes into is deliberately not checked — see the
        module docstring.
        """
        anchor = rom_writer.read_prg(
            _prg_offset(ANCHOR_CPU_ADDR, HOOK_BANK), len(ANCHOR_BYTES)
        )
        if anchor != ANCHOR_BYTES:
            return False
        if rom_writer.read_prg(self.splice_offset, 2) != self.vanilla_splice_bytes:
            return False
        padding = rom_writer.read_prg(self.trampoline_offset, len(self.trampoline))
        return padding == b"\xff" * len(self.trampoline)

    def is_applied(self, rom_writer) -> bool:
        if rom_writer.read_prg(self.splice_offset, 2) != self.splice_bytes:
            return False
        return (
            rom_writer.read_prg(self.trampoline_offset, len(self.trampoline))
            == self.trampoline
        )

    def apply(self, rom_writer) -> None:
        if not self.is_applied(rom_writer) and not self.can_apply(rom_writer):
            raise PatchError(
                "the post-round scorecard call site is not where this patch "
                "expects it, or bank 13's tail padding is already in use"
            )
        rom_writer.write_prg(self.image_offset, self.image)
        rom_writer.write_prg(self.trampoline_offset, self.trampoline)
        rom_writer.write_prg(self.splice_offset, self.splice_bytes)
        rom_writer.annotate(
            f"{self.name}: {len(self.image)} bytes at bank {QR_BANK} "
            f"${layout.TABLE_ORIGIN:04X}, hooked at bank {HOOK_BANK} "
            f"${SPLICE_CPU_ADDR:04X}"
        )


def scorecard_qr_patch(credentials: QrCredentials | None = None) -> ScorecardQrPatch:
    """The patch, with fresh random credentials unless some are supplied."""
    return ScorecardQrPatch(credentials or QrCredentials.random())
