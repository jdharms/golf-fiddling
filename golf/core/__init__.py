"""
Core NES functionality.

This package contains ROM reading, decompression, CHR tile decoding,
and palette definitions for NES Open Tournament Golf.
"""

from .rom_reader import RomReader
from .rom_writer import RomWriter, BankOverflowError
from .course_writer import CourseWriter
from .instrumented_io import InstrumentedRomReader, InstrumentedRomWriter

__all__ = [
    "RomReader",
    "RomWriter",
    "BankOverflowError",
    "CourseWriter",
    "InstrumentedRomReader",
    "InstrumentedRomWriter",
]
