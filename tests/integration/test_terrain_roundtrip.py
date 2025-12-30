"""Integration tests for terrain compression round-trip validation."""

import pytest


def test_simple_terrain_roundtrip(simple_terrain_fixture, terrain_decompressor):
    """Compress and decompress simple fixture - should match original."""
    from golf.core.compressor import TerrainCompressor

    original_rows = simple_terrain_fixture["rows"]

    # Create compressor and compress
    compressor = TerrainCompressor()
    compressed = compressor.compress(original_rows)

    # Decompress
    decompressed = terrain_decompressor.decompress(compressed, row_width=22)

    # Verify round-trip
    assert len(decompressed) == len(original_rows), \
        f"Height mismatch: original={len(original_rows)}, decompressed={len(decompressed)}"

    for i, (original, decomp) in enumerate(zip(original_rows, decompressed)):
        assert original == decomp, \
            f"Row {i} mismatch: original={original}, decompressed={decomp}"


def test_hole_04_roundtrip(hole_04_data, terrain_decompressor):
    """Load hole 4 (simple 30-row hole), compress and decompress."""
    from golf.core.compressor import TerrainCompressor

    original_rows = hole_04_data.terrain

    compressor = TerrainCompressor()
    compressed = compressor.compress(original_rows)

    decompressed = terrain_decompressor.decompress(compressed, row_width=22)

    # Verify dimensions
    assert len(decompressed) == len(original_rows), \
        f"Height mismatch: original={len(original_rows)}, decompressed={len(decompressed)}"

    # Verify content
    for i, (original, decomp) in enumerate(zip(original_rows, decompressed)):
        assert original == decomp, \
            f"Hole 4 row {i} mismatch: {len(original)} tiles vs {len(decomp)} tiles"


def test_hole_01_roundtrip(hole_01_data, terrain_decompressor):
    """Load hole 1 (complex 38-row hole), compress and decompress."""
    from golf.core.compressor import TerrainCompressor

    original_rows = hole_01_data.terrain

    compressor = TerrainCompressor()
    compressed = compressor.compress(original_rows)

    decompressed = terrain_decompressor.decompress(compressed, row_width=22)

    # Verify dimensions
    assert len(decompressed) == len(original_rows), \
        f"Height mismatch: original={len(original_rows)}, decompressed={len(decompressed)}"

    # Verify content
    for i, (original, decomp) in enumerate(zip(original_rows, decompressed)):
        assert original == decomp, \
            f"Hole 1 row {i} mismatch"


def test_all_terrain_zeros(terrain_decompressor):
    """Edge case: terrain grid of all 0x00."""
    from golf.core.compressor import TerrainCompressor

    # Create a simple grid of all zeros (22 wide, 5 high)
    original_rows = [[0x00] * 22 for _ in range(5)]

    compressor = TerrainCompressor()
    compressed = compressor.compress(original_rows)

    decompressed = terrain_decompressor.decompress(compressed, row_width=22)

    # Should compress very efficiently
    assert len(compressed) < len(original_rows) * 22, \
        "All-zero compression should be much smaller than original"

    # Verify round-trip
    assert len(decompressed) == len(original_rows)
    for original, decomp in zip(original_rows, decompressed):
        assert original == decomp


def test_no_vertical_fills(terrain_decompressor):
    """Terrain with no vertical fill opportunities."""
    from golf.core.compressor import TerrainCompressor

    # Create rows where no tile equals vert_table[tile_above]
    # Using alternating pattern that won't match any vertical fills
    original_rows = [
        [0xA0, 0xA1, 0xA2, 0xA3] * 6,  # 24 tiles (truncated to 22)
        [0xA1, 0xA2, 0xA3, 0xA0] * 6,
        [0xA2, 0xA3, 0xA0, 0xA1] * 6,
    ]
    # Trim to 22 tiles wide
    original_rows = [row[:22] for row in original_rows]

    compressor = TerrainCompressor()
    compressed = compressor.compress(original_rows)

    decompressed = terrain_decompressor.decompress(compressed, row_width=22)

    # Verify round-trip
    for original, decomp in zip(original_rows, decompressed):
        assert original == decomp


def test_compression_stats(simple_terrain_fixture, terrain_decompressor):
    """Verify compression produces reasonable size."""
    from golf.core.compressor import TerrainCompressor

    original_rows = simple_terrain_fixture["rows"]
    original_size = sum(len(row) for row in original_rows)

    compressor = TerrainCompressor()
    compressed = compressor.compress(original_rows)

    # Compressed should be smaller than original (with RLE/dict)
    # But not necessarily < 50% due to overhead
    assert len(compressed) < original_size, \
        f"Compression failed: original={original_size} bytes, compressed={len(compressed)} bytes"

    # Verify round-trip still works
    decompressed = terrain_decompressor.decompress(compressed, row_width=22)
    for original, decomp in zip(original_rows, decompressed):
        assert original == decomp
