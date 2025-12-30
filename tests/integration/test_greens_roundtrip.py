"""Integration tests for greens compression round-trip validation."""

import pytest


def test_simple_greens_roundtrip(simple_greens_fixture, greens_decompressor):
    """Compress and decompress simple greens fixture (24x24)."""
    from golf.core.compressor import GreensCompressor

    original_rows = simple_greens_fixture["rows"]

    # Create compressor and compress
    compressor = GreensCompressor()
    compressed = compressor.compress(original_rows)

    # Decompress
    decompressed = greens_decompressor.decompress(compressed)

    # Greens are always 24x24 = 576 tiles
    assert len(decompressed) == 24, f"Expected 24 rows, got {len(decompressed)}"
    assert all(len(row) == 24 for row in decompressed), \
        "Not all rows have 24 columns"

    # Verify content
    for i, (original, decomp) in enumerate(zip(original_rows, decompressed)):
        assert original == decomp, \
            f"Row {i} mismatch: original length={len(original)}, decompressed length={len(decomp)}"


def test_hole_04_greens_roundtrip(hole_04_data, greens_decompressor):
    """Load hole 4 greens (24x24), compress and decompress."""
    from golf.core.compressor import GreensCompressor

    original_rows = hole_04_data.greens

    compressor = GreensCompressor()
    compressed = compressor.compress(original_rows)

    decompressed = greens_decompressor.decompress(compressed)

    # Verify dimensions
    assert len(decompressed) == 24
    assert all(len(row) == 24 for row in decompressed)

    # Verify content
    for i, (original, decomp) in enumerate(zip(original_rows, decompressed)):
        assert original == decomp, \
            f"Hole 4 greens row {i} mismatch"


def test_hole_01_greens_roundtrip(hole_01_data, greens_decompressor):
    """Load hole 1 greens (24x24), compress and decompress."""
    from golf.core.compressor import GreensCompressor

    original_rows = hole_01_data.greens

    compressor = GreensCompressor()
    compressed = compressor.compress(original_rows)

    decompressed = greens_decompressor.decompress(compressed)

    # Verify dimensions
    assert len(decompressed) == 24
    assert all(len(row) == 24 for row in decompressed)

    # Verify content
    for original, decomp in zip(original_rows, decompressed):
        assert original == decomp


def test_all_greens_zeros(greens_decompressor):
    """Edge case: greens grid of all 0x00."""
    from golf.core.compressor import GreensCompressor

    # Create a 24x24 grid of all zeros
    original_rows = [[0x00] * 24 for _ in range(24)]

    compressor = GreensCompressor()
    compressed = compressor.compress(original_rows)

    decompressed = greens_decompressor.decompress(compressed)

    # Should compress very efficiently
    assert len(compressed) < 24 * 24, \
        "All-zero compression should be much smaller than original"

    # Verify round-trip
    assert len(decompressed) == 24
    assert all(len(row) == 24 for row in decompressed)
    for original, decomp in zip(original_rows, decompressed):
        assert original == decomp


def test_greens_fixed_size(greens_decompressor):
    """Verify decompressor always outputs exactly 576 tiles (24x24)."""
    from golf.core.compressor import GreensCompressor

    # Create a simple greens pattern (24x24)
    original_rows = [
        [48, 49] * 12,  # 24 tiles per row
        [50, 51] * 12,
    ] * 12  # 24 rows

    compressor = GreensCompressor()
    compressed = compressor.compress(original_rows)

    decompressed = greens_decompressor.decompress(compressed)

    # Count total tiles
    total_tiles = sum(len(row) for row in decompressed)
    assert total_tiles == 576, \
        f"Expected 576 tiles (24x24), got {total_tiles}"

    # Verify it's actually 24x24
    assert len(decompressed) == 24
    assert all(len(row) == 24 for row in decompressed)
