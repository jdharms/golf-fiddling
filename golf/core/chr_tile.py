"""
NES Open Tournament Golf - CHR Tile Decoding

Unified NES CHR format tile decoding functionality used by all tools.
This eliminates duplication between the editor, visualizer, and other tools.
"""

from typing import List

# CHR format constants
TILE_SIZE = 8           # 8x8 pixels per tile
BYTES_PER_TILE = 16     # 16 bytes per tile (8 bytes per bitplane)


def decode_tile(tile_data: bytes, tile_idx: int = 0) -> List[List[int]]:
    """
    Decode a single 8x8 NES CHR tile into 2-bit pixel values.

    NES tiles use two bitplanes to encode 4-color (2-bit) pixel data.
    Each tile is 16 bytes: 8 bytes for plane 0 (low bit), 8 bytes for plane 1 (high bit).

    Args:
        tile_data: Either a full CHR bank or a single 16-byte tile
        tile_idx: Tile index if tile_data is a full CHR bank (default: 0)

    Returns:
        8x8 array of pixel values (0-3), where each value is a palette index
    """
    # Calculate offset based on tile index
    offset = tile_idx * BYTES_PER_TILE

    # Handle out-of-range indices
    if offset + BYTES_PER_TILE > len(tile_data):
        return [[0] * 8 for _ in range(8)]

    # Extract the two bitplanes
    plane0 = tile_data[offset:offset + 8]      # Low bit plane
    plane1 = tile_data[offset + 8:offset + 16]  # High bit plane

    # Decode pixel by pixel
    pixels = []
    for row in range(8):
        row_pixels = []
        for col in range(8):
            # Extract bit from each plane (MSB first, left to right)
            bit_mask = 0x80 >> col
            low_bit = 1 if (plane0[row] & bit_mask) else 0
            high_bit = 1 if (plane1[row] & bit_mask) else 0

            # Combine into 2-bit value (0-3)
            pixel = low_bit | (high_bit << 1)
            row_pixels.append(pixel)
        pixels.append(row_pixels)

    return pixels


class TilesetData:
    """
    Loads NES CHR tile data from binary files.

    This class is rendering-agnostic - it only handles loading and decoding
    tile data. Rendering is handled separately by pygame or PIL-based renderers.
    """

    def __init__(self, chr_path: str):
        """
        Load CHR data from file.

        Args:
            chr_path: Path to CHR binary file
        """
        with open(chr_path, 'rb') as f:
            self.data = f.read()

        self.num_tiles = len(self.data) // BYTES_PER_TILE

    def decode_tile(self, tile_idx: int) -> List[List[int]]:
        """
        Decode a single tile from the loaded CHR data.

        Args:
            tile_idx: Index of tile to decode (0-based)

        Returns:
            8x8 array of pixel values (0-3)
        """
        return decode_tile(self.data, tile_idx)

    def get_tile_data(self, tile_idx: int) -> bytes:
        """
        Get raw 16-byte tile data.

        Args:
            tile_idx: Index of tile to retrieve

        Returns:
            16 bytes of raw CHR data
        """
        if tile_idx >= self.num_tiles:
            return bytes(16)

        offset = tile_idx * BYTES_PER_TILE
        return self.data[offset:offset + BYTES_PER_TILE]
