"""Play back NES Open Tournament Golf music.

:func:`build_nsf` packages the game's audio engine (bank 14) plus the DPCM sample
page into a standard NSF, so a real player or emulator runs the original 6502
code. :func:`run_engine` executes that same code under py65 and logs every APU
register write, which is how the exporters are tested.

Both work on the US ROM and on the Japanese release, Mario Open Golf, whose
engine is the same code at shifted addresses - see :func:`discover_layout`.

See ``docs/music_format.md`` for the data format the engine reads.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from py65.devices.mpu6502 import MPU

CPU_HZ = 1789773.0
FRAME_HZ = 60.0988
FIRST_MUSIC_ID = 1
LAST_MUSIC_ID = 0x17
TRACK_COUNT = LAST_MUSIC_ID - FIRST_MUSIC_ID + 1

BANK14_OFF = 0x38000
BANK15_OFF = 0x3C000
AUDIO_ENGINE_MAIN = 0x8000

MUSIC_REQUEST = 0xF4      # $F4, see docs/music_format.md
MUSIC_SUSPEND = 0xFF      # $FF, non-zero disables the sequencer
SFX_ACTIVE = 0xFE         # $FE, gates DmcUpdate (the percussion track)


def _prg_image(rom: bytes) -> bytearray:
    """Bank 14 at $8000-$BFFF and bank 15 at $C000-$FFFF, as the engine sees them."""
    if len(rom) >= 16 and rom[:4] == b"NES\x1a":
        rom = rom[16:]
    return bytearray(rom[BANK14_OFF:BANK15_OFF] + rom[BANK15_OFF:BANK15_OFF + 0x4000])


# ------------------------------------------------------------------- ROM layout

@dataclass(frozen=True)
class MusicLayout:
    """Where the music tables live in a given ROM.

    The Japanese release (Mario Open Golf) runs the same engine as the US ROM but
    assembled at shifted addresses, so nothing can be hardcoded. Every field here is
    recovered by matching the instruction that reads the table, which is stable across
    both versions.
    """
    order_table: int
    header_bases: tuple           # ((max_music_id, base), ..., (None, default_base))
    duration_table: int
    period_table: int
    envelope_table: int
    transpose_table: int
    noise_drum_table: int
    dmc_duration_table: int
    dmc_rate_table: int
    dmc_ptr_table: int

    def header_base(self, music_id: int) -> int:
        for limit, base in self.header_bases:
            if limit is None or music_id < limit:
                return base
        raise AssertionError("header_bases must end with a default")


def _find(blk: bytes, pat) -> int:
    for i in range(len(blk) - len(pat)):
        if all(p is None or blk[i + k] == p for k, p in enumerate(pat)):
            return i
    return -1


def _operand(blk: bytes, pat, index: int, bank_base: int = 0x8000) -> int:
    i = _find(blk, pat)
    if i < 0:
        raise ValueError(f"could not locate table for pattern at index {index}")
    return blk[i + index] | (blk[i + index + 1] << 8)


def discover_layout(rom: bytes) -> MusicLayout:
    """Locate the music tables in `rom` by matching the code that reads them."""
    blk = _prg_image(rom)[:0x4000]          # bank 14
    W = None

    # the header-base chain: LDA PlayingMusicID, then CMP #limit / LDA #hi / LDX #lo
    tail = _find(blk, [0x85, 0xFD, 0x86, 0xFC, 0xB1, 0xFC])
    if tail < 0:
        raise ValueError("could not locate the pattern-header loader")
    start = max(0, tail - 64)
    rel = _find(blk[start:tail], [0xA5, 0xF9])
    if rel < 0:
        raise ValueError("could not locate the header-base selection")
    i = start + rel + 2
    bases = []
    # each block is  CMP #limit / BCS +6 / LDA #hi / LDX #lo / BNE ->done
    while blk[i] == 0xC9 and blk[i + 2] == 0xB0:
        bases.append((blk[i + 1], blk[i + 7] | (blk[i + 5] << 8)))
        i += 10
    bases.append((None, blk[i + 3] | (blk[i + 1] << 8)))       # LDA #hi / LDX #lo

    return MusicLayout(
        order_table=_operand(blk, [0xAC, W, W, 0xB9, W, W, 0x18, 0x6D, W, W,
                                   0xEE, W, W, 0xA8, 0xB9, W, W], 4),
        header_bases=tuple(bases),
        duration_table=_operand(blk, [0x29, 0x1F, 0x18, 0x6D, W, W, 0xA8, 0xB9, W, W], 8),
        period_table=_operand(blk, [0x98, 0x0A, 0xA8, 0xB9, W, W, 0x85, 0xFC], 4),
        envelope_table=_operand(blk, [0x18, 0x6D, W, W, 0xA8, 0xB9, W, W, 0xAA], 6),
        transpose_table=_operand(blk, [0xA4, 0xF9, 0xB9, W, W, 0xAE, 0xC1, 0x07], 3),
        noise_drum_table=_operand(blk, [0xB9, W, W, 0x8D, 0x0C, 0x40], 1),
        # DMC tables are indexed 1-based (and the pointer table by id*2), so the
        # operands sit one and two bytes below the tables themselves.
        dmc_duration_table=_operand(blk, [0x84, 0xF8, 0xB9, W, W, 0x8D, W, 0x07], 3) + 1,
        dmc_rate_table=_operand(blk, [0xB9, W, W, 0x8D, 0xD8, 0x07], 1) + 1,
        dmc_ptr_table=_operand(blk, [0xB9, W, W, 0x8D, 0x12, 0x40], 1) + 2,
    )


# --------------------------------------------------------------------------- NSF

# Assembled by hand; see docs/music_format.md. Lives at $D000 in its own NSF page.
_NSF_STUB = bytes([
    0xA8,                    # TAY            stash the song number
    0xA9, 0x00,              # LDA #$00
    0xAA,                    # TAX
    0x95, 0x00,              # STA $00,X      clear $0000-$00FF
    0x9D, 0x00, 0x02,        # STA $0200,X    ...and $0200-$07FF, but never the
    0x9D, 0x00, 0x03,        # STA $0300,X       stack page: INIT has to RTS
    0x9D, 0x00, 0x04,        # STA $0400,X
    0x9D, 0x00, 0x05,        # STA $0500,X
    0x9D, 0x00, 0x06,        # STA $0600,X
    0x9D, 0x00, 0x07,        # STA $0700,X
    0xE8,                    # INX
    0xD0, 0xE9,              # BNE -23
    0xA9, 0x0F,              # LDA #$0F
    0x8D, 0x15, 0x40,        # STA $4015
    0xC8,                    # INY            song 0-based -> music ID 1-based
    0x84, 0xF4,              # STY MusicRequest
    0xA9, 0x01,              # LDA #$01
    0x85, 0xFE,              # STA SfxActiveFlag   enable the DMC percussion
    0x60,                    # RTS
    0x4C, 0x00, 0x80,        # PLAY: JMP AudioEngineMain
])
_NSF_INIT_ADDR = 0xD000
_NSF_PLAY_ADDR = _NSF_INIT_ADDR + len(_NSF_STUB) - 3


def _assemble_nsf(rom, stub, init_addr, play_addr, songs, name, artist,
                  copyright_, starting_song) -> bytes:
    prg = _prg_image(rom)
    pages = [bytes(prg[i * 0x1000:(i + 1) * 0x1000]) for i in range(4)]   # bank 14
    pages.append(bytes(prg[0x4000:0x5000]))                              # $C000 DPCM page
    page = bytearray(0x1000)
    page[:len(stub)] = stub
    pages.append(bytes(page))

    def field(s: str) -> bytes:
        return s.encode("ascii", "replace")[:31].ljust(32, b"\0")

    header = bytearray(0x80)
    header[0:5] = b"NESM\x1a"
    header[5] = 1
    header[6] = songs
    header[7] = starting_song
    struct.pack_into("<HHH", header, 8, 0x8000, init_addr, play_addr)
    header[14:46] = field(name)
    header[46:78] = field(artist)
    header[78:110] = field(copyright_)
    struct.pack_into("<H", header, 110, int(round(1_000_000 / FRAME_HZ)))
    #   $8000 $9000 $A000 $B000  $C000  $D000 $E000 $F000
    header[112:120] = bytes([0, 1, 2, 3, 4, 5, 5, 5])
    struct.pack_into("<H", header, 120, 19997)   # PAL, unused
    header[122] = 0      # NTSC
    header[123] = 0      # no expansion audio
    return bytes(header) + b"".join(pages)


def build_nsf(rom: bytes, *, name: str = "NES Open Tournament Golf",
              artist: str = "", copyright_: str = "Nintendo 1991",
              starting_song: int = 1) -> bytes:
    """Package the game's audio engine as a bankswitched NSF with every track."""
    return _assemble_nsf(rom, _NSF_STUB, _NSF_INIT_ADDR, _NSF_PLAY_ADDR,
                         TRACK_COUNT, name, artist, copyright_, starting_song)


