#!/usr/bin/env python3
"""
NES Open Tournament Golf - Course Data Dumper

Extracts course data from ROM and saves as human-readable JSON files.
"""

import sys
from pathlib import Path
from typing import List
import compact_json as json

# ROM layout constants
INES_HEADER_SIZE = 0x10
PRG_BANK_SIZE = 0x4000  # 16KB banks
FIXED_BANK_PRG_START = 0x3C000  # Bank 15, maps to $C000-$FFFF

# Pointer tables (CPU addresses in fixed bank $C000-$FFFF)
# These are relative to $C000, so we calculate PRG offset
TABLE_COURSE_HOLE_OFFSET = 0xDBBB  # 3 bytes: 0, 18, 36
TABLE_COURSE_BANK_TERRAIN = 0xDBBE  # 3 bytes: bank numbers
TABLE_TERRAIN_START_PTR = 0xDBC1   # 54 x 2-byte pointers
TABLE_TERRAIN_END_PTR = 0xDC2D     # 54 x 2-byte pointers (also attr start)
TABLE_GREENS_PTR = 0xDC99          # 54 x 2-byte pointers
TABLE_PAR = 0xDD05                 # 54 bytes
TABLE_HANDICAP = 0xDDDD            # 54 bytes
TABLE_DISTANCE_100 = 0xDD3B        # 54 bytes (BCD)
TABLE_DISTANCE_10 = 0xDD71         # 54 bytes (BCD)
TABLE_DISTANCE_1 = 0xDDA7          # 54 bytes (BCD)
TABLE_SCROLL_LIMIT = 0xDE13        # 54 bytes
TABLE_GREEN_X = 0xDE49             # 54 bytes
TABLE_GREEN_Y = 0xDE7F             # 54 bytes
TABLE_TEE_X = 0xDEB5               # 54 bytes
TABLE_TEE_Y = 0xDEEB               # 54 x 2-byte values
TABLE_FLAG_Y_OFFSET = 0xE02F       # 54 x 4 bytes (4 positions per hole)
TABLE_FLAG_X_OFFSET = 0xDF57       # 54 x 4 bytes

# Decompression tables (also in fixed bank)
TABLE_HORIZ_TRANSITION = 0xE1AC    # 224 bytes
TABLE_VERT_CONTINUATION = 0xE28C   # 224 bytes
TABLE_DICTIONARY = 0xE36C          # 64 bytes (32 x 2-byte pairs)

# Course info (Japan first - original development order)
COURSES = [
    {"name": "japan", "display_name": "Japan"},
    {"name": "us", "display_name": "US"},
    {"name": "uk", "display_name": "UK"},
]
HOLES_PER_COURSE = 18
TOTAL_HOLES = 54

# Terrain dimensions
TERRAIN_ROW_WIDTH = 22
ATTR_ROW_WIDTH = 11  # 22 / 2 (supertiles)
ATTR_TOTAL_BYTES = 72


