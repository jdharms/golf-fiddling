"""Unit tests for compression table loading."""

import pytest


def test_load_real_tables(compression_tables):
    """Load from compression_tables.json and validate structure."""
    # Verify top-level structure
    assert "terrain" in compression_tables
    assert "greens" in compression_tables

    # Check terrain tables
    terrain = compression_tables["terrain"]
    assert "horizontal_table" in terrain
    assert "vertical_table" in terrain
    assert "dictionary_codes" in terrain
    assert "reverse_dict_lookup" in terrain

    # Validate sizes
    assert len(terrain["horizontal_table"]) == 224
    assert len(terrain["vertical_table"]) == 224
    assert len(terrain["dictionary_codes"]) == 32  # 0xE0-0xFF = 32 codes

    # Check greens tables
    greens = compression_tables["greens"]
    assert "horizontal_table" in greens
    assert "vertical_table" in greens
    assert "dictionary_codes" in greens
    assert "reverse_dict_lookup" in greens

    # Validate greens sizes
    assert len(greens["horizontal_table"]) == 192
    assert len(greens["vertical_table"]) == 192
    assert len(greens["dictionary_codes"]) == 32


def test_reverse_dict_lookup_sorted(compression_tables):
    """Verify reverse_dict_lookup keys are sorted by length (longest first)."""
    terrain = compression_tables["terrain"]
    reverse_lookup = terrain["reverse_dict_lookup"]

    keys = list(reverse_lookup.keys())

    # Keys should be sorted by length (longest first)
    # Each key is a hex-encoded byte sequence
    lengths = [len(k) // 2 for k in keys]  # Divide by 2 because 2 hex chars = 1 byte

    # Check that lengths are non-increasing (longest first)
    for i in range(len(lengths) - 1):
        assert lengths[i] >= lengths[i + 1], \
            f"Reverse lookup not sorted longest-first: {lengths[i]} < {lengths[i+1]}"


def test_dict_sequence_expansion(compression_tables):
    """Pick a dictionary code and verify expansion matches lookup."""
    terrain = compression_tables["terrain"]
    dict_codes = terrain["dictionary_codes"]

    # Pick code 0xE0 (should exist)
    code = "0xE0"
    assert code in dict_codes

    # Get the code definition
    code_def = dict_codes[code]
    assert "sequence" in code_def
    assert "length" in code_def

    # Verify the length matches the sequence
    assert code_def["length"] == len(code_def["sequence"])

    # Verify sequence starts with first_byte
    if len(code_def["sequence"]) > 0:
        assert code_def["sequence"][0] == code_def["first_byte"]


def test_table_consistency(compression_tables):
    """Verify horiz_table length matches dict expansion expectations."""
    terrain = compression_tables["terrain"]

    horiz_table = terrain["horizontal_table"]
    vert_table = terrain["vertical_table"]
    dict_codes = terrain["dictionary_codes"]

    # All dictionary codes should have first_byte < len(horiz_table)
    for code_name, code_def in dict_codes.items():
        first_byte = code_def["first_byte"]
        assert first_byte < len(horiz_table), \
            f"Code {code_name} has first_byte={first_byte} >= len(horiz_table)={len(horiz_table)}"

    # Verify tables are same length for terrain
    assert len(horiz_table) == len(vert_table), \
        f"Terrain tables mismatch: horiz={len(horiz_table)}, vert={len(vert_table)}"

    # Check greens consistency too
    greens = compression_tables["greens"]
    greens_horiz = greens["horizontal_table"]
    greens_vert = greens["vertical_table"]
    greens_dict = greens["dictionary_codes"]

    assert len(greens_horiz) == len(greens_vert), \
        f"Greens tables mismatch: horiz={len(greens_horiz)}, vert={len(greens_vert)}"

    # All greens dictionary codes should have valid first_byte
    for code_name, code_def in greens_dict.items():
        first_byte = code_def["first_byte"]
        assert first_byte < len(greens_horiz), \
            f"Greens code {code_name} has first_byte={first_byte} >= len(horiz_table)={len(greens_horiz)}"
