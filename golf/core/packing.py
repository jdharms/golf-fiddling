"""
NES Open Tournament Golf - Data Packing

Inverse operations for decompression: pack attributes and encode BCD distances.
These functions are used when writing course data back to ROM.
"""


def pack_attributes(attr_rows: list[list[int]]) -> bytes:
    """
    Pack 2D palette indices into NES attribute bytes.

    Inverse of unpack_attributes(). Takes 11-column attribute rows and packs
    them into bytes with HUD column prepended, one byte per 2x2-supertile
    megatile: ((len(attr_rows) + 1) // 2) * 6 bytes total.

    The NES attribute format uses one byte to encode 4 supertile palettes
    (2x2 tile blocks). Each byte covers a 4x4 tile area (megatile).

    Bit layout of each attribute byte: [BR BR BL BL TR TR TL TL]
    - TL = top-left supertile palette (bits 0-1)
    - TR = top-right supertile palette (bits 2-3)
    - BL = bottom-left supertile palette (bits 4-5)
    - BR = bottom-right supertile palette (bits 6-7)

    Output length is not padded or truncated to any fixed size. The
    vanilla game's course-load routine always copies a fixed 72-byte
    window regardless of a hole's real height, but only ever reads back
    as many bytes as that hole's actual height needs - anything beyond a
    short hole's real data is copied but never used (in the vanilla
    layout, it's simply the start of the next hole's data). There is no
    reason to write that unused padding into the ROM.

    Args:
        attr_rows: Array of shape (num_rows, 11) with palette values 0-3

    Returns:
        Packed attribute data, ((len(attr_rows) + 1) // 2) * 6 bytes

    Raises:
        ValueError: If attr_rows is empty or contains invalid palette values
    """
    if not attr_rows:
        raise ValueError("attr_rows cannot be empty")

    # Validate palette values are in range 0-3
    for row_idx, row in enumerate(attr_rows):
        if len(row) != 11:
            raise ValueError(
                f"Row {row_idx} has {len(row)} columns, expected 11"
            )
        for col_idx, val in enumerate(row):
            if not 0 <= val <= 3:
                raise ValueError(
                    f"Invalid palette value {val} at row {row_idx}, col {col_idx}. "
                    f"Must be 0-3"
                )

    output = []

    # Process rows in pairs (megatile rows)
    for megatile_row_idx in range((len(attr_rows) + 1) // 2):
        # Get top and bottom rows (or duplicate last if odd)
        top_idx = megatile_row_idx * 2
        bottom_idx = min(top_idx + 1, len(attr_rows) - 1)

        top_row = attr_rows[top_idx]
        bottom_row = attr_rows[bottom_idx]

        # Prepend HUD column (palette 0) to both rows
        top_full = [0] + list(top_row)  # Now 12 columns
        bottom_full = [0] + list(bottom_row)

        # Pack 6 megatiles (12 supertile columns → 6 bytes)
        for megatile_col in range(6):
            col_idx = megatile_col * 2

            # Extract 4 supertile palettes for this megatile
            top_left = top_full[col_idx]
            top_right = top_full[col_idx + 1]
            bottom_left = bottom_full[col_idx]
            bottom_right = bottom_full[col_idx + 1]

            # Pack into single byte: [BR BR BL BL TR TR TL TL]
            attr_byte = (
                top_left | (top_right << 2) | (bottom_left << 4) | (bottom_right << 6)
            )
            output.append(attr_byte)

    return bytes(output)


def int_to_bcd(value: int) -> tuple[int, int, int]:
    """
    Convert integer distance to BCD (Binary-Coded Decimal) format.

    Inverse of bcd_to_int(). Each decimal digit is encoded in 4 bits.

    Example: 456 → (0x04, 0x05, 0x06)
    - Hundreds: 4 → 0x04
    - Tens: 5 → 0x05
    - Ones: 6 → 0x06

    Args:
        value: Integer distance (0-999)

    Returns:
        Tuple of (hundreds_bcd, tens_bcd, ones_bcd)

    Raises:
        ValueError: If value not in range 0-999
    """
    if not 0 <= value <= 999:
        raise ValueError(f"Distance must be 0-999, got {value}")

    # Extract decimal digits
    hundreds = value // 100
    tens = (value % 100) // 10
    ones = value % 10

    # Convert to BCD (each digit takes 4 bits)
    # For values 0-99, high nibble is 0, low nibble is the digit
    hundreds_bcd = (hundreds // 10) << 4 | (hundreds % 10)
    tens_bcd = (tens // 10) << 4 | (tens % 10)
    ones_bcd = (ones // 10) << 4 | (ones % 10)

    return (hundreds_bcd, tens_bcd, ones_bcd)
