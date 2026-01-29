"""Unit tests for golf.core.rom_utils address translation functions."""

import pytest

from golf.core.rom_utils import (
    FIXED_BANK_PRG_START,
    INES_HEADER_SIZE,
    PRG_BANK_SIZE,
    cpu_to_prg_fixed,
    cpu_to_prg_switched,
    prg_to_bank_and_cpu,
    prg_to_cpu_switched,
)


class TestConstants:
    """Test ROM layout constants have expected values."""

    def test_ines_header_size(self):
        assert INES_HEADER_SIZE == 0x10

    def test_prg_bank_size(self):
        assert PRG_BANK_SIZE == 0x4000  # 16KB

    def test_fixed_bank_prg_start(self):
        assert FIXED_BANK_PRG_START == 0x3C000  # Bank 15


class TestCpuToPrgFixed:
    """Tests for cpu_to_prg_fixed() function."""

    def test_fixed_bank_start(self):
        """$C000 maps to PRG offset 0x3C000."""
        assert cpu_to_prg_fixed(0xC000) == 0x3C000

    def test_fixed_bank_end(self):
        """$FFFF maps to PRG offset 0x3FFFF."""
        assert cpu_to_prg_fixed(0xFFFF) == 0x3FFFF

    def test_mid_range_address(self):
        """Mid-range address conversion."""
        assert cpu_to_prg_fixed(0xDBBB) == 0x3C000 + (0xDBBB - 0xC000)

    def test_below_range_raises_error(self):
        """Address below $C000 raises ValueError."""
        with pytest.raises(ValueError, match="not in fixed bank range"):
            cpu_to_prg_fixed(0xBFFF)

    def test_above_range_raises_error(self):
        """Address above $FFFF raises ValueError."""
        with pytest.raises(ValueError, match="not in fixed bank range"):
            cpu_to_prg_fixed(0x10000)

    def test_switchable_bank_address_raises_error(self):
        """Address in switchable bank range raises ValueError."""
        with pytest.raises(ValueError, match="not in fixed bank range"):
            cpu_to_prg_fixed(0x8000)


class TestCpuToPrgSwitched:
    """Tests for cpu_to_prg_switched() function."""

    def test_bank_0_start(self):
        """$8000 in bank 0 maps to PRG offset 0."""
        assert cpu_to_prg_switched(0x8000, 0) == 0x0000

    def test_bank_0_end(self):
        """$BFFF in bank 0 maps to PRG offset 0x3FFF."""
        assert cpu_to_prg_switched(0xBFFF, 0) == 0x3FFF

    def test_bank_1_start(self):
        """$8000 in bank 1 maps to PRG offset 0x4000."""
        assert cpu_to_prg_switched(0x8000, 1) == 0x4000

    def test_bank_3_start(self):
        """$8000 in bank 3 maps to PRG offset 0xC000."""
        assert cpu_to_prg_switched(0x8000, 3) == 0xC000

    def test_mid_range_address(self):
        """Mid-range address in bank 2."""
        assert cpu_to_prg_switched(0x9000, 2) == 0x8000 + 0x1000

    def test_below_range_raises_error(self):
        """Address below $8000 raises ValueError."""
        with pytest.raises(ValueError, match="not in switchable bank range"):
            cpu_to_prg_switched(0x7FFF, 0)

    def test_above_range_raises_error(self):
        """Address above $BFFF raises ValueError."""
        with pytest.raises(ValueError, match="not in switchable bank range"):
            cpu_to_prg_switched(0xC000, 0)

    def test_fixed_bank_address_raises_error(self):
        """Address in fixed bank range raises ValueError."""
        with pytest.raises(ValueError, match="not in switchable bank range"):
            cpu_to_prg_switched(0xD000, 0)