class RomReader:
    def __init__(self, rom_path: str):
        with open(rom_path, 'rb') as f:
            self.data = f.read()
        
        # Verify iNES header
        if self.data[:4] != b'NES\x1a':
            raise ValueError("Not a valid iNES ROM file")
        
        self.prg_banks = self.data[4]
        self.chr_banks = self.data[5]
        self.prg_size = self.prg_banks * PRG_BANK_SIZE
        self.prg_start = INES_HEADER_SIZE
        
        print(f"ROM loaded: {self.prg_banks} PRG banks ({self.prg_size // 1024}KB)")
    
    def read_prg(self, prg_offset: int, length: int = 1) -> bytes:
        """Read bytes from PRG ROM at absolute PRG offset."""
        file_offset = self.prg_start + prg_offset
        return self.data[file_offset:file_offset + length]
    
    def read_prg_byte(self, prg_offset: int) -> int:
        return self.read_prg(prg_offset, 1)[0]
    
    def read_prg_word(self, prg_offset: int) -> int:
        """Read 16-bit little-endian word."""
        data = self.read_prg(prg_offset, 2)
        return data[0] | (data[1] << 8)
    
    def cpu_to_prg_fixed(self, cpu_addr: int) -> int:
        """Convert CPU address in fixed bank ($C000-$FFFF) to PRG offset."""
        if cpu_addr < 0xC000 or cpu_addr > 0xFFFF:
            raise ValueError(f"Address ${cpu_addr:04X} not in fixed bank range")
        return FIXED_BANK_PRG_START + (cpu_addr - 0xC000)
    
    def cpu_to_prg_switched(self, cpu_addr: int, bank: int) -> int:
        """Convert CPU address in switched bank ($8000-$BFFF) to PRG offset."""
        if cpu_addr < 0x8000 or cpu_addr > 0xBFFF:
            raise ValueError(f"Address ${cpu_addr:04X} not in switchable bank range")
        return (bank * PRG_BANK_SIZE) + (cpu_addr - 0x8000)
    
    def read_fixed(self, cpu_addr: int, length: int = 1) -> bytes:
        """Read from fixed bank using CPU address."""
        return self.read_prg(self.cpu_to_prg_fixed(cpu_addr), length)
    
    def read_fixed_byte(self, cpu_addr: int) -> int:
        return self.read_fixed(cpu_addr, 1)[0]
    
    def read_fixed_word(self, cpu_addr: int) -> int:
        data = self.read_fixed(cpu_addr, 2)
        return data[0] | (data[1] << 8)
    
    def read_switched(self, cpu_addr: int, bank: int, length: int = 1) -> bytes:
        """Read from switched bank using CPU address."""
        return self.read_prg(self.cpu_to_prg_switched(cpu_addr, bank), length)


class TerrainDecompressor:
    """Decompresses terrain data using the game's RLE + dictionary + vertical fill algorithm."""
    
    def __init__(self, rom: RomReader):
        self.rom = rom
        
        # Load decompression tables from fixed bank
        prg = rom.cpu_to_prg_fixed(TABLE_HORIZ_TRANSITION)
        self.horiz_table = list(rom.read_prg(prg, 224))
        
        prg = rom.cpu_to_prg_fixed(TABLE_VERT_CONTINUATION)
        self.vert_table = list(rom.read_prg(prg, 224))
        
        prg = rom.cpu_to_prg_fixed(TABLE_DICTIONARY)
        self.dict_table = list(rom.read_prg(prg, 64))
    
    def decompress(self, compressed: bytes, row_width: int = TERRAIN_ROW_WIDTH) -> List[List[int]]:
        """
        Decompress terrain data.
        Returns a 2D array of tile values, one row per list.
        """
        # First pass: RLE + dictionary expansion
        output = []
        src_idx = 0
        
        while src_idx < len(compressed):
            byte = compressed[src_idx]
            src_idx += 1
            
            if byte >= 0xE0:
                # Dictionary code: expands to 2+ bytes
                dict_idx = (byte - 0xE0) * 2
                first_byte = self.dict_table[dict_idx]
                repeat_count = self.dict_table[dict_idx + 1]
                
                output.append(first_byte)
                
                # Apply horizontal transition for repeat_count iterations
                for _ in range(repeat_count):
                    prev = output[-1]
                    if prev < len(self.horiz_table):
                        output.append(self.horiz_table[prev])
                    else:
                        output.append(0)
            
            elif byte == 0x00:
                # Zero: written directly (row terminator or special)
                output.append(0)
            
            elif byte < 0x20:
                # Repeat count: apply horizontal transition
                repeat_count = byte
                for _ in range(repeat_count):
                    if len(output) > 0:
                        prev = output[-1]
                        if prev < len(self.horiz_table):
                            output.append(self.horiz_table[prev])
                        else:
                            output.append(0)
                    else:
                        output.append(0)
            
            else:
                # Literal terrain value ($20-$DF)
                output.append(byte)
        
        # Convert to rows
        rows = []
        for i in range(0, len(output), row_width):
            row = output[i:i + row_width]
            # Pad if necessary
            while len(row) < row_width:
                row.append(0)
            rows.append(row)
        
        # Second pass: vertical fill (0 = derive from row above)
        for row_idx in range(1, len(rows)):
            for col_idx in range(row_width):
                if rows[row_idx][col_idx] == 0:
                    above = rows[row_idx - 1][col_idx]
                    if above < len(self.vert_table):
                        rows[row_idx][col_idx] = self.vert_table[above]
        
        return rows


