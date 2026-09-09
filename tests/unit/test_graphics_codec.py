"""Unit tests for the $D4C3 graphics stream decoder.

Each literal mode and each of the three video-memory lookback modes gets a
hand-built stream, so a regression shows up as a specific mode rather than a
corrupted image somewhere downstream.
"""

import pytest

from golf.core.graphics_codec import (
    VideoMemory,
    decompress_stream,
    load_graphics_table,
)


def run(stream_bytes, dest=0x0000, prefill=None):
    """Decode a stream placed at the start of a synthetic bank."""
    bank = bytes(stream_bytes) + b"\x00" * 64
    vram = VideoMemory()
    if prefill:
        for addr, value in prefill.items():
            vram.write(addr, value)
    result = decompress_stream(bank, 0, vram, dest)
    return vram, result


class TestLiteralModes:
    def test_literal_run(self):
        vram, result = run([0x02, 0xAA, 0xBB, 0xCC, 0xFF])
        assert bytes(vram.data[0:3]) == b"\xaa\xbb\xcc"
        assert result.end_ppu_addr == 3
        assert result.compressed_length == 5

    def test_byte_run(self):
        vram, _ = run([0x22, 0x77, 0xFF])
        assert bytes(vram.data[0:4]) == b"\x77\x77\x77\x00"

    def test_two_byte_pattern_advances_by_double(self):
        vram, result = run([0x41, 0xAA, 0xBB, 0xFF])
        assert bytes(vram.data[0:4]) == b"\xaa\xbb\xaa\xbb"
        assert result.end_ppu_addr == 4

    def test_incrementing_run(self):
        vram, _ = run([0x62, 0x10, 0xFF])
        assert bytes(vram.data[0:3]) == b"\x10\x11\x12"

    def test_terminator_ends_immediately(self):
        vram, result = run([0xFF])
        assert result.compressed_length == 1
        assert not vram.touched


class TestLongForm:
    def test_long_literal(self):
        payload = list(range(100))
        vram, result = run([0xE0, 0x63] + payload + [0xFF])
        assert bytes(vram.data[0:100]) == bytes(payload)
        assert result.end_ppu_addr == 100

    def test_long_run_selects_mode_from_middle_bits(self):
        # $E4 -> (op << 3) & $E0 == $20, the run mode
        vram, result = run([0xE4, 0x0F, 0x5A, 0xFF])
        assert bytes(vram.data[0:16]) == b"\x5a" * 16
        assert result.end_ppu_addr == 16


class TestLookbackModes:
    def test_forward_copy(self):
        vram, _ = run([0x02, 0x01, 0x02, 0x03, 0x82, 0x00, 0x00, 0xFF])
        assert bytes(vram.data[0:6]) == b"\x01\x02\x03\x01\x02\x03"

    def test_copy_is_relative_to_the_stream_base(self):
        vram, _ = run([0x02, 0x01, 0x02, 0x03, 0x82, 0x00, 0x00, 0xFF], dest=0x1000)
        assert bytes(vram.data[0x1000:0x1006]) == b"\x01\x02\x03\x01\x02\x03"

    def test_bit_reversed_copy(self):
        vram, _ = run([0x01, 0x01, 0x80, 0xA1, 0x00, 0x00, 0xFF])
        # $01 -> $80, $80 -> $01
        assert bytes(vram.data[0:4]) == b"\x01\x80\x80\x01"

    def test_backwards_copy_reads_the_byte_at_the_offset_first(self):
        # $D658 rewinds by the length, then $D670/$D673 read $2007 twice, so the
        # bytes copied are mem[src-n+1 .. src] reversed - not mem[src-n .. src-1].
        vram, _ = run([0x02, 0x01, 0x02, 0x03, 0xC2, 0x00, 0x02, 0xFF])
        assert bytes(vram.data[0:6]) == b"\x01\x02\x03\x03\x02\x01"

    def test_lookback_can_read_what_an_earlier_load_left_behind(self):
        vram, _ = run(
            [0x82, 0x00, 0x00, 0xFF],
            dest=0x0100,
            prefill={0x0100: 0xDE, 0x0101: 0xAD, 0x0102: 0xBE},
        )
        assert bytes(vram.data[0x0100:0x0103]) == b"\xde\xad\xbe"


class FakeRom:
    """Just enough of RomReader for the table walker."""

    def __init__(self, bank_data):
        self.bank_data = bank_data

    def read_switched(self, cpu_addr, bank, length):
        start = cpu_addr - 0x8000
        return bytes(self.bank_data[start : start + length])


class TestGraphicsTable:
    def _bank(self, *chunks):
        bank = bytearray(0x4000)
        for offset, data in chunks:
            bank[offset : offset + len(data)] = data
        return bank

    def test_streams_chain_from_where_the_previous_one_stopped(self):
        # header at $8000: dest $0000, two streams at $8010 and $8020
        bank = self._bank(
            (0x0000, [0x00, 0x00, 0x02, 0x10, 0x80, 0x20, 0x80]),
            (0x0010, [0x02, 0x01, 0x02, 0x03, 0xFF]),
            (0x0020, [0x02, 0x04, 0x05, 0x06, 0xFF]),
        )
        table, vram = load_graphics_table(FakeRom(bank), 0, 0x8000)
        assert table.dest_ppu_addr == 0x0000
        assert [s.end_ppu_addr for s in table.streams] == [3, 6]
        assert bytes(vram.data[0:6]) == b"\x01\x02\x03\x04\x05\x06"
        assert table.end_ppu_addr == 6

    def test_compressed_length_covers_header_and_streams(self):
        bank = self._bank(
            (0x0000, [0x00, 0x10, 0x01, 0x10, 0x80]),
            (0x0010, [0x22, 0x77, 0xFF]),
        )
        table, _ = load_graphics_table(FakeRom(bank), 0, 0x8000)
        assert table.dest_ppu_addr == 0x1000
        assert table.compressed_length == 3 + 2 + 3

    def test_second_stream_can_reference_the_first(self):
        bank = self._bank(
            (0x0000, [0x00, 0x00, 0x02, 0x10, 0x80, 0x20, 0x80]),
            (0x0010, [0x02, 0x01, 0x02, 0x03, 0xFF]),
            # base is $0003, so offset $FFFD wraps back to $0000
            (0x0020, [0x82, 0xFF, 0xFD, 0xFF]),
        )
        _, vram = load_graphics_table(FakeRom(bank), 0, 0x8000)
        assert bytes(vram.data[0:6]) == b"\x01\x02\x03\x01\x02\x03"


class TestVideoMemory:
    def test_tile_decodes_two_bitplanes(self):
        vram = VideoMemory()
        vram.write(0, 0b10000000)
        vram.write(8, 0b11000000)
        rows = vram.tile(0)
        assert rows[0][0] == 3
        assert rows[0][1] == 2
        assert rows[0][2] == 0

    def test_touched_records_only_written_addresses(self):
        vram = VideoMemory()
        vram.write(0x1234, 1)
        assert vram.touched == {0x1234}

    def test_addresses_wrap_within_the_ppu_space(self):
        vram = VideoMemory()
        vram.write(0x4000, 0x42)
        assert vram.read(0x0000) == 0x42
