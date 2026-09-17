"""
Decoder for the game's compressed graphics streams (`$D4C3` in the fixed bank).

Every pixel the game displays arrives through this codec: the cartridge has no
CHR ROM (mapper 1, `CHR 8KB banks: 0`), so pattern data, nametables and
attribute tables are all decompressed into video memory at runtime.  Roughly a
third of the 256KB PRG is data in this format.

A *graphics table* is the unit the game points at.  `LD494_DecompressGraphicsTable`
(`$D494`) reads its header and feeds each stream to the decompressor::

    dest_lo, dest_hi     ; starting PPU address
    count                ; number of streams
    ptr_lo, ptr_hi       ; x count

Two details are easy to get wrong and produce plausible-looking corruption
rather than an obvious failure:

1. **Streams chain.**  `$54`/`$55` carries over between streams of one table, so
   stream N starts where stream N-1 stopped, and `$52`/`$53` - the base that
   lookback offsets are relative to - is re-latched from it for each stream.

2. **The backwards-lookback mode reads `$2007` twice** before its copy loop
   (`$D670` and `$D673`) where the forward modes read it once.  It therefore
   copies ``mem[src-n+1 .. src]`` reversed, not ``mem[src-n .. src-1]``.

Opcode layout, decoded from `$D4CB`-`$D505`:

===========  ==================================================================
Short form   ``mode | (length-1)``, one byte, length 1-32, any mode but ``$E0``
Long form    ``$E0 | (mode >> 3) | (length >> 8)`` then ``length & $FF``,
             two bytes, length 1-1024
===========  ==================================================================

Modes:

=======  ======================================================================
``$00``  literal - ``length`` bytes follow
``$20``  run - one byte, repeated
``$40``  two-byte pattern - two bytes, ``length`` pairs (advances ``2*length``)
``$60``  incrementing run - one byte, then +1 each step
``$80``  copy ``length`` bytes already in video memory at ``base + offset``
``$A0``  same, bit-reversing each byte (a horizontal tile flip)
``$C0``  same, reading backwards (a vertical tile flip)
=======  ======================================================================
"""

from dataclasses import dataclass, field

VRAM_SIZE = 0x4000

_BIT_REVERSE = bytes(
    int(f"{value:08b}"[::-1], 2) for value in range(256)
)


class VideoMemory:
    """The PPU address space as the decompressor sees it.

    Writes go through `$2007`, so the lookback modes can only reference bytes
    that were written earlier - including by earlier streams of the same table,
    or by an earlier table load.  `touched` records which addresses a decode
    actually wrote, which is what lets callers measure a blob's real extent.
    """

    def __init__(self) -> None:
        self.data = bytearray(VRAM_SIZE)
        self.touched: set[int] = set()

    def read(self, addr: int) -> int:
        return self.data[addr & (VRAM_SIZE - 1)]

    def write(self, addr: int, value: int) -> None:
        addr &= VRAM_SIZE - 1
        self.data[addr] = value
        self.touched.add(addr)

    def tile(self, index: int, base: int = 0x0000) -> list[list[int]]:
        """Return one 8x8 pattern as rows of 2-bit colour indices."""
        origin = base + index * 16
        rows = []
        for y in range(8):
            low = self.data[origin + y]
            high = self.data[origin + 8 + y]
            rows.append(
                [
                    ((low >> (7 - x)) & 1) | (((high >> (7 - x)) & 1) << 1)
                    for x in range(8)
                ]
            )
        return rows


@dataclass
class StreamResult:
    """One decompressed stream."""

    cpu_addr: int
    compressed_length: int
    end_ppu_addr: int


@dataclass
class GraphicsTable:
    """A decoded graphics table and everything its streams wrote."""

    bank: int
    cpu_addr: int
    dest_ppu_addr: int
    streams: list[StreamResult] = field(default_factory=list)

    @property
    def compressed_length(self) -> int:
        """Header plus every stream."""
        return 3 + 2 * len(self.streams) + sum(s.compressed_length for s in self.streams)

    @property
    def end_ppu_addr(self) -> int:
        return self.streams[-1].end_ppu_addr if self.streams else self.dest_ppu_addr