class GreensDecompressor:
    """Decompresses greens data - similar algorithm but different tables in switched bank."""
    
    def __init__(self, rom: RomReader, bank: int):
        self.rom = rom
        self.bank = bank
        
        # Greens decompression tables are at $8000, $80C0, $8180 in the switched bank
        prg = rom.cpu_to_prg_switched(0x8000, bank)
        self.horiz_table = list(rom.read_prg(prg, 192))
        
        prg = rom.cpu_to_prg_switched(0x80C0, bank)
        self.vert_table = list(rom.read_prg(prg, 192))
        
        prg = rom.cpu_to_prg_switched(0x8180, bank)
        self.dict_table = list(rom.read_prg(prg, 64))
    
    def decompress(self, compressed: bytes) -> List[List[int]]:
        """Decompress greens data. Row width is 24 for greens."""
        row_width = 24
        
        # First pass: RLE + dictionary expansion
        output = []
        src_idx = 0
        
        while src_idx < len(compressed):
            byte = compressed[src_idx]
            src_idx += 1
            
            if byte >= 0xE0:
                dict_idx = (byte - 0xE0) * 2
                first_byte = self.dict_table[dict_idx]
                repeat_count = self.dict_table[dict_idx + 1]
                
                output.append(first_byte)
                
                for _ in range(repeat_count):
                    prev = output[-1]
                    if prev < len(self.horiz_table):
                        output.append(self.horiz_table[prev])
                    else:
                        output.append(0)
            
            elif byte == 0x00:
                output.append(0)
            
            elif byte < 0x20:
                repeat_count = byte
                for _ in range(repeat_count):
                    if len(output) > 0:
                        prev = output[-1]
                        if prev < len(self.horiz_table):
                            output.append(self.horiz_table[prev])
                        else:
                            output.append(0)
                    else:
                        output.append(0)
            
            else:
                output.append(byte)
        
        # Convert to rows
        rows = []
        for i in range(0, len(output), row_width):
            row = output[i:i + row_width]
            while len(row) < row_width:
                row.append(0)
            rows.append(row)
        
        # Second pass: vertical fill
        for row_idx in range(1, len(rows)):
            for col_idx in range(row_width):
                if rows[row_idx][col_idx] == 0:
                    above = rows[row_idx - 1][col_idx]
                    if above < len(self.vert_table):
                        rows[row_idx][col_idx] = self.vert_table[above]
        
        return rows


