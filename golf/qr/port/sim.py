"""
A flat 6502 machine for running the port, so each stage can be checked against
the oracle without an emulator or a ROM.

Deliberately not an NES, but not quite bare metal either: 64K of plain memory
with the tables and code loaded where the layout says they go, plus enough of a
PPU to capture what the display layer draws (an address latch, VRAM, OAM) and
stubs for the handful of fixed-bank routines the port calls. That is what lets
`tests/unit/test_qr_display.py` decode the finished screen out of simulated
video memory rather than trusting the code that wrote it.

Anything the routine reads out of game RAM is poked in by the caller, which is
exactly the interface the real routine has.
"""

from collections.abc import Callable

from py65.devices.mpu6502 import MPU

from golf.core.asm6502 import Program, assemble
from golf.qr.port import build, layout, table_blob

#: Address the harness pushes as the return address; execution stops when the
#: routine's final RTS lands there.
SENTINEL = 0x0002

#: Instruction budget. The whole pipeline is about 106,000 instructions and
#: both players' screens under half a million, so anything past this is a
#: runaway loop rather than slow code.
DEFAULT_LIMIT = 2_000_000

#: Writing here stands in for a frame boundary — the stub for
#: `WaitForVblank` pokes it, and the harness runs its frame callback.
FRAME_TICK = 0x5FFF

#: The fixed-bank routines the port calls, stubbed at their real addresses so
#: the assembled code is byte-identical to what goes on cart.
STUB_SOURCE = """
        .org $CD74
WaitForVblank:
        pha
        lda #$01
        sta $5FFF                       ; harness frame tick
        pla
        rts

        .org $CDB3
RenderingOff:
        lda #$00
        sta $2001
        sta $12
        rts

        .org $CDBE
RenderingOn:
        lda $11
        sta $12
        sta $2001
        rts

        .org $D291
HideAllSprites:
        ldx #$00
        lda #$F0
@loop:
        sta $0200,x
        inx
        bne @loop
        rts

; Records its three inline arguments at $5FF0 and steps the return address
; past them, the way the real routine does. Decompression itself is not
; modelled: nothing the port draws depends on the card font's pixels.
        .org $D45F
LoadCompressedGraphics:
        tsx
        lda $0101,x
        sta $00
        lda $0102,x
        sta $01
        ldy #1
        lda ($00),y
        sta $5FF0
        iny
        lda ($00),y
        sta $5FF1
        iny
        lda ($00),y
        sta $5FF2
        clc
        lda $0101,x
        adc #3
        sta $0101,x
        lda $0102,x
        adc #0
        sta $0102,x
        rts
"""


class RunawayError(RuntimeError):
    """A routine did not return inside the instruction budget."""


class Bus:
    """CPU memory plus the slice of PPU behaviour the display layer uses."""

    def __init__(self) -> None:
        self.memory = bytearray(0x10000)
        self.vram = bytearray(0x4000)
        self.oam = bytearray(0x100)
        self.ppu_ctrl = 0
        self.ppu_mask = 0
        self.ppu_addr = 0
        self.scroll = [0, 0]
        self.frames = 0
        self.on_frame: Callable[[int], None] | None = None
        self._high_byte_next = True
        self._scroll_x_next = True

    # -- the CPU's view ---------------------------------------------------

    def __getitem__(self, address: int | slice) -> int | bytes:
        if isinstance(address, slice):
            return bytes(
                bytearray(
                    self._read(index) for index in range(address.start, address.stop)
                )
            )
        return self._read(address)

    def _read(self, address: int) -> int:
        if address == 0x2002:
            self._high_byte_next = True
            self._scroll_x_next = True
            return 0x80
        if address == 0x2007:
            value = self.vram[self.ppu_addr & 0x3FFF]
            self._advance()
            return value
        return self.memory[address]

    def __setitem__(self, address: int | slice, value) -> None:
        if isinstance(address, slice):
            for index, item in zip(
                range(address.start, address.stop), value, strict=True
            ):
                self[index] = item
            return
        value &= 0xFF
        if address == FRAME_TICK:
            self.frames += 1
            if self.on_frame is not None:
                self.on_frame(self.frames)
            return
        if 0x2000 <= address <= 0x3FFF:
            self._ppu_register(0x2000 + (address & 7), value)
            return
        if address == 0x4014:
            page = value << 8
            self.oam[:] = self.memory[page : page + 0x100]
            return
        self.memory[address] = value

    # -- the PPU ----------------------------------------------------------

    def _ppu_register(self, register: int, value: int) -> None:
        if register == 0x2000:
            self.ppu_ctrl = value
        elif register == 0x2001:
            self.ppu_mask = value
        elif register == 0x2005:
            self.scroll[0 if self._scroll_x_next else 1] = value
            self._scroll_x_next = not self._scroll_x_next
        elif register == 0x2006:
            if self._high_byte_next:
                self.ppu_addr = (value << 8) | (self.ppu_addr & 0xFF)
            else:
                self.ppu_addr = (self.ppu_addr & 0xFF00) | value
            self._high_byte_next = not self._high_byte_next
        elif register == 0x2007:
            self.vram[self.ppu_addr & 0x3FFF] = value
            self._advance()

    def _advance(self) -> None:
        step = 32 if self.ppu_ctrl & 0x04 else 1
        self.ppu_addr = (self.ppu_addr + step) & 0xFFFF

    # -- reading video memory back ----------------------------------------

    def nametable(self, base: int = 0x2000) -> bytes:
        return bytes(self.vram[base : base + 0x400])

    def pattern(self, base: int = 0x1800, count: int = 16) -> bytes:
        return bytes(self.vram[base : base + count * 16])

    def palette(self) -> bytes:
        return bytes(self.vram[0x3F00:0x3F20])


