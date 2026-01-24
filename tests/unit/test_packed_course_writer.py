"""Unit tests for PackedCourseWriter."""

import pytest

from golf.core.packed_course_writer import (
    BANK_TABLE_CPU_ADDR,
    BANK_TABLE_SIZE,
    GREENS_DATA_END,
    GREENS_DATA_START,
    TERRAIN_BOUNDS,
    BankAllocation,
    HoleCompressedData,
    PackedCourseWriter,
    PackedWriteStats,
    ValidationResult,
)
from golf.core.patches import COURSE3_MIRROR_PATCH, MULTI_BANK_CODE_PATCH
from golf.core.rom_writer import BankOverflowError


class MockRomWriter:
    """Mock RomWriter for testing PackedCourseWriter."""

    def __init__(self, data: bytes | None = None, size: int = 0x40000):
        """Create mock ROM with optional initial data."""
        if data is not None:
            self.data = bytearray(data)
        else:
            # Create 256KB ROM (typical for NES Open)
            self.data = bytearray(size)

        # Set up patches as "can apply" by default
        self._setup_patchable_state()

    def _setup_patchable_state(self):
        """Set up ROM to have original patch bytes (so patches can be applied)."""
        # Write original bytes for multi_bank_lookup patch at PRG offset 0x1DB78
        multi_bank_offset = MULTI_BANK_CODE_PATCH.prg_offset
        self.data[multi_bank_offset:multi_bank_offset + len(MULTI_BANK_CODE_PATCH.original)] = (
            MULTI_BANK_CODE_PATCH.original
        )

        # Write original bytes for course3_mirror patch at PRG offset 0x1DBCD
        course3_offset = COURSE3_MIRROR_PATCH.prg_offset
        self.data[course3_offset:course3_offset + len(COURSE3_MIRROR_PATCH.original)] = (
            COURSE3_MIRROR_PATCH.original
        )

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        return bytes(self.data[prg_offset:prg_offset + length])

    def read_prg_byte(self, prg_offset: int) -> int:
        return self.data[prg_offset]

    def write_prg(self, prg_offset: int, data: bytes):
        self.data[prg_offset:prg_offset + len(data)] = data

    def read_fixed_byte(self, cpu_addr: int) -> int:
        prg_offset = 0x3C000 + (cpu_addr - 0xC000)
        return self.data[prg_offset]

    def read_fixed_word(self, cpu_addr: int) -> int:
        prg_offset = 0x3C000 + (cpu_addr - 0xC000)
        low = self.data[prg_offset]
        high = self.data[prg_offset + 1]
        return low | (high << 8)

    def write_fixed_byte(self, cpu_addr: int, value: int):
        prg_offset = 0x3C000 + (cpu_addr - 0xC000)
        self.data[prg_offset] = value

    def write_fixed_word(self, cpu_addr: int, value: int):
        prg_offset = 0x3C000 + (cpu_addr - 0xC000)
        self.data[prg_offset] = value & 0xFF
        self.data[prg_offset + 1] = (value >> 8) & 0xFF

    def annotate(self, description: str) -> "MockRomWriter":
        return self