def unpack_attributes(attr_bytes: bytes, num_rows: int) -> List[List[int]]:
    """
    Unpack NES attribute bytes into 2D palette index array.
    Each attribute byte covers a 4x4 tile (2x2 supertile) area.
    We return per-supertile (2x2 tile) palette indices.
    
    The first supertile column is HUD, so we skip it and return 11 course columns.
    
    Returns array of shape (num_rows, 11) with values 0-3.
    """
    # Attributes are stored in rows of 6 bytes (covering 12 supertiles)
    # First supertile column is HUD, we want columns 1-11 (11 total)
    
    rows = []
    attr_idx = 0
    
    for megatile_row in range(num_rows // 2):
        # Each megatile row produces 2 supertile rows
        top_row = []
        bottom_row = []
        
        for megatile_col in range(6):  # 6 megatiles wide (covers 12 supertile columns)
            if attr_idx >= len(attr_bytes):
                break
            
            attr = attr_bytes[attr_idx]
            attr_idx += 1
            
            # Unpack 4 palette indices from attribute byte
            top_left = attr & 0x03
            top_right = (attr >> 2) & 0x03
            bottom_left = (attr >> 4) & 0x03
            bottom_right = (attr >> 6) & 0x03
            
            top_row.extend([top_left, top_right])
            bottom_row.extend([bottom_left, bottom_right])
        
        # Skip first column (HUD), take next 11 columns (course data)
        rows.append(top_row[1:12])
        rows.append(bottom_row[1:12])
    
    return rows[:num_rows]


def bcd_to_int(hundreds: int, tens: int, ones: int) -> int:
    """Convert BCD distance values to integer."""
    h = ((hundreds >> 4) * 10 + (hundreds & 0x0F)) * 100
    t = ((tens >> 4) * 10 + (tens & 0x0F)) * 10
    o = (ones >> 4) * 10 + (ones & 0x0F)
    return h + t + o


def rows_to_hex_strings(rows: List[List[int]]) -> List[str]:
    """Convert 2D array of bytes to list of hex strings."""
    return [' '.join(f'{b:02X}' for b in row) for row in rows]


def dump_course(rom: RomReader, course_idx: int, output_dir: Path):
    """Dump all holes for a single course."""
    course = COURSES[course_idx]
    course_dir = output_dir / course["name"]
    course_dir.mkdir(parents=True, exist_ok=True)
    
    # Read course-level data
    hole_offset = rom.read_fixed_byte(TABLE_COURSE_HOLE_OFFSET + course_idx)
    terrain_bank = rom.read_fixed_byte(TABLE_COURSE_BANK_TERRAIN + course_idx)
    
    # Greens use bank 3 based on the code analysis
    greens_bank = 3
    
    # Write course metadata
    course_meta = {
        "name": course["display_name"],
        "hole_offset": hole_offset,
        "terrain_bank": terrain_bank,
        "greens_bank": greens_bank
    }
    
    with open(course_dir / "course.json", 'w') as f:
        json.dump(course_meta, f, indent=2)
    
    print(f"\nDumping {course['display_name']} course (bank {terrain_bank})...")
    
    # Create decompressors
    terrain_decomp = TerrainDecompressor(rom)
    greens_decomp = GreensDecompressor(rom, greens_bank)
    
    # Dump each hole
    for hole_in_course in range(HOLES_PER_COURSE):
        hole_idx = hole_offset + hole_in_course  # Absolute hole index 0-53
        hole_num = hole_in_course + 1  # Display number 1-18
        
        print(f"  Hole {hole_num}...", end=" ")
        
        # Read metadata from fixed bank tables
        par = rom.read_fixed_byte(TABLE_PAR + hole_idx)
        handicap = rom.read_fixed_byte(TABLE_HANDICAP + hole_idx)
        
        dist_100 = rom.read_fixed_byte(TABLE_DISTANCE_100 + hole_idx)
        dist_10 = rom.read_fixed_byte(TABLE_DISTANCE_10 + hole_idx)
        dist_1 = rom.read_fixed_byte(TABLE_DISTANCE_1 + hole_idx)
        distance = bcd_to_int(dist_100, dist_10, dist_1)
        
        scroll_limit = rom.read_fixed_byte(TABLE_SCROLL_LIMIT + hole_idx)
        green_x = rom.read_fixed_byte(TABLE_GREEN_X + hole_idx)
        green_y = rom.read_fixed_byte(TABLE_GREEN_Y + hole_idx)
        tee_x = rom.read_fixed_byte(TABLE_TEE_X + hole_idx)
        tee_y = rom.read_fixed_word(TABLE_TEE_Y + (hole_idx * 2))
        
        # Read flag positions (4 per hole)
        flag_positions = []
        for i in range(4):
            flag_y_off = rom.read_fixed_byte(TABLE_FLAG_Y_OFFSET + (hole_idx * 4) + i)
            flag_x_off = rom.read_fixed_byte(TABLE_FLAG_X_OFFSET + (hole_idx * 4) + i)
            flag_positions.append({"x_offset": flag_x_off, "y_offset": flag_y_off})
        
        # Read pointers
        terrain_start_ptr = rom.read_fixed_word(TABLE_TERRAIN_START_PTR + (hole_idx * 2))
        terrain_end_ptr = rom.read_fixed_word(TABLE_TERRAIN_END_PTR + (hole_idx * 2))
        greens_ptr = rom.read_fixed_word(TABLE_GREENS_PTR + (hole_idx * 2))
        
        # Calculate compressed terrain size
        terrain_compressed_size = terrain_end_ptr - terrain_start_ptr
        
        # Read compressed terrain data
        terrain_prg = rom.cpu_to_prg_switched(terrain_start_ptr, terrain_bank)
        terrain_compressed = rom.read_prg(terrain_prg, terrain_compressed_size)
        
        # Read attribute data (72 bytes after terrain)
        attr_prg = rom.cpu_to_prg_switched(terrain_end_ptr, terrain_bank)
        attr_bytes = rom.read_prg(attr_prg, ATTR_TOTAL_BYTES)
        
        # Decompress terrain
        terrain_rows = terrain_decomp.decompress(terrain_compressed)
        terrain_height = len(terrain_rows)
        
        # Unpack attributes
        attr_height = (terrain_height + 1) // 2  # Supertile rows
        attr_rows = unpack_attributes(attr_bytes, attr_height)
        
        # Read and decompress greens (need to find size first)
        # Greens end is the start of next hole's greens, or end of data
        if hole_idx < TOTAL_HOLES - 1:
            next_greens_ptr = rom.read_fixed_word(TABLE_GREENS_PTR + ((hole_idx + 1) * 2))
            # Handle course boundaries where pointer table wraps
            if next_greens_ptr > greens_ptr:
                greens_size = next_greens_ptr - greens_ptr
            else:
                greens_size = 256  # Fallback estimate
        else:
            greens_size = 256  # Last hole, estimate
        
        greens_prg = rom.cpu_to_prg_switched(greens_ptr, greens_bank)
        greens_compressed = rom.read_prg(greens_prg, greens_size)
        
        try:
            greens_rows = greens_decomp.decompress(greens_compressed)
        except Exception as e:
            print(f"(greens decompress error: {e})")
            greens_rows = []
        
        # Build hole JSON
        hole_data = {
            "hole": hole_num,
            "par": par,
            "distance": distance,
            "handicap": handicap,
            "scroll_limit": scroll_limit,
            
            "green": {"x": green_x, "y": green_y},
            "tee": {"x": tee_x, "y": tee_y},
            "flag_positions": flag_positions,
            
            "terrain": {
                "width": TERRAIN_ROW_WIDTH,
                "height": terrain_height,
                "rows": rows_to_hex_strings(terrain_rows)
            },
            
            "attributes": {
                "width": ATTR_ROW_WIDTH,
                "height": len(attr_rows),
                "rows": attr_rows
            },
            
            "greens": {
                "width": 24,
                "height": len(greens_rows),
                "rows": rows_to_hex_strings(greens_rows)
            },
            
            "_debug": {
                "terrain_ptr": f"${terrain_start_ptr:04X}",
                "terrain_end_ptr": f"${terrain_end_ptr:04X}",
                "terrain_compressed_size": terrain_compressed_size,
                "greens_ptr": f"${greens_ptr:04X}",
                "attr_raw": ' '.join(f'{b:02X}' for b in attr_bytes)
            }
        }
        
        # Write hole file
        filename = f"hole_{hole_num:02d}.json"
        with open(course_dir / filename, 'w') as f:
            json.dump(hole_data, f, indent=2)
        
        print(f"OK ({terrain_height} rows, {terrain_compressed_size} bytes compressed)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python dump_courses.py <rom_file> [output_dir]")
        print("\nDumps all course data from NES Open Tournament Golf ROM to JSON files.")
        sys.exit(1)
    
    rom_path = sys.argv[1]
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("courses")
    
    print(f"Loading ROM: {rom_path}")
    rom = RomReader(rom_path)
    
    print(f"Output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Dump all three courses
    for course_idx in range(len(COURSES)):
        dump_course(rom, course_idx, output_dir)
    
    print("\nDone!")


if __name__ == "__main__":
    main()