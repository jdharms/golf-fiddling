"""
Unit tests for data packing functions (inverse of decompression).
"""

import pytest

from golf.core.decompressor import bcd_to_int, unpack_attributes
from golf.core.packing import int_to_bcd, pack_attributes


class TestPackAttributes:
    """Test pack_attributes() function."""

    def test_roundtrip_simple(self):
        """Test pack/unpack roundtrip with simple data."""
        # Create simple 2x11 attribute array
        original = [[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]]

        packed = pack_attributes(original)
        unpacked = unpack_attributes(packed, len(original))

        assert unpacked == original

    def test_roundtrip_varied(self):
        """Test roundtrip with varied palette values."""
        original = [
            [0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2],
            [3, 2, 1, 0, 3, 2, 1, 0, 3, 2, 1],
            [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3],
            [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2],
        ]

        packed = pack_attributes(original)
        unpacked = unpack_attributes(packed, len(original))

        assert unpacked == original

    def test_roundtrip_real_data(self):
        """Test roundtrip with real attribute data from Japan hole 1."""
        # First 4 rows from Japan hole 1
        original = [
            [1, 1, 1, 1, 3, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 3, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 3, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 3, 1, 1, 1, 1, 1, 1],
        ]

        packed = pack_attributes(original)
        unpacked = unpack_attributes(packed, len(original))

        assert unpacked == original

    def test_odd_rows(self):
        """Test packing with odd number of rows."""
        # 3 rows (odd)
        original = [
            [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
            [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        ]

        packed = pack_attributes(original)
        unpacked = unpack_attributes(packed, len(original))

        assert unpacked == original

    def test_single_row(self):
        """Test packing single row."""
        original = [[1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]]

        packed = pack_attributes(original)
        unpacked = unpack_attributes(packed, len(original))

        assert unpacked == original

    def test_returns_72_bytes(self):
        """Test that pack_attributes always returns exactly 72 bytes."""
        original = [[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]]

        packed = pack_attributes(original)

        assert len(packed) == 72

    def test_hud_column_is_zero(self):
        """Test that HUD column (first column) is always palette 0."""
        original = [[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]]

        packed = pack_attributes(original)

        # First byte should have TL=0, TR=1 (first megatile, top row)
        # Byte format: [BR BR BL BL TR TR TL TL]
        # TL=0, TR=1 → 0b00000100 = 0x04
        first_byte = packed[0]
        top_left = first_byte & 0x03
        assert top_left == 0  # HUD column should be palette 0

    def test_empty_raises_error(self):
        """Test that empty attr_rows raises ValueError."""
        with pytest.raises(ValueError, match="attr_rows cannot be empty"):
            pack_attributes([])

    def test_wrong_column_count_raises_error(self):
        """Test that wrong column count raises ValueError."""
        original = [[1, 2, 3, 4, 5]]  # Only 5 columns, should be 11

        with pytest.raises(ValueError, match="expected 11"):
            pack_attributes(original)

    def test_invalid_palette_value_raises_error(self):
        """Test that invalid palette value raises ValueError."""
        original = [[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 4]]  # 4 is invalid (must be 0-3)

        with pytest.raises(ValueError, match="Invalid palette value"):
            pack_attributes(original)

    def test_negative_palette_value_raises_error(self):
        """Test that negative palette value raises ValueError."""
        original = [[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, -1]]  # Negative is invalid

        with pytest.raises(ValueError, match="Invalid palette value"):
            pack_attributes(original)


class TestIntToBCD:
    """Test int_to_bcd() function."""

    def test_roundtrip_zero(self):
        """Test BCD encoding roundtrip for zero."""
        value = 0
        bcd = int_to_bcd(value)
        result = bcd_to_int(*bcd)

        assert result == value

    def test_roundtrip_100(self):
        """Test BCD encoding roundtrip for 100."""
        value = 100
        bcd = int_to_bcd(value)
        result = bcd_to_int(*bcd)

        assert result == value

    def test_roundtrip_456(self):
        """Test BCD encoding roundtrip for 456."""
        value = 456
        bcd = int_to_bcd(value)
        result = bcd_to_int(*bcd)

        assert result == value

    def test_roundtrip_999(self):
        """Test BCD encoding roundtrip for 999."""
        value = 999
        bcd = int_to_bcd(value)
        result = bcd_to_int(*bcd)

        assert result == value

    def test_roundtrip_all_distances(self):
        """Test roundtrip for common golf distances."""
        for value in [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600]:
            bcd = int_to_bcd(value)
            result = bcd_to_int(*bcd)
            assert result == value, f"Failed for {value}"

    def test_encoding_456(self):
        """Test specific BCD encoding for 456."""
        hundreds, tens, ones = int_to_bcd(456)

        # 4 → 0x04, 5 → 0x05, 6 → 0x06
        assert hundreds == 0x04
        assert tens == 0x05
        assert ones == 0x06

    def test_encoding_001(self):
        """Test specific BCD encoding for 1."""
        hundreds, tens, ones = int_to_bcd(1)

        # 0 → 0x00, 0 → 0x00, 1 → 0x01
        assert hundreds == 0x00
        assert tens == 0x00
        assert ones == 0x01

    def test_encoding_090(self):
        """Test specific BCD encoding for 90."""
        hundreds, tens, ones = int_to_bcd(90)

        # 0 → 0x00, 9 → 0x09, 0 → 0x00
        assert hundreds == 0x00
        assert tens == 0x09
        assert ones == 0x00

    def test_negative_raises_error(self):
        """Test that negative value raises ValueError."""
        with pytest.raises(ValueError, match="must be 0-999"):
            int_to_bcd(-1)

    def test_1000_raises_error(self):
        """Test that 1000 raises ValueError."""
        with pytest.raises(ValueError, match="must be 0-999"):
            int_to_bcd(1000)

    def test_large_value_raises_error(self):
        """Test that large value raises ValueError."""
        with pytest.raises(ValueError, match="must be 0-999"):
            int_to_bcd(9999)