class Machine:
    """A loaded port, plus a way to call into it."""

    def __init__(self, program: Program | None = None, mask: int | None = None):
        self.program = build(mask=mask) if program is None else program
        self.bus = Bus()
        self.memory = self.bus.memory
        self.write(layout.TABLE_ORIGIN, table_blob(mask))
        self.write(self.program.origin, self.program.code)
        stubs = assemble(STUB_SOURCE, 0xCD74)
        self.write(stubs.origin, stubs.code)
        self.mpu = MPU(memory=self.bus)
        self.mpu.sp = 0xFD
        self.instructions = 0

    # -- memory -----------------------------------------------------------

    def write(self, address: int, data: bytes) -> None:
        self.memory[address : address + len(data)] = data

    def read(self, address: int, length: int) -> bytes:
        return bytes(self.memory[address : address + length])

    def peek(self, address: int) -> int:
        return self.memory[address]

    def poke(self, address: int, value: int) -> None:
        self.memory[address] = value & 0xFF

    # -- execution --------------------------------------------------------

    def call(
        self,
        entry: int | str,
        a: int = 0,
        x: int = 0,
        y: int = 0,
        limit: int = DEFAULT_LIMIT,
        on_frame: Callable[[int], None] | None = None,
    ) -> int:
        """
        Run a routine to its RTS. `entry` may be a label. `on_frame` is called
        each time the code waits for vblank, which is how an input sequence is
        fed to the dismissal loop. Returns the instruction count.
        """
        address = self.program.symbol(entry) if isinstance(entry, str) else entry
        self.bus.on_frame = on_frame
        mpu = self.mpu
        mpu.a, mpu.x, mpu.y = a & 0xFF, x & 0xFF, y & 0xFF
        ret = SENTINEL - 1
        mpu.memory[0x0100 + mpu.sp] = (ret >> 8) & 0xFF
        mpu.sp = (mpu.sp - 1) & 0xFF
        mpu.memory[0x0100 + mpu.sp] = ret & 0xFF
        mpu.sp = (mpu.sp - 1) & 0xFF
        mpu.pc = address

        steps = 0
        while mpu.pc != SENTINEL:
            mpu.step()
            steps += 1
            if steps > limit:
                raise RunawayError(
                    f"{entry} did not return after {limit} instructions "
                    f"(pc ${mpu.pc:04X})"
                )
        self.instructions += steps
        self.bus.on_frame = None
        return steps

    # -- convenience ------------------------------------------------------

    def set_round(
        self,
        holes: list[tuple[int, int]],
        player: int = 0,
        game_mode: int = 0,
        player_count: int = 0,
    ) -> None:
        """Stage a finished round in game RAM the way the game leaves it."""
        self.poke(layout.GAME_PROGRESS, len(holes))
        self.poke(layout.PLAYER_COUNT, player_count)
        self.poke(layout.GOLF_GAME_MODE, game_mode)
        strokes = layout.PER_HOLE_STROKES + player * layout.STROKE_STRIDE
        putts = layout.PER_HOLE_PUTTS + player * layout.PUTT_STRIDE
        for index, (stroke, putt) in enumerate(holes):
            self.poke(strokes + index, stroke)
            self.poke(putts + index, putt)

    def hold(self, buttons: int, controller: int = 0) -> None:
        """Hold a button mask on one controller, as the NMI would leave it."""
        self.poke(layout.CONTROLLER_CURRENT + controller, buttons)