def decompress_stream(
    bank_data: bytes, offset: int, vram: VideoMemory, dest: int
) -> StreamResult:
    """Decode one stream into `vram`, starting at PPU address `dest`.

    `bank_data` is a whole 16KB bank; `offset` is the stream's index into it.
    """
    start = offset
    base = dest
    ppu = dest
    pos = offset

    while True:
        op = bank_data[pos]
        if op == 0xFF:
            return StreamResult(0, pos + 1 - start, ppu)

        if (op & 0xE0) == 0xE0:
            mode = (op << 3) & 0xE0
            length = (((op & 0x03) << 8) | bank_data[pos + 1]) + 1
            pos += 2
        else:
            mode = op & 0xE0
            length = (op & 0x1F) + 1
            pos += 1

        if not mode & 0x80:
            if mode == 0x00:
                for i in range(length):
                    vram.write(ppu + i, bank_data[pos + i])
                pos += length
                written = length
            elif mode == 0x20:
                value = bank_data[pos]
                pos += 1
                for i in range(length):
                    vram.write(ppu + i, value)
                written = length
            elif mode == 0x40:
                first, second = bank_data[pos], bank_data[pos + 1]
                pos += 2
                for i in range(length):
                    vram.write(ppu + 2 * i, first)
                    vram.write(ppu + 2 * i + 1, second)
                written = length * 2
            else:  # $60
                value = bank_data[pos]
                pos += 1
                for i in range(length):
                    vram.write(ppu + i, (value + i) & 0xFF)
                written = length
            ppu = (ppu + written) & 0xFFFF
            continue

        # Lookback modes.  The source is an offset from this stream's base.
        offset16 = (bank_data[pos] << 8) | bank_data[pos + 1]
        pos += 2
        src = (base + offset16) & 0xFFFF

        # $D5B3 splits the length the same way the ROM does: a low byte of zero
        # borrows from the high byte, and each pass copies 256 bytes until the
        # last one.
        low, high = length & 0xFF, (length >> 8) & 0xFF
        if low == 0:
            high = (high - 1) & 0xFF
        for _ in range(high + 1):
            count = 256 if high else (low or 256)
            if mode == 0xC0:
                chunk = [vram.read(src - i) for i in range(count)]
                src = (src - count) & 0xFFFF
            else:
                chunk = [vram.read(src + i) for i in range(count)]
                src = (src + 0x100) & 0xFFFF
            if mode == 0xA0:
                chunk = [_BIT_REVERSE[b] for b in chunk]
            for i, value in enumerate(chunk):
                vram.write(ppu + i, value)
            ppu = (ppu + count) & 0xFFFF
            high -= 1


def load_graphics_table(
    rom, bank: int, cpu_addr: int, vram: VideoMemory | None = None
) -> tuple[GraphicsTable, VideoMemory]:
    """Decode the table at `cpu_addr` in `bank` into `vram`.

    Pass an existing `vram` to layer several tables the way the game does -
    the lookback modes can reference whatever an earlier table already wrote.
    """
    if vram is None:
        vram = VideoMemory()

    bank_data = rom.read_switched(0x8000, bank, 0x4000)
    header = cpu_addr - 0x8000
    dest = bank_data[header] | (bank_data[header + 1] << 8)
    count = bank_data[header + 2]

    table = GraphicsTable(bank=bank, cpu_addr=cpu_addr, dest_ppu_addr=dest)
    cursor = dest
    for i in range(count):
        ptr = (
            bank_data[header + 3 + 2 * i] | (bank_data[header + 4 + 2 * i] << 8)
        )
        result = decompress_stream(bank_data, ptr - 0x8000, vram, cursor)
        result.cpu_addr = ptr
        table.streams.append(result)
        cursor = result.end_ppu_addr
    return table, vram
