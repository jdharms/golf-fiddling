"""Unit tests for vertical fill detection in compression."""

import pytest


def test_first_row_unchanged(mock_minimal_terrain_tables):
    """First row should never be modified (no row above to compare)."""
    from golf.core.compressor import detect_vertical_fills

    rows = [[0xA2, 0xA3], [0xA0, 0xA1]]
    vert_table = mock_minimal_terrain_tables["vertical_table"]

    result = detect_vertical_fills(rows, vert_table)

    # First row should be completely unchanged
    assert result[0] == [0xA2, 0xA3]


def test_exact_vertical_match(mock_minimal_terrain_tables):
    """When tile == vert_table[tile_above], replace with 0x00."""
    from golf.core.compressor import detect_vertical_fills

    # Set up so that vert_table[0xA0] = 0xA2 and vert_table[0xA1] = 0xA3
    vert_table = mock_minimal_terrain_tables["vertical_table"]
    vert_table[0xA0] = 0xA2
    vert_table[0xA1] = 0xA3

    rows = [[0xA0, 0xA1], [0xA2, 0xA3]]

    result = detect_vertical_fills(rows, vert_table)

    # First row unchanged
    assert result[0] == [0xA0, 0xA1]
    # Second row: both tiles match vert_table lookup, so should become 0x00
    assert result[1] == [0x00, 0x00]


def test_no_vertical_match(mock_minimal_terrain_tables):
    """When tile != vert_table[tile_above], leave unchanged."""
    from golf.core.compressor import detect_vertical_fills

    vert_table = mock_minimal_terrain_tables["vertical_table"]
    vert_table[0xA0] = 0xA2
    vert_table[0xA1] = 0xA3

    rows = [[0xA0, 0xA1], [0x25, 0x27]]

    result = detect_vertical_fills(rows, vert_table)

    # First row unchanged
    assert result[0] == [0xA0, 0xA1]
    # Second row: tiles don't match, so unchanged
    assert result[1] == [0x25, 0x27]


def test_mixed_vertical_fills(mock_minimal_terrain_tables):
    """Some tiles match, some don't."""
    from golf.core.compressor import detect_vertical_fills

    vert_table = mock_minimal_terrain_tables["vertical_table"]
    vert_table[0xA0] = 0xA2
    vert_table[0xA1] = 0xA3
    vert_table[0x25] = 0x27

    rows = [[0xA0, 0xA1, 0x25], [0xA2, 0x99, 0x27]]

    result = detect_vertical_fills(rows, vert_table)

    # First row unchanged
    assert result[0] == [0xA0, 0xA1, 0x25]
    # Second row: first matches, second doesn't, third matches
    assert result[1] == [0x00, 0x99, 0x00]


def test_multiple_rows(mock_minimal_terrain_tables):
    """Test 5+ rows with various vertical fill patterns."""
    from golf.core.compressor import detect_vertical_fills

    vert_table = mock_minimal_terrain_tables["vertical_table"]
    # Set up simple pattern: horiz_table[x] = x (identity for our test values)
    for i in range(256):
        vert_table[i] = i

    rows = [
        [0x10, 0x11, 0x12],  # Row 0: seed values
        [0x10, 0x11, 0x99],  # Row 1: first two match, third doesn't
        [0x10, 0x99, 0x12],  # Row 2: first and third match, middle doesn't
        [0x99, 0x99, 0x99],  # Row 3: none match
        [0x10, 0x11, 0x12],  # Row 4: all match
    ]

    result = detect_vertical_fills(rows, vert_table)

    assert result[0] == [0x10, 0x11, 0x12]  # First row unchanged
    assert result[1] == [0x00, 0x00, 0x99]  # First two match row 0, third doesn't
    assert result[2] == [0x10, 0x99, 0x12]  # None match (row 1 has 0x00 values, different from row 0)
    assert result[3] == [0x99, 0x00, 0x99]  # Middle matches row2[1]=0x99 where vert[0x99]=0x99
    assert result[4] == [0x10, 0x11, 0x12]  # None match (row 3 has 0x99 values, different from row 0 tiles)


def test_bounds_safety(mock_minimal_terrain_tables):
    """Tile values >= len(vert_table) should not cause crashes."""
    from golf.core.compressor import detect_vertical_fills

    vert_table = [0] * 100  # Small table (only 100 entries)

    rows = [
        [0x50, 200],  # 200 is out of bounds
        [0x50, 200],  # Try to look up 200 in vert_table
    ]

    # Should not raise an exception
    result = detect_vertical_fills(rows, vert_table)

    # First row unchanged
    assert result[0] == [0x50, 200]
    # Second row: 0x50 < len(vert_table), so first might be replaced
    # But 200 >= len(vert_table), so it should be left alone (or default handled)
    assert len(result[1]) == 2
    assert result[1][1] == 200  # Out of bounds value left alone