# Drum-kit NSF: one song per DPCM slot. Rather than synthesising anything, this
# hands the sample id to the game's own DmcUpdate and lets it run, so the hit --
# including the frame-counter cut-off -- is byte-for-byte what plays in game.
_DRUM_STUB = bytes([
    0xA8,                    # INIT: TAY        stash the song number
    0xA9, 0x00,              # LDA #$00
    0xAA,                    # TAX
    0x95, 0x00,              # STA $00,X        clear RAM, never the stack page
    0x9D, 0x00, 0x02,        # STA $0200,X
    0x9D, 0x00, 0x03,        # STA $0300,X
    0x9D, 0x00, 0x04,        # STA $0400,X
    0x9D, 0x00, 0x05,        # STA $0500,X
    0x9D, 0x00, 0x06,        # STA $0600,X
    0x9D, 0x00, 0x07,        # STA $0700,X
    0xE8,                    # INX
    0xD0, 0xE9,              # BNE -23
    0xA9, 0x0F,              # LDA #$0F
    0x8D, 0x15, 0x40,        # STA $4015
    0xC8,                    # INY              song 0-based -> sample id 1-10
    0x8C, 0x00, 0x03,        # STY $0300        remember which sample
    0xB9, 0x47, 0xD0,        # LDA $D047,Y      rate index (samples 1-3 only)
    0x8D, 0xD8, 0x07,        # STA $07D8
    0xA9, 0x80,              # LDA #$80
    0x85, 0xF4,              # STA MusicRequest stop the music
    0xA9, 0x01,              # LDA #$01
    0x85, 0xFE,              # STA SfxActiveFlag  so DmcUpdate runs
    0x8D, 0x01, 0x03,        # STA $0301        counter = 1: hit on the first frame
    0x60,                    # RTS
    0xCE, 0x01, 0x03,        # PLAY: DEC $0301
    0xD0, 0x0A,              # BNE +10
    0xA9, 0x30,              # LDA #48          frames between hits
    0x8D, 0x01, 0x03,        # STA $0301
    0xAD, 0x00, 0x03,        # LDA $0300
    0x85, 0xF3,              # STA DmcSampleRequest
    0x4C, 0x00, 0x80,        # JMP AudioEngineMain
    #    1     2     3   (4-10 get their rate from DmcSampleRateTable instead)
    0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])