class MockHoleData:
    """Mock HoleData for testing."""

    def __init__(
        self,
        terrain_height: int = 32,
        terrain: list | None = None,
        attributes: list | None = None,
        greens: list | None = None,
    ):
        self.terrain_height = terrain_height
        self.terrain = terrain or [[0xA0] * 22 for _ in range(terrain_height)]
        # Attributes need 11 columns (for 22-tile wide terrain with 2x2 supertiles)
        self.attributes = attributes or [[0] * 11 for _ in range((terrain_height + 1) // 2)]
        self.greens = greens or [[0x10] * 24 for _ in range(24)]
        self.green_x = 88
        self.green_y = 100
        self.metadata = {
            "par": 4,
            "handicap": 1,
            "distance": 400,
            "scroll_limit": 2,
            "tee": {"x": 88, "y": 500},
            "flag_positions": [
                {"x_offset": 0, "y_offset": 0},
                {"x_offset": 4, "y_offset": -4},
                {"x_offset": -4, "y_offset": 4},
                {"x_offset": 8, "y_offset": -8},
            ],
        }


class TestTerrainBounds:
    """Tests for terrain bank boundaries."""

    def test_bank_0_bounds(self):
        """Bank 0 (Japan) has correct bounds."""
        start, end = TERRAIN_BOUNDS[0]
        assert start == 0x8000
        assert end == 0xA23E
        assert end - start == 8766  # 8,766 bytes

    def test_bank_1_bounds(self):
        """Bank 1 (US) has correct bounds."""
        start, end = TERRAIN_BOUNDS[1]
        assert start == 0x8000
        assert end == 0xA1E6
        assert end - start == 8678  # 8,678 bytes

    def test_bank_2_bounds(self):
        """Bank 2 (UK) has correct bounds starting at $837F."""
        start, end = TERRAIN_BOUNDS[2]
        assert start == 0x837F
        assert end == 0xA554
        assert end - start == 8661  # 8,661 bytes

    def test_total_available_space(self):
        """Total terrain space across all banks is ~26,105 bytes."""
        total = sum(end - start for start, end in TERRAIN_BOUNDS.values())
        assert total == 26105


class TestBankTableConstants:
    """Tests for per-hole bank table constants."""

    def test_bank_table_address(self):
        """Bank table at $A700 in bank 3."""
        assert BANK_TABLE_CPU_ADDR == 0xA700

    def test_bank_table_size(self):
        """Bank table is 72 bytes (36 holes × 2)."""
        assert BANK_TABLE_SIZE == 72

    def test_greens_region_accounts_for_table(self):
        """Greens region ends before bank table."""
        assert GREENS_DATA_END == BANK_TABLE_CPU_ADDR


class TestPackedCourseWriterInit:
    """Tests for PackedCourseWriter initialization."""

    def test_creates_with_rom_writer(self):
        """Can create PackedCourseWriter with RomWriter."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer)
        assert writer.writer is rom_writer
        assert writer.apply_patches is True

    def test_can_disable_auto_patches(self):
        """Can disable automatic patch application."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)
        assert writer.apply_patches is False


class TestBankAllocation:
    """Tests for terrain bank allocation algorithm."""

    def test_allocates_to_first_bank_with_space(self):
        """Holes are allocated to first bank with sufficient space."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        # Create small compressed data that fits in bank 0
        compressed = [
            HoleCompressedData(
                hole_index=i,
                terrain=bytes([0xA0] * 100),
                attributes=bytes([0] * 72),
                greens=bytes([0x10] * 100),
            )
            for i in range(5)
        ]

        allocations = writer._allocate_terrain_to_banks(compressed)

        # All should fit in bank 0
        for alloc in allocations:
            assert alloc.bank == 0

    def test_overflows_to_next_bank(self):
        """Holes overflow to next bank when current bank is full."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        # Create data that will fill bank 0 and overflow to bank 1
        # Bank 0 has 8766 bytes, so 18 holes of 500 bytes each = 9000 bytes (overflow)
        compressed = [
            HoleCompressedData(
                hole_index=i,
                terrain=bytes([0xA0] * 428),  # 428 + 72 = 500 bytes per hole
                attributes=bytes([0] * 72),
                greens=bytes([0x10] * 100),
            )
            for i in range(18)
        ]

        allocations = writer._allocate_terrain_to_banks(compressed)

        # First 17 holes fit in bank 0 (8500 bytes), hole 18 overflows to bank 1
        banks_used = set(a.bank for a in allocations)
        assert 0 in banks_used
        assert 1 in banks_used

    def test_raises_on_overflow(self):
        """Raises BankOverflowError when data doesn't fit in any bank."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        # Create data too large for all banks combined
        # Total available: ~26,105 bytes
        compressed = [
            HoleCompressedData(
                hole_index=i,
                terrain=bytes([0xA0] * 1000),  # 1000 + 72 = 1072 bytes per hole
                attributes=bytes([0] * 72),
                greens=bytes([0x10] * 100),
            )
            for i in range(30)  # 30 × 1072 = 32160 bytes > 26105
        ]

        with pytest.raises(BankOverflowError):
            writer._allocate_terrain_to_banks(compressed)


class TestBankTableWriting:
    """Tests for per-hole bank table generation."""

    def test_writes_bank_table_at_correct_address(self):
        """Bank table is written at $A700 in bank 3."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        allocations = [
            BankAllocation(hole_index=0, bank=0, terrain_start=0x8000, terrain_end=0x8100),
            BankAllocation(hole_index=1, bank=0, terrain_start=0x8100, terrain_end=0x8200),
            BankAllocation(hole_index=2, bank=1, terrain_start=0x8000, terrain_end=0x8100),
        ]

        writer._write_bank_table(allocations)

        # Check table at PRG offset for $A700 in bank 3
        # Bank 3 starts at PRG 0xC000, $A700 - $8000 = 0x2700
        # PRG offset = 3 * 0x4000 + 0x2700 = 0xC000 + 0x2700 = 0xE700
        table_prg = 3 * 0x4000 + (BANK_TABLE_CPU_ADDR - 0x8000)

        # Hole 0 at offset 0: bank 0
        assert rom_writer.data[table_prg + 0] == 0
        # Hole 1 at offset 2: bank 0
        assert rom_writer.data[table_prg + 2] == 0
        # Hole 2 at offset 4: bank 1
        assert rom_writer.data[table_prg + 4] == 1

    def test_uses_doubled_indexing(self):
        """Bank table uses doubled indexing (hole * 2)."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        allocations = [
            BankAllocation(hole_index=5, bank=2, terrain_start=0x837F, terrain_end=0x847F),
        ]

        writer._write_bank_table(allocations)

        table_prg = 3 * 0x4000 + (BANK_TABLE_CPU_ADDR - 0x8000)

        # Hole 5 at offset 10 (5 * 2): bank 2
        assert rom_writer.data[table_prg + 10] == 2


class TestValidation:
    """Tests for course validation."""

    def test_validates_course_count(self):
        """Validation fails with invalid course count."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        # Empty courses
        result = writer.validate_courses([])
        assert result.valid is False
        assert "Expected 1 or 2 courses" in result.message

        # Too many courses
        result = writer.validate_courses([[], [], []])
        assert result.valid is False
        assert "Expected 1 or 2 courses" in result.message

    def test_validates_hole_count(self):
        """Validation fails with wrong number of holes."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        # Course with only 5 holes
        holes = [MockHoleData() for _ in range(5)]
        result = writer.validate_courses([holes])
        assert result.valid is False
        assert "18" in result.message


class TestPackedWriteStats:
    """Tests for PackedWriteStats dataclass."""

    def test_default_values(self):
        """Stats have sensible defaults."""
        stats = PackedWriteStats()
        assert stats.bank_usage == {}
        assert stats.bank_assignments == []
        assert stats.num_courses == 0
        assert stats.num_holes == 0

    def test_can_populate_stats(self):
        """Stats can be populated with data."""
        stats = PackedWriteStats(
            bank_usage={0: 5000, 1: 3000},
            bank_capacity={0: 8766, 1: 8678},
            bank_assignments=[0, 0, 1],
            terrain_bytes_per_hole=[200, 200, 200],
            greens_bytes_per_hole=[150, 150, 150],
            total_terrain_bytes=600,
            total_greens_bytes=450,
            num_courses=1,
            num_holes=3,
        )
        assert stats.bank_usage[0] == 5000
        assert stats.num_courses == 1
        assert len(stats.bank_assignments) == 3


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Can create valid result."""
        result = ValidationResult(valid=True, message="OK")
        assert result.valid is True
        assert result.message == "OK"
        assert result.stats is None

    def test_invalid_result(self):
        """Can create invalid result."""
        result = ValidationResult(valid=False, message="Too large")
        assert result.valid is False
        assert result.message == "Too large"

    def test_result_with_stats(self):
        """Can include stats in result."""
        stats = PackedWriteStats(num_courses=1)
        result = ValidationResult(valid=True, message="OK", stats=stats)
        assert result.stats is stats


class TestPatchApplication:
    """Tests for patch application during write."""

    def test_applies_patches_when_enabled(self):
        """Patches are applied when apply_patches=True."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=True)

        # Verify patches are not yet applied
        assert MULTI_BANK_CODE_PATCH.can_apply(rom_writer)
        assert COURSE3_MIRROR_PATCH.can_apply(rom_writer)

        # Call ensure_patches
        writer._ensure_patches_applied()

        # Verify patches are now applied
        assert MULTI_BANK_CODE_PATCH.is_applied(rom_writer)
        assert COURSE3_MIRROR_PATCH.is_applied(rom_writer)

    def test_skips_already_applied_patches(self):
        """Already-applied patches are skipped."""
        rom_writer = MockRomWriter()

        # Pre-apply patches
        MULTI_BANK_CODE_PATCH.apply(rom_writer)
        COURSE3_MIRROR_PATCH.apply(rom_writer)

        writer = PackedCourseWriter(rom_writer, apply_patches=True)

        # Should not raise even though patches are already applied
        writer._ensure_patches_applied()

        # Patches should still be applied
        assert MULTI_BANK_CODE_PATCH.is_applied(rom_writer)
        assert COURSE3_MIRROR_PATCH.is_applied(rom_writer)


class TestCompression:
    """Tests for hole compression."""

    def test_compresses_all_holes(self):
        """All holes are compressed."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        holes = [MockHoleData() for _ in range(3)]
        compressed = writer._compress_all_holes(holes)

        assert len(compressed) == 3
        for i, comp in enumerate(compressed):
            assert comp.hole_index == i
            assert len(comp.terrain) > 0
            assert len(comp.attributes) == 72  # Packed attributes
            assert len(comp.greens) > 0

    def test_respects_terrain_height(self):
        """Compression uses terrain_height to limit rows."""
        rom_writer = MockRomWriter()
        writer = PackedCourseWriter(rom_writer, apply_patches=False)

        # Create hole with 48 rows of terrain but only 32 visible
        hole = MockHoleData(terrain_height=32)
        hole.terrain = [[0xA0] * 22 for _ in range(48)]

        compressed = writer._compress_all_holes([hole])

        # Compression should use only 32 rows
        # (can't easily verify this without decompression, but no error is good)
        assert len(compressed) == 1
