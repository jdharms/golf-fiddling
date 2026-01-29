"""
NES Open Tournament Golf - Packed Course Writer

Multi-bank course writing with per-hole bank lookup.
Packs 1 or 2 courses across 3 terrain banks for maximum space efficiency.
"""

from dataclasses import dataclass, field

from .compressor import GreensCompressor, TerrainCompressor
from .course_validation import CourseValidator
from .decompressor import GreensDecompressor
from .packing import int_to_bcd, pack_attributes
from .patches import COURSE2_MIRROR_PATCH, COURSE3_MIRROR_PATCH, MULTI_BANK_CODE_PATCH, PatchError
from .rom_reader import (
    HOLES_PER_COURSE,
    TABLE_DISTANCE_1,
    TABLE_DISTANCE_10,
    TABLE_DISTANCE_100,
    TABLE_FLAG_X_OFFSET,
    TABLE_FLAG_Y_OFFSET,
    TABLE_GREEN_X,
    TABLE_GREEN_Y,
    TABLE_GREENS_PTR,
    TABLE_HANDICAP,
    TABLE_PAR,
    TABLE_SCROLL_LIMIT,
    TABLE_TERRAIN_END_PTR,
    TABLE_TERRAIN_START_PTR,
    TABLE_TEE_X,
    TABLE_TEE_Y,
)
from .rom_utils import PRG_BANK_SIZE, cpu_to_prg_switched
from .rom_writer import BankOverflowError, RomWriter
from ..formats.hole_data import HoleData


# Terrain bank boundaries - each bank has lookup tables that limit the terrain region
TERRAIN_BOUNDS = {
    0: (0x8000, 0xA23E),  # Japan: 8,766 bytes
    1: (0x8000, 0xA1E6),  # US: 8,678 bytes
    2: (0x837F, 0xA554),  # UK: 8,661 bytes (note offset start)
}

# Per-hole bank table location in bank 3
# Chosen to be after typical greens data but before executable code
BANK_TABLE_CPU_ADDR = 0xA700
BANK_TABLE_SIZE = 72  # 36 holes × 2 (doubled indexing)

# Greens region boundaries in bank 3
GREENS_TABLES_SIZE = 0x1C0  # 448 bytes for decompression tables ($8000-$81BF)
GREENS_DATA_START = 0x81C0  # First byte after tables
GREENS_DATA_END = BANK_TABLE_CPU_ADDR  # Stop before bank table
GREENS_CODE_START = 0xA774  # Executable code starts here (must not overwrite)


@dataclass
class HoleCompressedData:
    """Compressed data for a single hole."""
    hole_index: int      # Global index (0-17 for 1 course, 0-35 for 2)
    terrain: bytes
    attributes: bytes
    greens: bytes


@dataclass
class BankAllocation:
    """Terrain bank allocation for a single hole."""
    hole_index: int
    bank: int            # 0, 1, or 2
    terrain_start: int   # CPU address
    terrain_end: int     # CPU address (attr start)


@dataclass
class PackedWriteStats:
    """Statistics from a packed write operation."""
    bank_usage: dict = field(default_factory=dict)     # bank -> bytes used
    bank_capacity: dict = field(default_factory=dict)  # bank -> total capacity
    bank_assignments: list = field(default_factory=list)  # hole -> bank
    terrain_bytes_per_hole: list = field(default_factory=list)
    greens_bytes_per_hole: list = field(default_factory=list)
    total_terrain_bytes: int = 0
    total_greens_bytes: int = 0
    num_courses: int = 0
    num_holes: int = 0


@dataclass
class ValidationResult:
    """Result of course validation."""
    valid: bool
    message: str
    stats: PackedWriteStats | None = None


