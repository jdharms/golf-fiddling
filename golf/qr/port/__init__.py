"""
The 6502 port of the scorecard QR generator — phase 4 of `docs/scorecard_qr.md`.

The assembly lives in `.s` files next to this module and is assembled by
`golf.core.asm6502` against `layout.symbols()`, so no source file hardcodes an
address and the ROM table addresses come from the phase-3 exporter itself.

`build()` returns the assembled program; `sim.Machine` runs it, which is how
every stage is differentially tested against `golf.qr` in
`tests/unit/test_qr_port.py`.
"""

from functools import lru_cache
from pathlib import Path

from golf.core.asm6502 import Program, assemble
from golf.qr import encoder, nes, payload, tables
from golf.qr.port import layout
from golf.qr.tables import CONSTANT_CODEWORDS

#: The URL prefix's length, which is what makes code words 0-27 constant.
CONSTANT_PREFIX_LEN = 26

#: CHR tile number the 16 QR tiles start at — where the display layer uploads
#: them, clear of the card font. The nametable builder adds it to every entry.
TILE_BASE = layout.TILE_BASE

#: Assembly sources, in the order they are concatenated. Order decides only
#: placement, since every reference is by label.
SOURCES = ("entry.s", "display.s", "payload.s", "hash.s", "codewords.s", "matrix.s")

_HERE = Path(__file__).parent

#: Placeholder for the per-build values the randomizer writes in at patch time.
#: Zero is deliberate: a ROM that was never patched produces an all-zero seed
#: and player ID, which the server rejects rather than silently accepting.
PATCH_FILL = 0x00


#: The scorecard font's tile numbers (docs/scorecard.md): digits `$00`-`$09`,
#: `A`-`Z` at `$0A`-`$23`, space `$24`. Every glyph is drawn in colour 2 only,
#: which is why one palette covers both the captions and the code.
def caption_tiles(text: str) -> list[int]:
    out = []
    for character in text:
        if character == " ":
            out.append(0x24)
        elif character.isdigit():
            out.append(ord(character) - ord("0"))
        elif "A" <= character <= "Z":
            out.append(0x0A + ord(character) - ord("A"))
        else:
            raise ValueError(
                f"{character!r} is not in the card font (A-Z, 0-9, space only)"
            )
    return out


#: Captions, and the rows they sit on. The player line is written as the word
#: plus a digit the routine computes from the slot, so there is one string
#: rather than two.
PLAYER_CAPTION = "PLAYER "
SCAN_CAPTION = "SCAN TO SUBMIT"
HOLD_CAPTION = "HOLD UP SELECT A"


def caption_address(row: int, width: int) -> int:
    """Nametable address that centres `width` tiles on `row`."""
    return 0x2000 + row * 32 + (32 - width) // 2


def source(name: str) -> str:
    return (_HERE / name).read_text()


