"""
Scorecard QR patch: draw a submission QR code when a round ends.

Phase 6 of `docs/scorecard_qr.md`. Three writes:

1. **The feature itself** — the table blob and the assembled routine from
   `golf.qr.port` — into bank 2's reclaimed region, from `$8400`. That region
   is the vacated UK course: a randomized ROM carries one course, and with
   course mirroring and menu trimming there is no way to play a round on
   course 3, so nothing reads it. The seed ID, player ID and MAC key
   placeholders (`QrSeedId`, `QrPlayerId`, `QrMacKey`) are left holding
   `port.PATCH_FILL`.

2. **A trampoline** in the fixed bank at `$DCBD`, ten bytes:

       JSR $85BA              ; the scorecard's own wait-for-A/B
       JSR ExecuteFarCall     ; .db $02, <QrShowCodes, >QrShowCodes
       RTS

   `$DCBD` is slot 18 of `GreenCompressedDataPtrTable` (`$DC99`). Its only
   reader is hole setup (`$DAF1`/`$DAF6`, indexed by the doubled hole index),
   and under `COURSE_MIRRORS_PATCH` every course slot plays holes 0-17, so
   slots 18-53 (`$DCBD`-`$DD04`) are never read. The patch requires the
   mirrors for that reason. The fixed bank is always mapped, so the bank 13
   `JSR` reaches it.

3. **A two-byte splice**: the `JSR $85BA` at bank 13 `$852D` — the wait that
   follows the post-round scorecard — is repointed at that trampoline. `$85BA`
   is also called from `$8599` on the tournament path; only this call site
   moves.

The image carries no credentials because a randomized ROM is built in two
stages (`docs/randomizer_devplan.md`): this patch belongs to the unfinished
ROM built once per seed, and one of two companions finishes it per download.

- `qr_credentials` (`golf/core/patches/qr_credentials.py`) writes a player's
  seed ID, player IDs and MAC keys over the fill.
- `QR_DISABLE_PATCH` (`qr_disable`) puts the splice back to `JSR $85BA` for a
  guest ROM, so the QR screen never appears. Its expected original is the
  splice this patch wrote, so it can only follow it. Afterwards this patch
  reports neither applied (the splice is vanilla) nor applicable (the
  trampoline is not), so it cannot be re-applied to a guest ROM.

Both rewrite bytes this patch wrote, so neither can share a `PatchStack` with
it; they run in the finishing stack on top of the unfinished ROM.

Unlike `BytePatch`, this does not verify the bytes it overwrites in bank 2. The
region write is nearly four kilobytes of vanilla course data, and carrying a
copy of that to compare against would be absurd. What it *does* verify is the
splice site itself and the six-byte far call to `DrawScorecardScreen` just
above it, which is a precise enough anchor to catch a wrong or already-modified
ROM, plus that the trampoline's ten bytes still hold the vanilla greens
pointers.

(A future "reclaim" patch that fills the freed region with `$FF` would let this
one assert on the region too. See the note in the doc.)
"""

from golf.core import rom_utils
from golf.core.asm6502 import assemble
from golf.qr import port
from golf.qr.port import layout

from .base import PatchError, ROMPatch
from .byte_patch import BytePatch
from .multi_bank import COURSE_MIRRORS_PATCH

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

#: Greens pointer slots 18-53, dead under the course mirrors: from slot 18 up
#: to the par table that follows.
TRAMPOLINE_CPU_ADDR = rom_utils.TABLE_GREENS_PTR + 18 * 2
TRAMPOLINE_LIMIT = rom_utils.TABLE_PAR

#: The vanilla UK greens pointers (slots 18-22) the trampoline replaces.
TRAMPOLINE_VANILLA = bytes([0x77, 0x8D, 0x11, 0x8E, 0x01, 0x8F, 0xDE, 0x8F, 0xBF, 0x90])

EXECUTE_FAR_CALL = 0xD372

PRG_BANK_SIZE = 0x4000


def _prg_offset(cpu_addr: int, bank: int) -> int:
    """A switchable-bank address as an offset into PRG, header excluded —
    which is what `RomWriter.read_prg` and `write_prg` take."""
    return bank * PRG_BANK_SIZE + (cpu_addr - 0x8000)


def build_trampoline(entry: int) -> bytes:
    """The ten bytes in the fixed bank that the spliced `JSR` now reaches."""
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
    requires = (COURSE_MIRRORS_PATCH,)

    def __init__(self) -> None:
        try:
            self.image = port.rom_bytes()
        except ValueError as error:  # an origin that cannot hold the tables
            raise PatchError(str(error)) from error
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
            raise PatchError(
                "the trampoline does not fit the dead greens pointer slots"
            )
        if len(self.trampoline) != len(TRAMPOLINE_VANILLA):
            raise PatchError(
                f"the trampoline is {len(self.trampoline)} bytes; update "
                "TRAMPOLINE_VANILLA to the vanilla bytes it now covers"
            )

    # -- addresses --------------------------------------------------------

    @property
    def image_offset(self) -> int:
        return _prg_offset(layout.TABLE_ORIGIN, QR_BANK)

    @property
    def trampoline_offset(self) -> int:
        return rom_utils.cpu_to_prg_fixed(TRAMPOLINE_CPU_ADDR)

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
        The splice site must be vanilla and the trampoline's slots must still
        hold the vanilla greens pointers. The region the image goes into is
        deliberately not checked — see the module docstring.
        """
        anchor = rom_writer.read_prg(
            _prg_offset(ANCHOR_CPU_ADDR, HOOK_BANK), len(ANCHOR_BYTES)
        )
        if anchor != ANCHOR_BYTES:
            return False
        if rom_writer.read_prg(self.splice_offset, 2) != self.vanilla_splice_bytes:
            return False
        return (
            rom_writer.read_prg(self.trampoline_offset, len(self.trampoline))
            == TRAMPOLINE_VANILLA
        )

    def is_applied(self, rom_writer) -> bool:
        if rom_writer.read_prg(self.splice_offset, 2) != self.splice_bytes:
            return False
        return (
            rom_writer.read_prg(self.trampoline_offset, len(self.trampoline))
            == self.trampoline
        )

    def apply(self, rom_writer) -> None:
        self.check_requirements(rom_writer)
        if not self.is_applied(rom_writer) and not self.can_apply(rom_writer):
            raise PatchError(
                "the post-round scorecard call site is not where this patch "
                "expects it, or the greens pointer slots it reuses are already in use"
            )
        rom_writer.write_prg(self.image_offset, self.image)
        rom_writer.write_prg(self.trampoline_offset, self.trampoline)
        rom_writer.write_prg(self.splice_offset, self.splice_bytes)
        rom_writer.annotate(
            f"{self.name}: {len(self.image)} bytes at bank {QR_BANK} "
            f"${layout.TABLE_ORIGIN:04X}, hooked at bank {HOOK_BANK} "
            f"${SPLICE_CPU_ADDR:04X}"
        )


SCORECARD_QR_PATCH = ScorecardQrPatch()

#: For a guest ROM: the splice back to the vanilla scorecard wait, so the round
#: ends on the scorecard and the QR screen is never reached. The image and the
#: trampoline stay, unreachable.
QR_DISABLE_PATCH = BytePatch(
    name="qr_disable",
    description="Revert the round-end splice so the QR screen never appears (guest ROMs)",
    prg_offset=SCORECARD_QR_PATCH.splice_offset,
    original=SCORECARD_QR_PATCH.splice_bytes,
    patched=SCORECARD_QR_PATCH.vanilla_splice_bytes,
)
