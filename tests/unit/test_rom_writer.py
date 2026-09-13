"""Unit tests for RomWriter's in-memory construction and write routing."""

import pytest

from golf.core.instrumented_io import InstrumentedRomWriter
from golf.core.rom_writer import RomWriter

BLANK = b"NES\x1a" + bytes([16]) + bytes(11) + bytes(16 * 0x4000)

WRITES = [
    ("write_prg", (0x100, b"\x01\x02")),
    ("write_prg_byte", (0x100, 1)),
    ("write_prg_word", (0x100, 0x0201)),
    ("write_fixed", (0xC000, b"\x01\x02")),
    ("write_fixed_byte", (0xC000, 1)),
    ("write_fixed_word", (0xC000, 0x0201)),
    ("write_switched", (0x8000, 3, b"\x01\x02")),
]


class CountingWriter(RomWriter):
    def write_prg(self, prg_offset, data):
        self.calls = getattr(self, "calls", 0) + 1
        super().write_prg(prg_offset, data)


def test_from_bytes_copies_the_data():
    data = bytearray(BLANK)
    writer = RomWriter.from_bytes(bytes(data))
    writer.write_prg(0, b"\xff")
    assert data == BLANK
    assert writer.rom_data[16] == 0xFF


def test_from_bytes_rejects_a_non_ines_file():
    with pytest.raises(ValueError, match="iNES"):
        RomWriter.from_bytes(bytes(64))


def test_save_needs_an_output_path():
    with pytest.raises(ValueError, match="no output path"):
        RomWriter.from_bytes(BLANK).save()


@pytest.mark.parametrize(("method", "args"), WRITES)
def test_every_write_goes_through_write_prg(method, args):
    writer = CountingWriter.from_bytes(BLANK)
    getattr(writer, method)(*args)
    assert writer.calls == 1


@pytest.mark.parametrize(("method", "args"), WRITES)
def test_the_instrumented_writer_logs_each_write_once(tmp_path, method, args):
    rom = tmp_path / "blank.nes"
    rom.write_bytes(BLANK)
    writer = InstrumentedRomWriter(str(rom), str(tmp_path / "out.nes"))
    getattr(writer.annotate("one write"), method)(*args)
    assert [entry["annotation"] for entry in writer.get_trace()] == ["one write"]