def constants_source() -> str:
    """
    The parts of the source that are data rather than code: the URL prefix and
    the per-build seed, player IDs and MAC keys. Generated so the domain and
    the payload geometry live only in `golf.qr.payload`.
    """
    prefix = payload.URL_PREFIX
    if len(prefix) != CONSTANT_PREFIX_LEN:
        raise ValueError(
            f"URL prefix is {len(prefix)} characters; the constant code word "
            f"head assumes {CONSTANT_PREFIX_LEN}"
        )
    fill = f"${PATCH_FILL:02X}"
    player = caption_tiles(PLAYER_CAPTION)
    scan = caption_tiles(SCAN_CAPTION)
    hold = caption_tiles(HOLD_CAPTION)

    def byte_row(values) -> str:
        return "        .byte " + ",".join(f"${value:02X}" for value in values)

    return "\n".join(
        [
            f"QrUrlPrefixLen = {len(prefix)}",
            f"QrUrlLen = {payload.URL_LEN}",
            f"QrPayloadLen = {payload.PAYLOAD_LEN}",
            f"QrHoleCount = {payload.HOLE_COUNT}",
            f"QrConstantCodewords = {CONSTANT_CODEWORDS}",
            f"QrDataCodewordCount = {encoder.DATA_CODEWORDS}",
            f"QrDataPerBlock = {encoder.DATA_PER_BLOCK}",
            f"QrEcPerBlock = {encoder.EC_PER_BLOCK}",
            f"QrTotalCodewords = {encoder.TOTAL_CODEWORDS}",
            f"QrModuleSize = {encoder.SIZE}",
            f"QrTileCount = {nes.TILE_COUNT}",
            f"QrTileBase = {TILE_BASE}",
            f"QrMatrixPages = {layout.MATRIX_BYTES // 256}",
            f"QrMatrixTail = {layout.MATRIX_BYTES % 256}",
            f"QrMatrixRowOffset36 = {layout.MATRIX_STRIDE * (encoder.SIZE - 1)}",
            f"QrChrDest = ${layout.CHR_DEST:04X}",
            f"QrScreenBase = ${layout.SCREEN_BASE:04X}",
            f"QrPpuCtrlValue = ${layout.PPU_CTRL_VALUE:02X}",
            f"QrPpuMaskValue = ${layout.PPU_MASK_VALUE:02X}",
            f"QrDismissMask = ${layout.DISMISS_MASK:02X}",
            f"QrHoldFrames = {layout.HOLD_FRAMES}",
            f"QrPlayerTextLen = {len(player)}",
            f"QrScanTextLen = {len(scan)}",
            f"QrHoldTextLen = {len(hold)}",
            "QrPlayerCaptionAddr = "
            f"${caption_address(layout.PLAYER_CAPTION_ROW, len(player) + 1):04X}",
            "QrScanCaptionAddr = "
            f"${caption_address(layout.SCAN_CAPTION_ROW, len(scan)):04X}",
            "QrHoldCaptionAddr = "
            f"${caption_address(layout.HOLD_CAPTION_ROW, len(hold)):04X}",
            "",
            f"QrPlayerText:                   ; {PLAYER_CAPTION!r} plus the slot digit",
            byte_row(player),
            f"QrScanText:                     ; {SCAN_CAPTION!r}",
            byte_row(scan),
            f"QrHoldText:                     ; {HOLD_CAPTION!r}",
            byte_row(hold),
            "",
            "; White backdrop, black everywhere else: the QR modules are colour 1",
            "; and the card font draws in colour 2.",
            "QrPalette:",
            "\n".join(byte_row([0x30, 0x0F, 0x0F, 0x0F]) for _ in range(8)),
            "",
            "QrUrlPrefix:",
            f'        .byte "{prefix}"',
            "",
            "; Patched in per build: seed ID, then one player ID and one MAC",
            "; key per player slot.",
            "QrSeedId:",
            f"        .res {payload.SEED_ID_LEN}, {fill}",
            "QrPlayerId:",
            f"        .res {2 * payload.PLAYER_ID_LEN}, {fill}",
            "QrMacKey:",
            f"        .res {2 * payload.KEY_LEN}, {fill}",
            "",
        ]
    )


def full_source() -> str:
    parts = [f"; ===== constants =====\n{constants_source()}"]
    parts += [f"; ===== {name} =====\n{source(name)}" for name in SOURCES]
    return "\n".join(parts)


@lru_cache(maxsize=4)
def build(origin: int | None = None, mask: int | None = None) -> Program:
    """Assemble the whole routine."""
    return assemble(
        full_source(),
        layout.CODE_ORIGIN if origin is None else origin,
        layout.symbols(mask),
    )


def table_blob(mask: int | None = None) -> bytes:
    built = tables.build_tables() if mask is None else tables.build_tables(mask)
    return tables.blob(built)


def rom_bytes(mask: int | None = None) -> bytes:
    """
    Tables and code as one image, laid out from `layout.TABLE_ORIGIN`, which is
    what eventually gets written into bank 2.
    """
    program = build(mask=mask)
    blob = table_blob(mask)
    gap = program.origin - (layout.TABLE_ORIGIN + len(blob))
    if gap < 0:
        raise ValueError("code origin overlaps the table blob")
    return blob + bytes(gap) + program.code
