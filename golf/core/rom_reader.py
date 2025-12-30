"""
NES Open Tournament Golf - ROM Reader

ROM file reading and address translation for NES Open Tournament Golf.
Handles iNES ROM format and CPU address mapping for both fixed and switched banks.
"""

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


class RomReader:
    """
    Reads and parses NES Open Tournament Golf ROM files.

    Handles iNES ROM format and provides methods for reading from both
    fixed bank ($C000-$FFFF) and switchable banks ($8000-$BFFF).
    """

    def __init__(self, rom_path: str):
        """
        Load a NES ROM file.

        Args:
            rom_path: Path to iNES ROM file

        Raises:
            ValueError: If file is not a valid iNES ROM
        """
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
        """
        Read bytes from PRG ROM at absolute PRG offset.

        Args:
            prg_offset: Offset into PRG ROM (relative to start of PRG data)
            length: Number of bytes to read

        Returns:
            Requested bytes
        """
        file_offset = self.prg_start + prg_offset
        return self.data[file_offset:file_offset + length]

    def read_prg_byte(self, prg_offset: int) -> int:
        """Read a single byte from PRG ROM."""
        return self.read_prg(prg_offset, 1)[0]

    def read_prg_word(self, prg_offset: int) -> int:
        """
        Read 16-bit little-endian word from PRG ROM.

        Args:
            prg_offset: Offset into PRG ROM

        Returns:
            16-bit value
        """
        data = self.read_prg(prg_offset, 2)
        return data[0] | (data[1] << 8)

    def cpu_to_prg_fixed(self, cpu_addr: int) -> int:
        """
        Convert CPU address in fixed bank ($C000-$FFFF) to PRG offset.

        Args:
            cpu_addr: CPU address in range $C000-$FFFF

        Returns:
            PRG ROM offset

        Raises:
            ValueError: If address is not in fixed bank range
        """
        if cpu_addr < 0xC000 or cpu_addr > 0xFFFF:
            raise ValueError(f"Address ${cpu_addr:04X} not in fixed bank range")
        return FIXED_BANK_PRG_START + (cpu_addr - 0xC000)

    def cpu_to_prg_switched(self, cpu_addr: int, bank: int) -> int:
        """
        Convert CPU address in switched bank ($8000-$BFFF) to PRG offset.

        Args:
            cpu_addr: CPU address in range $8000-$BFFF
            bank: Bank number to use

        Returns:
            PRG ROM offset

        Raises:
            ValueError: If address is not in switchable bank range
        """
        if cpu_addr < 0x8000 or cpu_addr > 0xBFFF:
            raise ValueError(f"Address ${cpu_addr:04X} not in switchable bank range")
        return (bank * PRG_BANK_SIZE) + (cpu_addr - 0x8000)

    def read_fixed(self, cpu_addr: int, length: int = 1) -> bytes:
        """
        Read from fixed bank using CPU address.

        Args:
            cpu_addr: CPU address in range $C000-$FFFF
            length: Number of bytes to read

        Returns:
            Requested bytes
        """
        return self.read_prg(self.cpu_to_prg_fixed(cpu_addr), length)

    def read_fixed_byte(self, cpu_addr: int) -> int:
        """Read a single byte from fixed bank."""
        return self.read_fixed(cpu_addr, 1)[0]

    def read_fixed_word(self, cpu_addr: int) -> int:
        """
        Read 16-bit little-endian word from fixed bank.

        Args:
            cpu_addr: CPU address in range $C000-$FFFF

        Returns:
            16-bit value
        """
        data = self.read_fixed(cpu_addr, 2)
        return data[0] | (data[1] << 8)

    def read_switched(self, cpu_addr: int, bank: int, length: int = 1) -> bytes:
        """
        Read from switched bank using CPU address.

        Args:
            cpu_addr: CPU address in range $8000-$BFFF
            bank: Bank number to use
            length: Number of bytes to read

        Returns:
            Requested bytes
        """
        return self.read_prg(self.cpu_to_prg_switched(cpu_addr, bank), length)