_DRUM_INIT_ADDR = 0xD000
_DRUM_PLAY_ADDR = _DRUM_INIT_ADDR + 0x36


def build_drum_nsf(rom: bytes, *, name: str = "NES Open Golf drum kit",
                   artist: str = "", copyright_: str = "Nintendo 1991") -> bytes:
    """An NSF with one song per DPCM drum slot, played by the game's own engine."""
    return _assemble_nsf(rom, _DRUM_STUB, _DRUM_INIT_ADDR, _DRUM_PLAY_ADDR,
                         DMC_SAMPLE_COUNT, name, artist, copyright_, 1)


# ------------------------------------------------------------------- emulation

class _Bus:
    """Enough of an NES bus to run the audio engine: RAM, APU registers, PRG."""

    def __init__(self, prg: bytearray):
        self.ram = bytearray(0x800)
        self.prg = prg
        self.writes: list[tuple[int, int, int]] = []
        self.frame = 0

    def __getitem__(self, a):
        if isinstance(a, slice):
            return bytes(self[i] for i in range(a.start, a.stop))
        if a < 0x2000:
            return self.ram[a & 0x7FF]
        if a >= 0x8000:
            return self.prg[a - 0x8000]
        return 0

    def __setitem__(self, a, v):
        if isinstance(a, slice):
            for i, val in zip(range(a.start, a.stop), v):
                self[i] = val
            return
        v &= 0xFF
        if a < 0x2000:
            self.ram[a & 0x7FF] = v
        elif 0x4000 <= a <= 0x4017:
            self.writes.append((self.frame, a, v))


