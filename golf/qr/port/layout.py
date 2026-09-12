"""
Every address the 6502 port uses, in one place.

The assembly sources in this package are assembled with these as predefined
symbols, so nothing in the `.s` files hardcodes an address. The ROM table
addresses come straight out of `golf.qr.tables`, which means the code cannot
drift from the exported blob.
"""

from golf.qr import tables

# --------------------------------------------------------------------------
# ROM
# --------------------------------------------------------------------------

#: Where the table blob is placed in bank 2's reclaimed region
#: (`$837F`-`$A553`). Page-aligned, so the two GF tables are page-aligned.
TABLE_ORIGIN = 0x8400

#: Code follows the tables, rounded up to the next page for legibility.
_TABLE_BYTES = len(tables.blob(tables.build_tables()))
CODE_ORIGIN = (TABLE_ORIGIN + _TABLE_BYTES + 0xFF) & ~0xFF

#: The region the whole feature has to fit in.
REGION_START = 0x837F
REGION_END = 0xA553

# --------------------------------------------------------------------------
# Zero page
#
# Four pointer slots. `$50`-`$57` is the graphics decompressor's state
# (`CompressedDataPtr`, `BaseAddrCopy`, `PpuWriteAddr`, `CompressionLookbackPtr`)
# — nothing the NMI touches, and no decompression is ever in flight while this
# routine owns the CPU. The rule that goes with borrowing them: a call to the
# game's graphics routines clobbers all four, so nothing may be held across one.
# --------------------------------------------------------------------------

PTR_A = 0x50
PTR_B = 0x52
PTR_C = 0x54
PTR_D = 0x56

# --------------------------------------------------------------------------
# Game RAM the routine reads
# --------------------------------------------------------------------------

PER_HOLE_STROKES = 0x0134  # + player * 36 + hole, $FF = hole not played
PER_HOLE_PUTTS = 0x017C  # + player * 18 + hole
GAME_PROGRESS = 0x95  # holes played; $12 at the hook
PLAYER_COUNT = 0x9A  # 0 = one player, 1 = two
GOLF_GAME_MODE = 0x0100  # $00 = 18-hole stroke play

STROKE_STRIDE = 36
PUTT_STRIDE = 18

#: Held buttons, one byte per controller, refreshed by the NMI's
#: `ProcessBothControllers`. A $80, B $40, Select $20, Start $10, Up $08,
#: Down $04, Left $02, Right $01.
CONTROLLER_CURRENT = 0x14

PPU_CTRL_CACHE = 0x10  # what the NMI writes to $2000
PPU_MASK_TARGET = 0x11  # what "rendering on" restores to $2001
SCROLL_X = 0x1A
NAMETABLE_X = 0x1B
SCROLL_Y = 0x1C
NAMETABLE_Y = 0x1D

# --------------------------------------------------------------------------
# Fixed-bank routines the display layer calls
# --------------------------------------------------------------------------

WAIT_FOR_VBLANK = 0xCD74
RENDERING_OFF = 0xCDB3
RENDERING_ON = 0xCDBE
HIDE_ALL_SPRITES = 0xD291
LOAD_COMPRESSED_GRAPHICS = 0xD45F

#: The scorecard's font, already in bank 2: a graphics table whose one stream
#: lands at PPU $1000. Reloaded rather than assumed still resident.
CARD_FONT_BANK = 0x02
CARD_FONT_TABLE = 0xB469

# --------------------------------------------------------------------------
# The screen
# --------------------------------------------------------------------------

#: PPU address the 16 QR tiles are uploaded to. The background pattern table
#: is $1000, so this is tile $80 — clear of the card font's $00-$7F.
CHR_DEST = 0x1800
TILE_BASE = (CHR_DEST - 0x1000) // 16

#: Where the code sits, from `nes.SCREEN_TILE_ORIGIN` (column 7, row 5).
SCREEN_TILE_COL = 7
SCREEN_TILE_ROW = 5
SCREEN_BASE = 0x2000 + SCREEN_TILE_ROW * 32 + SCREEN_TILE_COL

#: Caption rows. Row 1 is above the code's quiet zone; 26 and 28 are below it,
#: with row 27 left blank so the two lines do not touch — the card font's
#: glyphs are seven pixels tall in an eight-pixel tile.
PLAYER_CAPTION_ROW = 1
SCAN_CAPTION_ROW = 26
HOLD_CAPTION_ROW = 28

#: Up + Select + A, held for three seconds at 60Hz.
DISMISS_MASK = 0x88 | 0x20
HOLD_FRAMES = 180

PPU_CTRL_VALUE = 0x90  # NMI on, background patterns at $1000
PPU_MASK_VALUE = 0x1E  # background and sprites, no left-column clipping

