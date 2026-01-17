"""
Putting surface tile counting utilities.

Provides functions to count tiles that are part of the putting surface area
on greens. Used by both the analysis CLI tool and the metadata dialog.
"""

# Tiles that are part of the putting surface
# (matches PAINTABLE_TILES from editor/tools/carpet_paint_tool.py, excluding placeholder)
PUTTING_SURFACE_TILES = {
    0xB0,  # Flat
    *range(0x30, 0x48),  # Dark slopes (0x30-0x47)
    *range(0x88, 0xA8),  # Light slopes (0x88-0xA7)
}


def count_putting_surface_tiles(greens: list[list[int]]) -> int:
    """
    Count tiles that are part of the putting surface.

    Args:
        greens: 2D list of greens tile values (24x24 grid)

    Returns:
        Number of tiles that are putting surface tiles
    """
    count = 0
    for row in greens:
        for tile in row:
            if tile in PUTTING_SURFACE_TILES:
                count += 1
    return count