def _call(mpu: MPU, addr: int, limit: int = 2_000_000) -> None:
    sentinel = 0x0002
    ret = sentinel - 1
    mpu.memory[0x0100 + mpu.sp] = (ret >> 8) & 0xFF
    mpu.sp = (mpu.sp - 1) & 0xFF
    mpu.memory[0x0100 + mpu.sp] = ret & 0xFF
    mpu.sp = (mpu.sp - 1) & 0xFF
    mpu.pc = addr
    steps = 0
    while mpu.pc != sentinel:
        mpu.step()
        steps += 1
        if steps > limit:
            raise RuntimeError(f"audio engine ran away at ${mpu.pc:04X}")


def run_engine(rom: bytes, music_id: int, frames: int, *, dmc: bool = True):
    """Run AudioEngineMain for ``frames`` frames; return the APU write log."""
    prg = _prg_image(rom)
    bus = _Bus(prg)
    mpu = MPU(memory=bus)
    mpu.sp = 0xFD
    bus.ram[MUSIC_REQUEST] = music_id
    bus.ram[MUSIC_SUSPEND] = 0
    bus.ram[SFX_ACTIVE] = 1 if dmc else 0
    for f in range(frames):
        bus.frame = f
        _call(mpu, AUDIO_ENGINE_MAIN)
    return bus.writes


# --------------------------------------------------------------------- DPCM kit

DMC_DURATION_TABLE = 0x8DCB   # frames the engine lets a sample run, indexed 1-10
DMC_RATE_TABLE = 0x8DD5       # $4010 value, used only for samples 4-10
DMC_PTR_TABLE = 0x8DDF        # address/length byte pairs
DMC_SAMPLE_COUNT = 10

# Samples 1-3 take their rate from the low nibble of the stream byte instead of
# DMC_RATE_TABLE, so they have no single "correct" pitch. These are the values the
# game's own music uses most often, i.e. how each is normally heard.
DMC_DEFAULT_RATE_INDEX = {1: 2, 2: 0, 3: 0}


def dmc_sample_info(rom, sample_id: int) -> dict:
    """Address, length, run time and playback rate of one built-in DPCM sample."""
    if not 1 <= sample_id <= DMC_SAMPLE_COUNT:
        raise ValueError(f"sample id {sample_id} out of range 1-{DMC_SAMPLE_COUNT}")
    prg = _prg_image(rom)
    at = lambda cpu: prg[cpu - 0x8000]
    i = sample_id - 1
    addr = 0xC000 + at(DMC_PTR_TABLE + i * 2) * 64
    length = at(DMC_PTR_TABLE + i * 2 + 1) * 16 + 1
    frames = at(DMC_DURATION_TABLE + i)
    if sample_id >= 4:
        rate_index = at(DMC_RATE_TABLE + i) & 0x0F
    else:
        rate_index = DMC_DEFAULT_RATE_INDEX[sample_id]
    return dict(address=addr, length=length, frames=frames, rate_index=rate_index)