class PackedCourseWriter:
    """
    Writes 1 or 2 courses packed across 3 terrain banks.

    Uses per-hole bank lookup instead of per-course bank lookup,
    allowing terrain data to overflow from one bank to the next.
    Requires ROM code patches for multi-bank terrain lookup.

    When 1 course is written: Holes 0-17, UK mirrors Japan (course3_mirror patch)
    When 2 courses are written: Holes 0-35, UK mirrors Japan
    """

    def __init__(self, writer: RomWriter, apply_patches: bool = True):
        """
        Create a PackedCourseWriter.

        Args:
            writer: RomWriter instance for low-level operations
            apply_patches: If True, auto-apply required patches (default True)
        """
        self.writer = writer
        self.apply_patches = apply_patches
        self.terrain_compressor = TerrainCompressor()
        self.greens_compressor = GreensCompressor()
        self.greens_decompressor: GreensDecompressor | None = None
        self.validator = CourseValidator()

    def write_courses(
        self, courses: list[list[HoleData]], verbose: bool = False
    ) -> PackedWriteStats:
        """
        Write 1 or 2 courses packed across terrain banks.

        Args:
            courses: List of 1 or 2 course hole lists (each 18 holes)
            verbose: If True, print progress messages

        Returns:
            Statistics dictionary with compression info

        Raises:
            ValueError: If courses list is empty or has more than 2 courses
            ValueError: If any course doesn't have exactly 18 holes
            BankOverflowError: If compressed data doesn't fit
            PatchError: If required patches cannot be applied
        """
        # Validate input
        if len(courses) < 1 or len(courses) > 2:
            raise ValueError(f"Expected 1 or 2 courses, got {len(courses)}")

        for i, course in enumerate(courses):
            if len(course) != HOLES_PER_COURSE:
                raise ValueError(
                    f"Course {i+1} has {len(course)} holes, expected {HOLES_PER_COURSE}"
                )

        # Ensure patches are applied
        self._ensure_patches_applied(len(courses))

        # Flatten holes into single list
        all_holes: list[HoleData] = []
        for course in courses:
            all_holes.extend(course)

        num_holes = len(all_holes)
        if verbose:
            print(f"Compressing {num_holes} holes across {len(courses)} course(s)...")

        # Compress all holes
        compressed = self._compress_all_holes(all_holes)

        # Allocate terrain to banks
        allocations = self._allocate_terrain_to_banks(compressed)

        # Write terrain data to banks
        if verbose:
            print("Writing terrain data to banks...")
        self._write_terrain_banks(compressed, allocations)

        # Write per-hole bank table
        if verbose:
            print("Writing per-hole bank table...")
        self._write_bank_table(allocations)

        # Write greens to bank 3
        if verbose:
            print("Writing greens data...")
        greens_pointers = self._write_greens_bank(compressed)

        # Update pointer tables in fixed bank
        if verbose:
            print("Updating pointer tables...")
        self._update_terrain_pointers(allocations)
        self._update_greens_pointers(greens_pointers)

        # Update metadata
        for i, hole_data in enumerate(all_holes):
            self._update_metadata(i, hole_data)

        # Calculate statistics
        stats = self._calculate_stats(compressed, allocations, len(courses))

        if verbose:
            self._print_stats(stats)

        return stats

    def validate_courses(
        self, courses: list[list[HoleData]], verbose: bool = False
    ) -> ValidationResult:
        """
        Validate that courses will fit without writing.

        Args:
            courses: List of 1 or 2 course hole lists
            verbose: If True, print validation details

        Returns:
            ValidationResult with validity status and message
        """
        try:
            # Validate input counts
            if len(courses) < 1 or len(courses) > 2:
                return ValidationResult(
                    valid=False,
                    message=f"Expected 1 or 2 courses, got {len(courses)}",
                )

            for i, course in enumerate(courses):
                if len(course) != HOLES_PER_COURSE:
                    return ValidationResult(
                        valid=False,
                        message=f"Course {i+1} has {len(course)} holes, expected {HOLES_PER_COURSE}",
                    )

            # Flatten and compress
            all_holes: list[HoleData] = []
            for course in courses:
                all_holes.extend(course)

            compressed = self._compress_all_holes(all_holes)

            # Try to allocate (this will raise if it doesn't fit)
            allocations = self._allocate_terrain_to_banks(compressed)

            # Check greens fit
            total_greens = sum(len(h.greens) for h in compressed)
            greens_available = GREENS_DATA_END - GREENS_DATA_START
            if total_greens > greens_available:
                return ValidationResult(
                    valid=False,
                    message=(
                        f"Greens data ({total_greens:,} bytes) exceeds "
                        f"available space ({greens_available:,} bytes)"
                    ),
                )

            # Calculate stats
            stats = self._calculate_stats(compressed, allocations, len(courses))

            if verbose:
                self._print_stats(stats)

            return ValidationResult(
                valid=True,
                message="Validation passed - courses will fit",
                stats=stats,
            )

        except BankOverflowError as e:
            return ValidationResult(valid=False, message=str(e))
        except Exception as e:
            return ValidationResult(valid=False, message=f"Validation error: {e}")

    def _ensure_patches_applied(self, num_courses: int) -> None:
        """Ensure required ROM patches are applied.

        Args:
            num_courses: Number of courses being written (1 or 2)
        """
        # Always apply these patches
        patches = [MULTI_BANK_CODE_PATCH, COURSE3_MIRROR_PATCH]

        # In 1-course mode, also mirror course 2 to course 1
        if num_courses == 1:
            patches.append(COURSE2_MIRROR_PATCH)

        for patch in patches:
            if patch.is_applied(self.writer):
                continue
            elif self.apply_patches and patch.can_apply(self.writer):
                patch.apply(self.writer)
                print(f"Applied patch: {patch.name}")
            elif not patch.can_apply(self.writer):
                raise PatchError(
                    f"Cannot apply required patch '{patch.name}': "
                    "ROM is in unexpected state"
                )
            else:
                raise PatchError(
                    f"Required patch '{patch.name}' not applied and "
                    "auto-apply is disabled"
                )

    def _compress_all_holes(
        self, holes: list[HoleData]
    ) -> list[HoleCompressedData]:
        """Compress terrain, attributes, and greens for all holes."""
        # Validate all holes before compressing any
        for i, hole_data in enumerate(holes):
            self.validator.validate_hole(i, hole_data)

        compressed = []

        for i, hole_data in enumerate(holes):
            # Compress terrain (only visible rows)
            terrain_compressed = self.terrain_compressor.compress(
                hole_data.terrain[: hole_data.terrain_height]
            )

            # Pack attributes
            attr_packed = pack_attributes(hole_data.attributes)

            # Compress greens
            greens_compressed = self.greens_compressor.compress(hole_data.greens)

            compressed.append(
                HoleCompressedData(
                    hole_index=i,
                    terrain=terrain_compressed,
                    attributes=attr_packed,
                    greens=greens_compressed,
                )
            )

        return compressed

    def _allocate_terrain_to_banks(
        self, compressed: list[HoleCompressedData]
    ) -> list[BankAllocation]:
        """
        Allocate holes to banks using greedy first-fit algorithm.

        Each hole's terrain + attributes must fit contiguously in a bank.
        Banks are filled in order: 0, 1, 2.
        """
        allocations: list[BankAllocation] = []

        # Track remaining space in each bank
        bank_remaining = {}
        bank_next_addr = {}
        for bank, (start, end) in TERRAIN_BOUNDS.items():
            bank_remaining[bank] = end - start
            bank_next_addr[bank] = start

        # Allocate each hole
        for hole in compressed:
            hole_size = len(hole.terrain) + len(hole.attributes)

            # Find first bank with enough space
            allocated = False
            for bank in [0, 1, 2]:
                if bank_remaining[bank] >= hole_size:
                    # Allocate to this bank
                    terrain_start = bank_next_addr[bank]
                    terrain_end = terrain_start + len(hole.terrain)

                    allocations.append(
                        BankAllocation(
                            hole_index=hole.hole_index,
                            bank=bank,
                            terrain_start=terrain_start,
                            terrain_end=terrain_end,
                        )
                    )

                    # Update bank state
                    bank_next_addr[bank] += hole_size
                    bank_remaining[bank] -= hole_size
                    allocated = True
                    break

            if not allocated:
                # Calculate total required vs available
                total_required = sum(
                    len(h.terrain) + len(h.attributes) for h in compressed
                )
                total_available = sum(
                    end - start for start, end in TERRAIN_BOUNDS.values()
                )
                raise BankOverflowError(
                    f"Hole {hole.hole_index} terrain ({hole_size} bytes) "
                    f"doesn't fit in any remaining bank space.\n"
                    f"Total required: {total_required:,} bytes, "
                    f"Total available: {total_available:,} bytes"
                )

        return allocations

    def _write_terrain_banks(
        self,
        compressed: list[HoleCompressedData],
        allocations: list[BankAllocation],
    ) -> None:
        """Write terrain and attributes to assigned banks."""
        for hole, alloc in zip(compressed, allocations):
            bank = alloc.bank
            terrain_prg = cpu_to_prg_switched(alloc.terrain_start, bank)
            attr_prg = cpu_to_prg_switched(alloc.terrain_end, bank)

            # Write terrain
            self.writer.annotate(
                f"hole {alloc.hole_index} terrain ({len(hole.terrain)} bytes, bank {bank})"
            ).write_prg(terrain_prg, hole.terrain)

            # Write attributes
            self.writer.annotate(
                f"hole {alloc.hole_index} attributes ({len(hole.attributes)} bytes, bank {bank})"
            ).write_prg(attr_prg, hole.attributes)

    def _write_bank_table(self, allocations: list[BankAllocation]) -> None:
        """
        Write per-hole bank lookup table at $A700 in bank 3.

        Table uses doubled indexing: table[hole * 2] = bank number.
        Odd-offset bytes are don't-care values (set to 0).
        """
        # Create 72-byte table (36 holes × 2)
        table = bytearray(BANK_TABLE_SIZE)

        for alloc in allocations:
            # Doubled indexing
            offset = alloc.hole_index * 2
            if offset < BANK_TABLE_SIZE:
                table[offset] = alloc.bank

        # Write to bank 3
        table_prg = cpu_to_prg_switched(BANK_TABLE_CPU_ADDR, 3)
        self.writer.annotate(
            f"per-hole bank table ({BANK_TABLE_SIZE} bytes)"
        ).write_prg(table_prg, bytes(table))

    def _write_greens_bank(
        self, compressed: list[HoleCompressedData]
    ) -> list[int]:
        """
        Write greens data for written holes to bank 3.

        Only writes greens for the holes we have compressed data for.
        With course3_mirror patch, holes 36-53 are never accessed (UK mirrors Japan),
        so we don't need to preserve or write greens for those slots.

        Returns list of 54 CPU addresses (pointers for unused holes point to hole 0).
        """
        bank = 3
        bank_start_prg = bank * PRG_BANK_SIZE
        num_new_holes = len(compressed)

        # Calculate total size needed (only for holes we're writing)
        total_size = sum(len(hole.greens) for hole in compressed)
        available_space = GREENS_DATA_END - GREENS_DATA_START

        if total_size > available_space:
            raise BankOverflowError(
                f"Greens data ({total_size:,} bytes) exceeds "
                f"available space ({available_space:,} bytes) in bank 3 "
                f"(region ${GREENS_DATA_START:04X}-${GREENS_DATA_END:04X})"
            )

        # Write greens sequentially after decompression tables
        current_addr = GREENS_DATA_START
        pointers: list[int] = []
        first_greens_addr = current_addr  # Save for unused holes

        for hole in compressed:
            pointers.append(current_addr)
            prg_offset = bank_start_prg + (current_addr - 0x8000)
            self.writer.annotate(
                f"hole {hole.hole_index} greens ({len(hole.greens)} bytes)"
            ).write_prg(prg_offset, hole.greens)
            current_addr += len(hole.greens)

        # For holes beyond what we wrote (36-53 when writing 2 courses),
        # point to hole 0's greens. These pointers are never accessed due to
        # course3_mirror patch, but having valid pointers is cleaner.
        for _ in range(num_new_holes, 54):
            pointers.append(first_greens_addr)

        return pointers

    def _update_terrain_pointers(self, allocations: list[BankAllocation]) -> None:
        """Update terrain start/end pointer tables in fixed bank."""
        for alloc in allocations:
            # Terrain start pointer
            self.writer.annotate(
                f"hole {alloc.hole_index} terrain start ptr"
            ).write_fixed_word(
                TABLE_TERRAIN_START_PTR + alloc.hole_index * 2,
                alloc.terrain_start,
            )

            # Terrain end pointer (= attribute start)
            self.writer.annotate(
                f"hole {alloc.hole_index} terrain end ptr"
            ).write_fixed_word(
                TABLE_TERRAIN_END_PTR + alloc.hole_index * 2,
                alloc.terrain_end,
            )

    def _update_greens_pointers(self, pointers: list[int]) -> None:
        """Update greens pointer table in fixed bank."""
        for hole_idx, ptr in enumerate(pointers):
            self.writer.annotate(
                f"hole {hole_idx} greens ptr"
            ).write_fixed_word(
                TABLE_GREENS_PTR + hole_idx * 2,
                ptr,
            )

    def _update_metadata(self, hole_idx: int, hole_data: HoleData) -> None:
        """Update metadata tables for a hole."""
        metadata = hole_data.metadata

        # Write par
        self.writer.annotate(f"hole {hole_idx} par").write_fixed_byte(
            TABLE_PAR + hole_idx, metadata.get("par", 4)
        )

        # Write handicap
        self.writer.annotate(f"hole {hole_idx} handicap").write_fixed_byte(
            TABLE_HANDICAP + hole_idx, metadata.get("handicap", 1)
        )

        # Write distance (BCD encoded)
        distance = metadata.get("distance", 400)
        dist_100, dist_10, dist_1 = int_to_bcd(distance)
        self.writer.annotate(f"hole {hole_idx} distance (100s)").write_fixed_byte(
            TABLE_DISTANCE_100 + hole_idx, dist_100
        )
        self.writer.annotate(f"hole {hole_idx} distance (10s)").write_fixed_byte(
            TABLE_DISTANCE_10 + hole_idx, dist_10
        )
        self.writer.annotate(f"hole {hole_idx} distance (1s)").write_fixed_byte(
            TABLE_DISTANCE_1 + hole_idx, dist_1
        )

        # Write scroll limit
        self.writer.annotate(f"hole {hole_idx} scroll limit").write_fixed_byte(
            TABLE_SCROLL_LIMIT + hole_idx, metadata.get("scroll_limit", 32)
        )

        # Write green position
        self.writer.annotate(f"hole {hole_idx} green X").write_fixed_byte(
            TABLE_GREEN_X + hole_idx, hole_data.green_x
        )
        self.writer.annotate(f"hole {hole_idx} green Y").write_fixed_byte(
            TABLE_GREEN_Y + hole_idx, hole_data.green_y
        )

        # Write tee position
        tee = metadata.get("tee", {"x": 0, "y": 0})
        self.writer.annotate(f"hole {hole_idx} tee X").write_fixed_byte(
            TABLE_TEE_X + hole_idx, tee["x"]
        )
        self.writer.annotate(f"hole {hole_idx} tee Y").write_fixed_word(
            TABLE_TEE_Y + hole_idx * 2, tee["y"]
        )

        # Write flag positions (4 per hole)
        flag_positions = metadata.get("flag_positions", [])
        for i in range(4):
            if i < len(flag_positions):
                flag = flag_positions[i]
                y_offset = flag.get("y_offset", 0)
                x_offset = flag.get("x_offset", 0)
            else:
                y_offset = 0
                x_offset = 0

            self.writer.annotate(
                f"hole {hole_idx} flag {i + 1} Y offset"
            ).write_fixed_byte(TABLE_FLAG_Y_OFFSET + hole_idx * 4 + i, y_offset)
            self.writer.annotate(
                f"hole {hole_idx} flag {i + 1} X offset"
            ).write_fixed_byte(TABLE_FLAG_X_OFFSET + hole_idx * 4 + i, x_offset)

    def _calculate_stats(
        self,
        compressed: list[HoleCompressedData],
        allocations: list[BankAllocation],
        num_courses: int,
    ) -> PackedWriteStats:
        """Calculate write statistics."""
        stats = PackedWriteStats(
            num_courses=num_courses,
            num_holes=len(compressed),
        )

        # Bank usage
        for bank in [0, 1, 2]:
            start, end = TERRAIN_BOUNDS[bank]
            stats.bank_capacity[bank] = end - start
            stats.bank_usage[bank] = 0

        # Per-hole stats
        for hole, alloc in zip(compressed, allocations):
            hole_size = len(hole.terrain) + len(hole.attributes)
            stats.bank_usage[alloc.bank] += hole_size
            stats.bank_assignments.append(alloc.bank)
            stats.terrain_bytes_per_hole.append(len(hole.terrain))
            stats.greens_bytes_per_hole.append(len(hole.greens))

        # Totals
        stats.total_terrain_bytes = sum(
            len(h.terrain) + len(h.attributes) for h in compressed
        )
        stats.total_greens_bytes = sum(len(h.greens) for h in compressed)

        return stats

    def _print_stats(self, stats: PackedWriteStats) -> None:
        """Print statistics summary."""
        print()
        print(f"Packed {stats.num_holes} holes from {stats.num_courses} course(s)")
        print()
        print("Bank usage:")
        for bank in [0, 1, 2]:
            used = stats.bank_usage.get(bank, 0)
            capacity = stats.bank_capacity.get(bank, 0)
            pct = (used / capacity * 100) if capacity > 0 else 0
            print(f"  Bank {bank}: {used:,} / {capacity:,} bytes ({pct:.1f}%)")

        total_capacity = sum(stats.bank_capacity.values())
        total_pct = (stats.total_terrain_bytes / total_capacity * 100) if total_capacity > 0 else 0
        print(f"  Total:  {stats.total_terrain_bytes:,} / {total_capacity:,} bytes ({total_pct:.1f}%)")
        print()
        print(f"Greens: {stats.total_greens_bytes:,} bytes")
