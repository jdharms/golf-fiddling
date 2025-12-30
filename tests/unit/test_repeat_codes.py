"""Unit tests for repeat code generation in compression."""

import pytest


def test_simple_repeat_sequence(mock_minimal_terrain_tables):
    """Stream follows horizontal transitions from prev_byte."""
    from golf.core.compressor import generate_repeat_code

    horiz_table = mock_minimal_terrain_tables["horizontal_table"]
    # Set up: 0xA0 -> 0xA2, 0xA2 -> 0xA0 (cycle)
    horiz_table[0xA0] = 0xA2
    horiz_table[0xA2] = 0xA0

    # Stream that follows this pattern: start from 0xA0, get 0xA2, then 0xA0, then 0xA2...
    byte_stream = [0xA2, 0xA0, 0xA2, 0xA0, 0x25]
    prev_byte = 0xA0

    result = generate_repeat_code(byte_stream, 0, prev_byte, horiz_table)

    # Should generate repeat code for 4 bytes (the cycle pattern)
    assert result is not None
    code, length = result
    assert code in range(0x01, 0x20)  # Valid repeat codes 1-31
    assert length == 4


def test_max_repeat_count(mock_minimal_terrain_tables):
    """Stream has 50 horizontal transitions, but max is 31."""
    from golf.core.compressor import generate_repeat_code

    horiz_table = mock_minimal_terrain_tables["horizontal_table"]
    # Set up identity: each byte transitions to itself
    for i in range(len(horiz_table)):
        horiz_table[i] = i

    # Stream with 50 of the same byte
    prev_byte = 0x50
    byte_stream = [0x50] * 50

    result = generate_repeat_code(byte_stream, 0, prev_byte, horiz_table)

    # Should cap at 31 (0x1F)
    assert result is not None
    code, length = result
    assert code == 0x1F
    assert length == 31


def test_no_repeat_match(mock_minimal_terrain_tables):
    """Stream doesn't follow horizontal transitions."""
    from golf.core.compressor import generate_repeat_code

    horiz_table = mock_minimal_terrain_tables["horizontal_table"]
    horiz_table[0xA0] = 0xA2

    # Stream doesn't follow the transition
    byte_stream = [0x25, 0x27, 0x3E]
    prev_byte = 0xA0

    result = generate_repeat_code(byte_stream, 0, prev_byte, horiz_table)

    # Should return None - no repeat match
    assert result is None


def test_single_transition(mock_minimal_terrain_tables):
    """Only 1 byte matches horizontal transition."""
    from golf.core.compressor import generate_repeat_code

    horiz_table = mock_minimal_terrain_tables["horizontal_table"]
    horiz_table[0xA0] = 0xA2

    # Stream has the one transition, then breaks
    byte_stream = [0xA2, 0x25, 0x27]
    prev_byte = 0xA0

    result = generate_repeat_code(byte_stream, 0, prev_byte, horiz_table)

    # Should generate code 0x01 (1 byte)
    assert result is not None
    code, length = result
    assert code == 0x01
    assert length == 1


def test_identity_transition(mock_minimal_terrain_tables):
    """horiz_table[byte] = byte (self-loop)."""
    from golf.core.compressor import generate_repeat_code

    horiz_table = mock_minimal_terrain_tables["horizontal_table"]
    # Set identity for 0x00
    horiz_table[0x00] = 0x00

    # Stream: all zeros (self-loop transition)
    byte_stream = [0x00, 0x00, 0x00, 0x00, 0x00]
    prev_byte = 0x00

    result = generate_repeat_code(byte_stream, 0, prev_byte, horiz_table)

    # Should generate repeat code for 5 bytes
    assert result is not None
    code, length = result
    assert code in range(0x01, 0x20)
    assert length == 5


def test_break_on_mismatch(mock_minimal_terrain_tables):
    """Sequence breaks after N transitions."""
    from golf.core.compressor import generate_repeat_code

    horiz_table = mock_minimal_terrain_tables["horizontal_table"]
    horiz_table[0xA0] = 0xA2
    horiz_table[0xA2] = 0xA0

    # Stream: follows pattern for 3 transitions, then breaks
    byte_stream = [0xA2, 0xA0, 0xA2, 0x25, 0x27]
    prev_byte = 0xA0

    result = generate_repeat_code(byte_stream, 0, prev_byte, horiz_table)

    # Should generate code for 3 transitions
    assert result is not None
    code, length = result
    assert code == 0x03
    assert length == 3
