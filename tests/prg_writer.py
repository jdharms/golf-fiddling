"""A RomWriter over a bare PRG image, for unit tests that need no real ROM."""

from golf.core.rom_writer import RomWriter


class PrgImageWriter(RomWriter):
    """Every RomWriter method, reading and writing `data`: PRG bytes with no iNES header."""

    def __init__(self, data: bytes = bytes(0x40000)):
        self.data = bytearray(data)
        self.rom_data = self.data
        self.prg_start = 0
        self.prg_banks = len(self.data) // 0x4000
        self.output_path = None
