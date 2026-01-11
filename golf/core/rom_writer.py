"""
NES Open Tournament Golf - ROM Writer

Writes course data from JSON files back to ROM.
Handles compression, pointer management, and bank allocation.
"""

from pathlib import Path

from .compressor import GreensCompressor, TerrainCompressor
from .packing import int_to_bcd, pack_attributes
from .rom_reader import (
    COURSES,
    FIXED_BANK_PRG_START,
    HOLES_PER_COURSE,
    INES_HEADER_SIZE,
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
from ..formats.hole_data import HoleData


class BankOverflowError(Exception):
    """Raised when compressed data exceeds bank capacity."""

    pass


class RomWriter:
    """
    Writes course data to NES ROM file with automatic pointer management.

    Strategy: Create modified ROM copy with defragmented banks.
    """

    def __init__(self, rom_path: str, output_path: str):
        """
        Load ROM for writing.

        Args:
            rom_path: Source ROM file (read-only)
            output_path: Output ROM file path (will be created/overwritten)

        Raises:
            ValueError: If ROM is not valid iNES format
        """
        # Read entire ROM into bytearray for modification
        with open(rom_path, "rb") as f:
            self.rom_data = bytearray(f.read())

        # Validate iNES header
        if self.rom_data[:4] != b"NES\x1a":
            raise ValueError("Not a valid iNES ROM file")

        self.output_path = output_path
        self.prg_banks = self.rom_data[4]
        self.prg_start = INES_HEADER_SIZE

        # Create compressors
        self.terrain_compressor = TerrainCompressor()
        self.greens_compressor = GreensCompressor()

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
        terrain_bank = self.read_fixed_byte(TABLE_COURSE_BANK_TERRAIN + course_idx)
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
                TABLE_TERRAIN_START_PTR, abs_hole_idx, terrain_ptr["start"]
            )
            self._write_pointer(TABLE_TERRAIN_END_PTR, abs_hole_idx, terrain_ptr["end"])
            self._write_pointer(TABLE_GREENS_PTR, abs_hole_idx, greens_ptr)

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
        # Calculate total size needed
        total_size = sum(
            len(d["terrain"]) + len(d["attributes"]) for d in compressed_data
        )

        if total_size > PRG_BANK_SIZE:
            raise BankOverflowError(
                f"Terrain data ({total_size} bytes) exceeds "
                f"bank size ({PRG_BANK_SIZE} bytes)"
            )

        # Start writing at beginning of bank
        bank_start_prg = bank * PRG_BANK_SIZE
        current_offset = bank_start_prg

        pointers = []

        for data in compressed_data:
            # Write terrain
            terrain_start = current_offset
            self._write_prg(current_offset, data["terrain"])
            current_offset += len(data["terrain"])

            # Terrain ends here (attributes start here)
            terrain_end = current_offset

            # Write attributes (72 bytes)
            self._write_prg(current_offset, data["attributes"])
            current_offset += len(data["attributes"])

            # Calculate CPU addresses
            terrain_start_cpu = self._prg_to_cpu_switched(terrain_start)
            terrain_end_cpu = self._prg_to_cpu_switched(terrain_end)

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
        original_greens_bank = bytes(
            self.rom_data[
                self.prg_start + bank_start_prg : self.prg_start
                + bank_start_prg
                + PRG_BANK_SIZE
            ]
        )

        # Read all existing greens pointers from source ROM
        all_greens_ptrs = []
        for hole_idx in range(54):
            ptr = self.read_fixed_word(TABLE_GREENS_PTR + hole_idx * 2)
            all_greens_ptrs.append(ptr)

        # Read all existing greens data from ORIGINAL bank before modifying
        all_existing_greens = []
        for hole_idx in range(54):
            ptr = all_greens_ptrs[hole_idx]
            offset_in_bank = ptr - 0x8000

            # Read until next hole's pointer or conservative fallback
            if hole_idx < 53:
                next_ptr = all_greens_ptrs[hole_idx + 1]
                if next_ptr > ptr:
                    size = next_ptr - ptr
                else:
                    size = 576  # Conservative fallback
            else:
                size = 576  # Last hole

            existing_data = original_greens_bank[
                offset_in_bank : offset_in_bank + size
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
        available_space = PRG_BANK_SIZE - GREENS_TABLES_SIZE

        if total_size > available_space:
            raise BankOverflowError(
                f"Greens data ({total_size} bytes) exceeds "
                f"available space ({available_space} bytes) in bank "
                f"(after reserving {GREENS_TABLES_SIZE} bytes for decompression tables)"
            )

        # Write all greens data sequentially
        # IMPORTANT: Greens decompression tables are at $8000-$81BF (448 bytes)
        # We must preserve them and start greens data after
        GREENS_TABLES_SIZE = 0x1C0  # Tables: $8000-$81BF (448 bytes)
        current_offset = bank_start_prg + GREENS_TABLES_SIZE
        all_ptrs = []

        for data in all_greens_data:
            cpu_addr = self._prg_to_cpu_switched(current_offset)
            all_ptrs.append(cpu_addr)

            self._write_prg(current_offset, data)
            current_offset += len(data)

        # Update ALL greens pointers (since we defragmented entire bank)
        for hole_idx, ptr in enumerate(all_ptrs):
            self._write_pointer(TABLE_GREENS_PTR, hole_idx, ptr)

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
        self.write_fixed_byte(TABLE_PAR + hole_idx, metadata.get("par", 4))

        # Write handicap
        self.write_fixed_byte(TABLE_HANDICAP + hole_idx, metadata.get("handicap", 1))

        # Write distance (BCD encoded)
        distance = metadata.get("distance", 400)
        dist_100, dist_10, dist_1 = int_to_bcd(distance)
        self.write_fixed_byte(TABLE_DISTANCE_100 + hole_idx, dist_100)
        self.write_fixed_byte(TABLE_DISTANCE_10 + hole_idx, dist_10)
        self.write_fixed_byte(TABLE_DISTANCE_1 + hole_idx, dist_1)

        # Write scroll limit
        self.write_fixed_byte(
            TABLE_SCROLL_LIMIT + hole_idx, metadata.get("scroll_limit", 32)
        )

        # Write green position
        self.write_fixed_byte(TABLE_GREEN_X + hole_idx, hole_data.green_x)
        self.write_fixed_byte(TABLE_GREEN_Y + hole_idx, hole_data.green_y)

        # Write tee position
        tee = metadata.get("tee", {"x": 0, "y": 0})
        self.write_fixed_byte(TABLE_TEE_X + hole_idx, tee["x"])
        self.write_fixed_word(TABLE_TEE_Y + hole_idx * 2, tee["y"])

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

            self.write_fixed_byte(TABLE_FLAG_Y_OFFSET + hole_idx * 4 + i, y_offset)
            self.write_fixed_byte(TABLE_FLAG_X_OFFSET + hole_idx * 4 + i, x_offset)

    def _write_pointer(self, table_addr: int, hole_idx: int, cpu_addr: int):
        """
        Write 2-byte little-endian pointer to fixed bank table.

        Args:
            table_addr: CPU address of pointer table
            hole_idx: Hole index
            cpu_addr: CPU address to write
        """
        prg_offset = self._cpu_to_prg_fixed(table_addr + hole_idx * 2)
        file_offset = self.prg_start + prg_offset
        self.rom_data[file_offset] = cpu_addr & 0xFF  # Low byte
        self.rom_data[file_offset + 1] = (cpu_addr >> 8) & 0xFF  # High byte

    def _write_prg(self, prg_offset: int, data: bytes):
        """
        Write bytes to PRG ROM at absolute offset.

        Args:
            prg_offset: Offset into PRG ROM
            data: Bytes to write
        """
        file_offset = self.prg_start + prg_offset
        self.rom_data[file_offset : file_offset + len(data)] = data

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        """
        Read bytes from PRG ROM at absolute offset.

        Args:
            prg_offset: Offset into PRG ROM
            length: Number of bytes to read

        Returns:
            Requested bytes
        """
        file_offset = self.prg_start + prg_offset
        return bytes(self.rom_data[file_offset : file_offset + length])

    def read_fixed_byte(self, cpu_addr: int) -> int:
        """Read a single byte from fixed bank."""
        prg_offset = self._cpu_to_prg_fixed(cpu_addr)
        return self.rom_data[self.prg_start + prg_offset]

    def read_fixed_word(self, cpu_addr: int) -> int:
        """Read 16-bit little-endian word from fixed bank."""
        low = self.read_fixed_byte(cpu_addr)
        high = self.read_fixed_byte(cpu_addr + 1)
        return low | (high << 8)

    def write_fixed_byte(self, cpu_addr: int, value: int):
        """Write a single byte to fixed bank."""
        prg_offset = self._cpu_to_prg_fixed(cpu_addr)
        self.rom_data[self.prg_start + prg_offset] = value

    def write_fixed_word(self, cpu_addr: int, value: int):
        """Write 16-bit little-endian word to fixed bank."""
        self.write_fixed_byte(cpu_addr, value & 0xFF)
        self.write_fixed_byte(cpu_addr + 1, (value >> 8) & 0xFF)

    def _prg_to_cpu_switched(self, prg_offset: int) -> int:
        """
        Convert PRG offset to CPU address in switched bank ($8000-$BFFF).

        Args:
            prg_offset: Absolute PRG offset

        Returns:
            CPU address in switched bank range
        """
        offset_in_bank = prg_offset % PRG_BANK_SIZE
        return 0x8000 + offset_in_bank

    def _cpu_to_prg_switched(self, cpu_addr: int, bank: int) -> int:
        """
        Convert CPU address in switched bank to PRG offset.

        Args:
            cpu_addr: CPU address ($8000-$BFFF)
            bank: Bank number

        Returns:
            Absolute PRG offset
        """
        offset_in_bank = cpu_addr - 0x8000
        return bank * PRG_BANK_SIZE + offset_in_bank

    def _cpu_to_prg_fixed(self, cpu_addr: int) -> int:
        """
        Convert fixed bank CPU address ($C000-$FFFF) to PRG offset.

        Args:
            cpu_addr: CPU address in fixed bank

        Returns:
            Absolute PRG offset
        """
        return FIXED_BANK_PRG_START + (cpu_addr - 0xC000)

    def save(self):
        """Write modified ROM to output file."""
        with open(self.output_path, "wb") as f:
            f.write(self.rom_data)
        print(f"Wrote modified ROM to: {self.output_path}")

    @classmethod
    def from_file(cls, rom_path: str, output_path: str | None = None) -> "RomWriter":
        """
        Create RomWriter from file path.

        Args:
            rom_path: Source ROM file
            output_path: Output ROM file (default: <rom>.modified.nes)

        Returns:
            RomWriter instance
        """
        if output_path is None:
            path = Path(rom_path)
            output_path = str(path.with_suffix("")) + ".modified.nes"

        return cls(rom_path, output_path)