# --------------------------------------------------------------------------
# Scratch RAM
#
# SRAM `$6F9C`-`$77E5` (2,122 bytes) is inert at round end. Buffers are placed
# from `$7000` so the matrix is page-aligned; the nametable deliberately
# overlays the payload/URL/code word buffers, all of which are dead by the time
# it is built.
# --------------------------------------------------------------------------

SCRATCH_START = 0x6F9C
SCRATCH_END = 0x77E5

MATRIX = 0x7000  # 38 * 38 = 1444
MATRIX_STRIDE = tables.ROM_MATRIX_STRIDE
MATRIX_ROWS = tables.ROM_MATRIX_ROWS
MATRIX_BYTES = MATRIX_STRIDE * MATRIX_ROWS

HASH_STATE = 0x75B0  # v0..v3, 16 bytes
HASH_KEY = 0x75C0  # k0, k1, 8 bytes
HASH_TEMP = 0x75C8  # rotate scratch and loop counters, 8 bytes
TEMP = 0x75D0  # general scratch, 16 bytes

PAYLOAD = 0x75E0  # 36
URL = 0x7610  # 74
DATA_CODEWORDS = 0x7660  # 86
EC_CODEWORDS = 0x76C0  # 48
INTERLEAVED = 0x76F0  # 134

RS_REMAINDER = 0x7776  # 24, the Reed-Solomon LFSR register

#: Display-layer state. Deliberately outside `QrTemp`, which `QrBuildCode`
#: clobbers: the slot number and the hold counter have to survive it.
DISPLAY_STATE = 0x778E  # 8

#: Built from the finished matrix, after every buffer above except the matrix
#: is dead. 19 x 19 = 361 bytes.
NAMETABLE = PAYLOAD

# --------------------------------------------------------------------------
# Payload constants patched in at build time
# --------------------------------------------------------------------------

SEED_ID_LEN = 8
PLAYER_ID_LEN = 4
KEY_LEN = 8


def table_symbols(mask: int | None = None) -> dict[str, int]:
    """Every ROM table's address, keyed by its assembler label."""
    built = tables.build_tables() if mask is None else tables.build_tables(mask)
    return {
        placement.table.label: placement.address
        for placement in tables.layout(built, TABLE_ORIGIN)
        if placement.address is not None
    }


def symbols(mask: int | None = None) -> dict[str, int]:
    """The full symbol table the assembly sources are assembled against."""
    out = {
        "PtrA": PTR_A,
        "PtrB": PTR_B,
        "PtrC": PTR_C,
        "PtrD": PTR_D,
        "PerHoleStrokes": PER_HOLE_STROKES,
        "PerHolePutts": PER_HOLE_PUTTS,
        "GameProgress": GAME_PROGRESS,
        "PlayerCount": PLAYER_COUNT,
        "GolfGameMode": GOLF_GAME_MODE,
        "StrokeStride": STROKE_STRIDE,
        "PuttStride": PUTT_STRIDE,
        "QrMatrix": MATRIX,
        "QrMatrixStride": MATRIX_STRIDE,
        "QrMatrixRows": MATRIX_ROWS,
        "QrMatrixBytes": MATRIX_BYTES,
        "QrHashState": HASH_STATE,
        "QrHashKey": HASH_KEY,
        "QrHashTemp": HASH_TEMP,
        "QrTemp": TEMP,
        "QrPayload": PAYLOAD,
        "QrUrl": URL,
        "QrDataCodewords": DATA_CODEWORDS,
        "QrEcCodewords": EC_CODEWORDS,
        "QrInterleaved": INTERLEAVED,
        "QrRsRemainder": RS_REMAINDER,
        "QrNametable": NAMETABLE,
        "QrDisplayState": DISPLAY_STATE,
        "ControllerCurrent": CONTROLLER_CURRENT,
        "PpuCtrlCache": PPU_CTRL_CACHE,
        "PpuMaskTarget": PPU_MASK_TARGET,
        "ScrollX": SCROLL_X,
        "ScrollY": SCROLL_Y,
        "NametableX": NAMETABLE_X,
        "NametableY": NAMETABLE_Y,
        "PpuAddr2006": 0x2006,
        "PpuData2007": 0x2007,
        "WaitForVblank": WAIT_FOR_VBLANK,
        "RenderingOff": RENDERING_OFF,
        "RenderingOn": RENDERING_ON,
        "HideAllSprites": HIDE_ALL_SPRITES,
        "LoadCompressedGraphics": LOAD_COMPRESSED_GRAPHICS,
        "CardFontBank": CARD_FONT_BANK,
        "CardFontTable": CARD_FONT_TABLE,
    }
    out.update(table_symbols(mask))
    return out
