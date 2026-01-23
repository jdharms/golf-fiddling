"""
NES Open Tournament Golf - Course Writer

High-level course data writing with compression and pointer management.
Uses RomWriter for low-level byte operations.
"""

from .compressor import GreensCompressor, TerrainCompressor
from .decompressor import GreensDecompressor
from .packing import int_to_bcd, pack_attributes
from .rom_reader import (
    COURSES,
    HOLES_PER_COURSE,
    PRG_BANK_SIZE,
    TABLE_COURSE_BANK_TERRAIN,
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
from .rom_writer import BankOverflowError, RomWriter
from ..formats.hole_data import HoleData


# Greens decompress to 24x24 = 576 tiles
GREENS_TOTAL_TILES = 576


def find_actual_greens_size(
    compressed_data: bytes, decompressor: GreensDecompressor, max_size: int = 400
) -> int:
    """
    Find the actual compressed size of greens data by binary search.

    The game's decompressor reads until it fills a 24x24 buffer (576 tiles),
    so we need to find exactly how many compressed bytes produce that.

    Args:
        compressed_data: Buffer containing compressed greens (may have extra bytes)
        decompressor: GreensDecompressor instance
        max_size: Maximum size to search (default 400, typical greens are 150-250)

    Returns:
        Exact number of compressed bytes needed to decompress to 576 tiles
    """
    max_size = min(max_size, len(compressed_data))

    # Binary search for minimum bytes needed
    lo, hi = 1, max_size
    while lo < hi:
        mid = (lo + hi) // 2
        try:
            result = decompressor.decompress(compressed_data[:mid])
            total_tiles = sum(len(row) for row in result)
            if total_tiles >= GREENS_TOTAL_TILES:
                hi = mid
            else:
                lo = mid + 1
        except Exception:
            lo = mid + 1

    return lo


class CourseWriter:
    """
    Writes course data to ROM with compression and pointer management.

    This is the high-level class that handles compression, bank allocation,
    and pointer updates. It delegates all byte-level operations to a RomWriter.
    """

    def __init__(self, writer: RomWriter):
        """
        Create a CourseWriter.

        Args:
            writer: RomWriter instance for low-level operations
        """
        self.writer = writer
        self.terrain_compressor = TerrainCompressor()
        self.greens_compressor = GreensCompressor()
        self.greens_decompressor: GreensDecompressor | None = None

    def write_course(self, course_idx: int, hole_data_list: list[HoleData]) -> dict:
        """
        Write complete course (18 holes) to ROM.

        Args:
            course_idx: Course index (0=Japan, 1=US, 2=UK)
            hole_data_list: List of 18 HoleData objects

        Returns:
            Statistics dictionary with compression info

        Raises:
            ValueError: If hole_data_list doesn't have exactly 18 holes
            BankOverflowError: If compressed data doesn't fit in bank
        """
        if len(hole_data_list) != HOLES_PER_COURSE:
            raise ValueError(
                f"Expected {HOLES_PER_COURSE} holes, got {len(hole_data_list)}"
            )

        course = COURSES[course_idx]
        hole_offset = course_idx * HOLES_PER_COURSE  # Absolute hole index

        # Read terrain bank from course metadata
        terrain_bank = self.writer.annotate(
            f"course {course_idx} terrain bank"
        ).read_fixed_byte(TABLE_COURSE_BANK_TERRAIN + course_idx)
        greens_bank = 3  # Greens always in bank 3

        print(
            f"Writing {course['display_name']} course "
            f"(terrain bank {terrain_bank}, greens bank {greens_bank})..."
        )

        # Compress all terrain and greens data
        compressed_data = []
        for hole_idx, hole_data in enumerate(hole_data_list):
            # Compress terrain
            terrain_compressed = self.terrain_compressor.compress(
                hole_data.terrain[: hole_data.terrain_height]
            )

            # Pack attributes
            attr_packed = pack_attributes(hole_data.attributes)

            # Compress greens
            greens_compressed = self.greens_compressor.compress(hole_data.greens)

            compressed_data.append(
                {
                    "terrain": terrain_compressed,
                    "attributes": attr_packed,
                    "greens": greens_compressed,
                    "hole_data": hole_data,
                }
            )

        # Write terrain bank (defragmented)
        terrain_pointers = self._write_terrain_bank(
            terrain_bank, compressed_data, hole_offset
        )

        # Write greens bank (preserve other courses)
        greens_pointers = self._write_greens_bank(
            greens_bank, compressed_data, hole_offset
        )

        # Update pointer tables
        for i, (terrain_ptr, greens_ptr) in enumerate(
            zip(terrain_pointers, greens_pointers)
        ):
            abs_hole_idx = hole_offset + i
            self._write_pointer(
                TABLE_TERRAIN_START_PTR,
                abs_hole_idx,
                terrain_ptr["start"],
                f"global hole {abs_hole_idx} terrain start ptr",
            )
            self._write_pointer(
                TABLE_TERRAIN_END_PTR,
                abs_hole_idx,
                terrain_ptr["end"],
                f"global hole {abs_hole_idx} terrain end ptr",
            )
            self._write_pointer(
                TABLE_GREENS_PTR,
                abs_hole_idx,
                greens_ptr,
                f"global hole {abs_hole_idx} greens ptr",
            )

        # Update metadata for each hole
        for i, hole_data in enumerate(hole_data_list):
            abs_hole_idx = hole_offset + i
            self._update_metadata(abs_hole_idx, hole_data)

        # Calculate statistics
        total_terrain_bytes = sum(
            len(d["terrain"]) + len(d["attributes"]) for d in compressed_data
        )
        total_greens_bytes = sum(len(d["greens"]) for d in compressed_data)

        stats = {
            "course": course["display_name"],
            "terrain_bank_usage": total_terrain_bytes,
            "greens_bytes": total_greens_bytes,
            "holes": [
                {
                    "hole": i + 1,
                    "terrain_bytes": len(d["terrain"]),
                    "greens_bytes": len(d["greens"]),
                }
                for i, d in enumerate(compressed_data)
            ],
        }

        return stats

    def _write_terrain_bank(
        self, bank: int, compressed_data: list[dict], hole_offset: int
    ) -> list[dict]:
        """
        Write terrain data for 18 holes sequentially in bank.

        Args:
            bank: Bank number (0-2)
            compressed_data: List of compressed data dicts
            hole_offset: Absolute hole index offset

        Returns:
            List of pointer dicts: [{'start': cpu_addr, 'end': cpu_addr}, ...]

        Raises:
            BankOverflowError: If data doesn't fit in bank
        """
        # IMPORTANT: Each terrain bank contains lookup tables that must be preserved.
        # The terrain data region is bounded by these tables:
        #   Bank 0 (Japan): $8000-$A23D for terrain, $A23E-$BFFF for tables
        #   Bank 1 (US):    $8000-$A1E5 for terrain, $A1E6-$BFFF for tables
        #   Bank 2 (UK):    $8000-$837E for tables, $837F-$A553 for terrain,
        #                   $A554-$BFFF for tables
        TERRAIN_BOUNDS = {
            0: (0x8000, 0xA23E),  # Japan: terrain starts at $8000, ends before $A23E
            1: (0x8000, 0xA1E6),  # US: terrain starts at $8000, ends before $A1E6
            2: (0x837F, 0xA554),  # UK: terrain starts at $837F, ends before $A554
        }

        terrain_start_addr, terrain_end_addr = TERRAIN_BOUNDS[bank]
        available_space = terrain_end_addr - terrain_start_addr

        # Calculate total size needed
        total_size = sum(
            len(d["terrain"]) + len(d["attributes"]) for d in compressed_data
        )

        if total_size > available_space:
            raise BankOverflowError(
                f"Terrain data ({total_size} bytes) exceeds "
                f"available space ({available_space} bytes) in bank {bank} "
                f"(terrain region ${terrain_start_addr:04X}-${terrain_end_addr - 1:04X})"
            )

        # Start writing at the terrain region start (not bank start for UK)
        bank_start_prg = bank * PRG_BANK_SIZE
        terrain_region_offset = terrain_start_addr - 0x8000
        current_offset = bank_start_prg + terrain_region_offset

        pointers = []

        for i, data in enumerate(compressed_data):
            abs_hole_idx = hole_offset + i

            # Write terrain
            terrain_start = current_offset
            self.writer.annotate(
                f"global hole {abs_hole_idx} terrain data ({len(data['terrain'])} bytes)"
            ).write_prg(current_offset, data["terrain"])
            current_offset += len(data["terrain"])

            # Terrain ends here (attributes start here)
            terrain_end = current_offset

            # Write attributes (72 bytes)
            self.writer.annotate(
                f"global hole {abs_hole_idx} attributes ({len(data['attributes'])} bytes)"
            ).write_prg(current_offset, data["attributes"])
            current_offset += len(data["attributes"])

            # Calculate CPU addresses
            terrain_start_cpu = self.writer.prg_to_cpu_switched(terrain_start)
            terrain_end_cpu = self.writer.prg_to_cpu_switched(terrain_end)

            pointers.append({"start": terrain_start_cpu, "end": terrain_end_cpu})

        return pointers

    def _write_greens_bank(
        self, bank: int, compressed_data: list[dict], hole_offset: int
    ) -> list[int]:
        """
        Write greens data for 18 holes in bank 3.

        Preserves other courses' greens data. Defragments only the section
        for this course.

        Args:
            bank: Bank number (always 3)
            compressed_data: List of compressed data dicts
            hole_offset: Absolute hole index offset (0, 18, or 36)

        Returns:
            List of greens CPU addresses

        Raises:
            BankOverflowError: If data doesn't fit in bank
        """
        bank_start_prg = bank * PRG_BANK_SIZE

        # IMPORTANT: Read ALL existing greens data BEFORE modifying bank
        # Store original greens bank data to preserve other courses
        original_greens_bank = self.writer.read_prg(bank_start_prg, PRG_BANK_SIZE)

        # Read all existing greens pointers from source ROM
        all_greens_ptrs = []
        for hole_idx in range(54):
            ptr = self.writer.annotate(
                f"global hole {hole_idx} greens ptr (read for defrag)"
            ).read_fixed_word(TABLE_GREENS_PTR + hole_idx * 2)
            all_greens_ptrs.append(ptr)

        # Read all existing greens data from ORIGINAL bank before modifying
        # Use decompression to find actual compressed sizes (not pointer differences)
        # because the game's decompressor reads until 576 tiles, not until a pointer
        all_existing_greens = []

        # Lazily initialize decompressor for finding actual sizes
        if self.greens_decompressor is None:
            # Create a temporary RomReader from the original bank data
            # We can use the decompressor with the original bank's tables
            from .rom_reader import RomReader

            # Create decompressor using tables from original bank
            self.greens_decompressor = GreensDecompressor(None, bank)
            # Manually load tables from original_greens_bank
            self.greens_decompressor.horiz_table = list(original_greens_bank[0:192])
            self.greens_decompressor.vert_table = list(original_greens_bank[192:384])
            self.greens_decompressor.dict_table = list(original_greens_bank[384:448])

        for hole_idx in range(54):
            ptr = all_greens_ptrs[hole_idx]
            offset_in_bank = ptr - 0x8000

            # Read a buffer large enough for any compressed greens (max ~400 bytes)
            # Typical greens are 150-250 bytes compressed
            max_read = min(400, len(original_greens_bank) - offset_in_bank)
            buffer = original_greens_bank[offset_in_bank : offset_in_bank + max_read]

            # Find actual compressed size by decompression
            actual_size = find_actual_greens_size(
                bytes(buffer), self.greens_decompressor, max_read
            )

            existing_data = original_greens_bank[
                offset_in_bank : offset_in_bank + actual_size
            ]
            all_existing_greens.append(existing_data)

        # Prepare all greens data (preserving other courses)
        all_greens_data = []
        for hole_idx in range(54):
            if hole_offset <= hole_idx < hole_offset + HOLES_PER_COURSE:
                # This course - use new compressed data
                data_idx = hole_idx - hole_offset
                all_greens_data.append(compressed_data[data_idx]["greens"])
            else:
                # Other course - use preserved data
                all_greens_data.append(all_existing_greens[hole_idx])

        # Calculate total size
        total_size = sum(len(data) for data in all_greens_data)

        # Account for decompression tables at start of bank
        # Tables: horiz(192) + vert(192) + dict(64) = 448 bytes ($8000-$81BF)
        GREENS_TABLES_SIZE = 0x1C0  # 448 bytes

        # IMPORTANT: Bank 3 contains executable code starting at $A774
        # The greens data region is $81C0-$A773, code is $A774-$BFFF
        GREENS_CODE_START = 0xA774  # CPU address where code begins
        available_space = GREENS_CODE_START - 0x8000 - GREENS_TABLES_SIZE

        if total_size > available_space:
            raise BankOverflowError(
                f"Greens data ({total_size} bytes) exceeds "
                f"available space ({available_space} bytes) in bank "
                f"(after reserving {GREENS_TABLES_SIZE} bytes for decompression tables)"
            )

        # Write all greens data sequentially
        # IMPORTANT: Greens decompression tables are at $8000-$81BF (448 bytes)
        # We must preserve them and start greens data after
        current_offset = bank_start_prg + GREENS_TABLES_SIZE
        all_ptrs = []

        for hole_idx, data in enumerate(all_greens_data):
            cpu_addr = self.writer.prg_to_cpu_switched(current_offset)
            all_ptrs.append(cpu_addr)

            self.writer.annotate(
                f"global hole {hole_idx} greens data ({len(data)} bytes)"
            ).write_prg(current_offset, data)
            current_offset += len(data)

        # Update ALL greens pointers (since we defragmented entire bank)
        for hole_idx, ptr in enumerate(all_ptrs):
            self._write_pointer(
                TABLE_GREENS_PTR,
                hole_idx,
                ptr,
                f"global hole {hole_idx} greens ptr (defrag)",
            )

        # Return pointers for this course only
        return all_ptrs[hole_offset : hole_offset + HOLES_PER_COURSE]

    def _update_metadata(self, hole_idx: int, hole_data: HoleData):
        """
        Update metadata tables for a hole.

        Args:
            hole_idx: Absolute hole index (0-53)
            hole_data: HoleData object
        """
        metadata = hole_data.metadata

        # Write par
        self.writer.annotate(f"global hole {hole_idx} par").write_fixed_byte(
            TABLE_PAR + hole_idx, metadata.get("par", 4)
        )

        # Write handicap
        self.writer.annotate(f"global hole {hole_idx} handicap").write_fixed_byte(
            TABLE_HANDICAP + hole_idx, metadata.get("handicap", 1)
        )

        # Write distance (BCD encoded)
        distance = metadata.get("distance", 400)
        dist_100, dist_10, dist_1 = int_to_bcd(distance)
        self.writer.annotate(f"global hole {hole_idx} distance (100s)").write_fixed_byte(
            TABLE_DISTANCE_100 + hole_idx, dist_100
        )
        self.writer.annotate(f"global hole {hole_idx} distance (10s)").write_fixed_byte(
            TABLE_DISTANCE_10 + hole_idx, dist_10
        )
        self.writer.annotate(f"global hole {hole_idx} distance (1s)").write_fixed_byte(
            TABLE_DISTANCE_1 + hole_idx, dist_1
        )

        # Write scroll limit
        self.writer.annotate(f"global hole {hole_idx} scroll limit").write_fixed_byte(
            TABLE_SCROLL_LIMIT + hole_idx, metadata.get("scroll_limit", 32)
        )

        # Write green position
        self.writer.annotate(f"global hole {hole_idx} green X").write_fixed_byte(
            TABLE_GREEN_X + hole_idx, hole_data.green_x
        )
        self.writer.annotate(f"global hole {hole_idx} green Y").write_fixed_byte(
            TABLE_GREEN_Y + hole_idx, hole_data.green_y
        )

        # Write tee position
        tee = metadata.get("tee", {"x": 0, "y": 0})
        self.writer.annotate(f"global hole {hole_idx} tee X").write_fixed_byte(
            TABLE_TEE_X + hole_idx, tee["x"]
        )
        self.writer.annotate(f"global hole {hole_idx} tee Y").write_fixed_word(
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
                f"global hole {hole_idx} flag {i + 1} Y offset"
            ).write_fixed_byte(TABLE_FLAG_Y_OFFSET + hole_idx * 4 + i, y_offset)
            self.writer.annotate(
                f"global hole {hole_idx} flag {i + 1} X offset"
            ).write_fixed_byte(TABLE_FLAG_X_OFFSET + hole_idx * 4 + i, x_offset)

    def _write_pointer(
        self, table_addr: int, hole_idx: int, cpu_addr: int, annotation: str
    ):
        """
        Write 2-byte little-endian pointer to fixed bank table.

        Args:
            table_addr: CPU address of pointer table
            hole_idx: Hole index
            cpu_addr: CPU address to write
            annotation: Description for tracing
        """
        self.writer.annotate(annotation).write_fixed_word(
            table_addr + hole_idx * 2, cpu_addr
        )