class TestPrgToCpuSwitched:
    """Tests for prg_to_cpu_switched() function."""

    def test_prg_zero(self):
        """PRG offset 0 maps to $8000."""
        assert prg_to_cpu_switched(0x0000) == 0x8000

    def test_prg_mid_bank(self):
        """PRG offset within a bank maps correctly."""
        assert prg_to_cpu_switched(0x1234) == 0x9234

    def test_prg_end_of_bank(self):
        """PRG offset at end of bank maps to $BFFF."""
        assert prg_to_cpu_switched(0x3FFF) == 0xBFFF

    def test_prg_across_bank_boundary(self):
        """PRG offset in bank 1 wraps to switchable range."""
        # 0x4000 is start of bank 1, so offset within bank is 0
        assert prg_to_cpu_switched(0x4000) == 0x8000

    def test_prg_bank_3(self):
        """PRG offset in bank 3 maps correctly."""
        assert prg_to_cpu_switched(0xC123) == 0x8123


class TestPrgToBankAndCpu:
    """Tests for prg_to_bank_and_cpu() function."""

    def test_bank_0(self):
        """PRG offset in bank 0 returns (0, cpu_addr)."""
        bank, cpu_addr = prg_to_bank_and_cpu(0x0000)
        assert bank == 0
        assert cpu_addr == 0x8000

    def test_bank_1(self):
        """PRG offset in bank 1 returns (1, cpu_addr)."""
        bank, cpu_addr = prg_to_bank_and_cpu(0x4000)
        assert bank == 1
        assert cpu_addr == 0x8000

    def test_bank_2_mid_range(self):
        """PRG offset mid-bank 2 returns correct bank and address."""
        bank, cpu_addr = prg_to_bank_and_cpu(0x8500)  # Bank 2, offset 0x500
        assert bank == 2
        assert cpu_addr == 0x8500

    def test_bank_3(self):
        """PRG offset in bank 3 returns (3, cpu_addr)."""
        bank, cpu_addr = prg_to_bank_and_cpu(0xC000)
        assert bank == 3
        assert cpu_addr == 0x8000

    def test_fixed_bank(self):
        """PRG offset in fixed bank returns (15, cpu_addr)."""
        bank, cpu_addr = prg_to_bank_and_cpu(0x3C000)
        assert bank == 15
        assert cpu_addr == 0xC000

    def test_fixed_bank_end(self):
        """PRG offset at end of fixed bank."""
        bank, cpu_addr = prg_to_bank_and_cpu(0x3FFFF)
        assert bank == 15
        assert cpu_addr == 0xFFFF

    def test_fixed_bank_mid_range(self):
        """PRG offset mid-fixed bank."""
        bank, cpu_addr = prg_to_bank_and_cpu(0x3DBBB)  # TABLE_COURSE_HOLE_OFFSET
        assert bank == 15
        assert cpu_addr == 0xDBBB


class TestRoundTrips:
    """Test that conversions are invertible where applicable."""

    def test_switched_roundtrip(self):
        """cpu_to_prg_switched and prg_to_cpu_switched are partial inverses."""
        # For any CPU address in switchable range, round-trip should preserve it
        for cpu_addr in [0x8000, 0x9000, 0xA500, 0xBFFF]:
            for bank in [0, 1, 2, 3]:
                prg = cpu_to_prg_switched(cpu_addr, bank)
                recovered_cpu = prg_to_cpu_switched(prg)
                assert recovered_cpu == cpu_addr

    def test_prg_to_bank_and_cpu_to_prg_switched(self):
        """prg_to_bank_and_cpu returns values that cpu_to_prg_switched can invert."""
        # For switched banks only (not fixed bank)
        for prg_offset in [0x0000, 0x1234, 0x4000, 0x8500, 0xC000]:
            bank, cpu_addr = prg_to_bank_and_cpu(prg_offset)
            if bank != 15:  # Skip fixed bank
                recovered_prg = cpu_to_prg_switched(cpu_addr, bank)
                assert recovered_prg == prg_offset

    def test_prg_to_bank_and_cpu_fixed_to_cpu_to_prg_fixed(self):
        """prg_to_bank_and_cpu returns values that cpu_to_prg_fixed can invert."""
        for prg_offset in [0x3C000, 0x3D000, 0x3FFFF]:
            bank, cpu_addr = prg_to_bank_and_cpu(prg_offset)
            assert bank == 15
            recovered_prg = cpu_to_prg_fixed(cpu_addr)
            assert recovered_prg == prg_offset
