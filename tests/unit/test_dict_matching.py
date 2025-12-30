"""Unit tests for dictionary sequence matching in compression."""

import pytest


def test_exact_longest_match(mock_minimal_terrain_tables):
    """Stream contains exact dictionary sequence - greedy longest match wins."""
    from golf.core.compressor import match_dict_sequence

    # Set up: we have a 4-byte sequence and a 6-byte sequence
    reverse_lookup = {
        "000000": ["0xE1"],  # 6-byte sequence
        "0000": ["0xE0"],    # 4-byte sequence (would match first)
    }

    # Stream has 6 zeros starting at position 0
    byte_stream = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x25, 0x27]

    result = match_dict_sequence(byte_stream, 0, reverse_lookup)

    # Should match the longer sequence (0xE1, 6 bytes)
    assert result is not None
    code, length = result
    assert code == "0xE1"
    assert length == 6


def test_shorter_match_when_longest_fails(mock_minimal_terrain_tables):
    """Stream partially matches longest, but shorter is complete."""
    from golf.core.compressor import match_dict_sequence

    reverse_lookup = {
        "000000": ["0xE1"],  # 6-byte sequence
        "0000": ["0xE0"],    # 4-byte sequence
    }

    # Stream only has 4 zeros, then something else
    byte_stream = [0x00, 0x00, 0x00, 0x00, 0x25, 0x27]

    result = match_dict_sequence(byte_stream, 0, reverse_lookup)

    # Should match the shorter sequence since 6-byte won't work
    assert result is not None
    code, length = result
    assert code == "0xE0"
    assert length == 4


def test_no_match(mock_minimal_terrain_tables):
    """Stream doesn't match any dictionary sequences."""
    from golf.core.compressor import match_dict_sequence

    reverse_lookup = {
        "000000": ["0xE1"],
        "0000": ["0xE0"],
    }

    # Stream has completely different pattern
    byte_stream = [0x25, 0x27, 0x3E, 0x5A]

    result = match_dict_sequence(byte_stream, 0, reverse_lookup)

    # Should return None (no match)
    assert result is None


def test_multiple_codes_same_sequence(mock_minimal_terrain_tables):
    """reverse_dict_lookup with multiple codes for same sequence."""
    from golf.core.compressor import match_dict_sequence

    # Could theoretically have multiple codes producing same sequence
    reverse_lookup = {
        "0000": ["0xE1", "0xE2"],  # Both produce same sequence
    }

    byte_stream = [0x00, 0x00, 0x00, 0x00]

    result = match_dict_sequence(byte_stream, 0, reverse_lookup)

    # Should return first code in list
    assert result is not None
    code, length = result
    assert code == "0xE1"
    assert length == 4


def test_end_of_stream(mock_minimal_terrain_tables):
    """Matching at end of byte stream."""
    from golf.core.compressor import match_dict_sequence

    reverse_lookup = {
        "0000": ["0xE0"],
    }

    # Stream with match at very end
    byte_stream = [0x25, 0x27, 0x3E, 0x00, 0x00, 0x00, 0x00]

    result = match_dict_sequence(byte_stream, 3, reverse_lookup)

    # Should find match starting at position 3
    assert result is not None
    code, length = result
    assert code == "0xE0"
    assert length == 4


def test_greedy_algorithm(mock_minimal_terrain_tables):
    """Confirms longest-first ordering matters."""
    from golf.core.compressor import match_dict_sequence

    # Three overlapping matches: 2-byte, 4-byte, 6-byte
    # Longest-first means we should try 6 first, then 4, then 2
    reverse_lookup = {
        "000000": ["0xE3"],  # 6 bytes
        "0000": ["0xE2"],    # 4 bytes
        "00": ["0xE1"],      # 2 bytes
    }

    # Stream with 8 zeros - should match the longest
    byte_stream = [0x00] * 8

    result = match_dict_sequence(byte_stream, 0, reverse_lookup)

    # Should match 6-byte sequence (longest), not 4 or 2
    assert result is not None
    code, length = result
    assert code == "0xE3"
    assert length == 6
