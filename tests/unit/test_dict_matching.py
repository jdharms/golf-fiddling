"""Unit tests for dictionary sequence matching in compression."""

import pytest


def test_exact_longest_match(mock_minimal_terrain_tables):
    """Stream contains exact dictionary sequence - greedy longest match wins."""
    from golf.core.compressor import match_dict_sequence

    # Set up: we have a 2-byte sequence and a 6-byte sequence
    reverse_lookup = {
        "000000000000": ["0xE1"],  # 6-byte sequence of 0x00
        "0000": ["0xE0"],          # 2-byte sequence of 0x00
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
        "000000000000": ["0xE1"],  # 6-byte sequence
        "0000": ["0xE0"],          # 2-byte sequence
    }

    # Stream only has 2 zeros, then something else
    byte_stream = [0x00, 0x00, 0x25, 0x27]

    result = match_dict_sequence(byte_stream, 0, reverse_lookup)

    # Should match the 2-byte sequence since 6-byte won't work
    assert result is not None
    code, length = result
    assert code == "0xE0"
    assert length == 2


def test_end_of_stream(mock_minimal_terrain_tables):
    """Matching at end of byte stream."""
    from golf.core.compressor import match_dict_sequence

    reverse_lookup = {
        "00000000": ["0xE0"],  # 4-byte sequence
    }

    # Stream with match at end
    byte_stream = [0x25, 0x27, 0x3E, 0x00, 0x00, 0x00, 0x00]

    result = match_dict_sequence(byte_stream, 3, reverse_lookup)

    # Should find match starting at position 3
    assert result is not None
    code, length = result
    assert code == "0xE0"
    assert length == 4
