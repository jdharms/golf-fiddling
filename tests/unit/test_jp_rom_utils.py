"""Unit tests for golf.core.jp_rom_utils constants and metadata helpers."""

from golf.core import jp_rom_utils


class FakeRom:
    """Records read_switched calls and returns canned bytes."""

    def __init__(self, data: bytes):
        self.data = data
        self.calls = []

    def read_switched(self, cpu_addr, bank, length=1):
        self.calls.append((cpu_addr, bank, length))
        return self.data[:length]


class TestConstants:
    """Spot-check documented JP table addresses."""

    def test_course_structure(self):
        assert jp_rom_utils.HOLES_PER_COURSE == 18
        assert jp_rom_utils.TOTAL_HOLES == 90
        assert len(jp_rom_utils.COURSES) == 5

    def test_metadata_bank(self):
        assert jp_rom_utils.JP_METADATA_BANK == 0x0B

    def test_attr_bytes(self):
        assert jp_rom_utils.JP_ATTR_BYTES == 90

    def test_fixed_bank_tables(self):
        assert jp_rom_utils.TABLE_COURSE_HOLE_OFFSET == 0xDC7D
        assert jp_rom_utils.TABLE_COURSE_BANK_TERRAIN == 0xDC82
        assert jp_rom_utils.TABLE_PAR == 0xDC87

    def test_switched_bank_tables(self):
        assert jp_rom_utils.TABLE_TERRAIN_START_PTR == 0xB696
        assert jp_rom_utils.TABLE_TERRAIN_END_PTR == 0xB74A
        assert jp_rom_utils.TABLE_GREENS_PTR == 0xB7FE

    def test_terrain_decompression_tables_use_jp_addresses(self):
        # Content matches US tables, but the bytes live at JP-specific
        # addresses in a JP ROM - these must not be the US addresses.
        assert jp_rom_utils.TABLE_TERRAIN_HORIZ_TRANSITION == 0xDEEE
        assert jp_rom_utils.TABLE_TERRAIN_VERT_CONTINUATION == 0xDFCE
        assert jp_rom_utils.TABLE_TERRAIN_DICTIONARY == 0xE0AE

    def test_greens_decompression_tables_in_fixed_bank(self):
        assert jp_rom_utils.TABLE_GREENS_HORIZ_TRANSITION == 0xE193
        assert jp_rom_utils.TABLE_GREENS_VERT_CONTINUATION == 0xE253
        assert jp_rom_utils.TABLE_GREENS_DICTIONARY == 0xE313


class TestReadMetadataByte:
    """Tests for read_metadata_byte()."""

    def test_reads_from_metadata_bank(self):
        rom = FakeRom(bytes([0x42]))
        value = jp_rom_utils.read_metadata_byte(rom, 0xB90C, 0)
        assert value == 0x42
        assert rom.calls == [(0xB90C, jp_rom_utils.JP_METADATA_BANK, 1)]

    def test_indexes_by_offset(self):
        rom = FakeRom(bytes([0x00]))
        jp_rom_utils.read_metadata_byte(rom, 0xB90C, 5)
        assert rom.calls == [(0xB90C + 5, jp_rom_utils.JP_METADATA_BANK, 1)]


class TestReadMetadataWord:
    """Tests for read_metadata_word()."""

    def test_little_endian_decode(self):
        rom = FakeRom(bytes([0x34, 0x12]))
        value = jp_rom_utils.read_metadata_word(rom, 0xBA1A, 0)
        assert value == 0x1234
        assert rom.calls == [(0xBA1A, jp_rom_utils.JP_METADATA_BANK, 2)]

    def test_indexes_by_word_offset(self):
        rom = FakeRom(bytes([0x00, 0x00]))
        jp_rom_utils.read_metadata_word(rom, 0xBA1A, 3)
        assert rom.calls == [(0xBA1A + 6, jp_rom_utils.JP_METADATA_BANK, 2)]
