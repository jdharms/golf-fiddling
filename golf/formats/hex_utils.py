"""
NES Open Tournament Golf - Hex String Utilities

Utilities for parsing and formatting hex strings used in hole data files.
Consolidates duplicate hex parsing/formatting code across all tools.
"""

from typing import List


def parse_hex_row(row_str: str) -> List[int]:
    """
    Parse space-separated hex string to list of integers.

    Args:
        row_str: Space-separated hex string (e.g., "01 02 A3 FF")

    Returns:
        List of integer values

    Example:
        >>> parse_hex_row("01 02 A3 FF")
        [1, 2, 163, 255]
    """
    return [int(x, 16) for x in row_str.split()]


def format_hex_row(row: List[int]) -> str:
    """
    Format list of integers as space-separated hex string.

    Args:
        row: List of integers (0-255)

    Returns:
        Space-separated uppercase hex string

    Example:
        >>> format_hex_row([1, 2, 163, 255])
        '01 02 A3 FF'
    """
    return ' '.join(f'{b:02X}' for b in row)


def parse_hex_rows(rows: List[str]) -> List[List[int]]:
    """
    Parse multiple hex rows.

    Args:
        rows: List of space-separated hex strings

    Returns:
        2D list of integers
    """
    return [parse_hex_row(row) for row in rows]


def format_hex_rows(rows: List[List[int]]) -> List[str]:
    """
    Format multiple rows as hex strings.

    Args:
        rows: 2D list of integers

    Returns:
        List of space-separated hex strings
    """
    return [format_hex_row(row) for row in rows]
