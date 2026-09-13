"""
Core NES functionality.

This package contains ROM reading, decompression, CHR tile decoding,
and palette definitions for NES Open Tournament Golf.

Import from the submodules directly (`from golf.core.rom_reader import RomReader`).
This file deliberately imports nothing: every `golf.core.*` import runs it, so
eager imports here load the course writer behind even a leaf module like
`palettes`, and that closes an import cycle through `golf.formats.hole_data`.
"""
