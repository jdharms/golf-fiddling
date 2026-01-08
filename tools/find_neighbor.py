#!/usr/bin/env python3
"""
Find holes with specific terrain tile neighbor relationships.

Usage:
    python find_neighbor.py <tile1> <direction> <tile2>

Examples:
    python find_neighbor.py A1 S A4    # Find A1 with A4 directly south
    python find_neighbor.py 9E E 9F    # Find 9E with 9F directly east
    python find_neighbor.py DF N 82    # Find DF with 82 directly north

Directions: N, S, E, W, NE, NW, SE, SW
"""

import json
import sys
from pathlib import Path


DIRECTION_OFFSETS = {
    'N': (-1, 0),   # North (row above)
    'S': (1, 0),    # South (row below)
    'E': (0, 1),    # East (column right)
    'W': (0, -1),   # West (column left)
    'NE': (-1, 1),  # Northeast
    'NW': (-1, -1), # Northwest
    'SE': (1, 1),   # Southeast
    'SW': (1, -1),  # Southwest
}


def parse_terrain_rows(rows):
    """Parse terrain rows from hex strings into 2D array."""
    terrain = []
    for row in rows:
        tiles = row.split()
        terrain.append(tiles)
    return terrain


def find_neighbor_matches(terrain, tile1, direction, tile2):
    """
    Find all positions where tile1 has tile2 as a neighbor in the given direction.

    Returns list of (row, col) positions where tile1 is found with the relationship.
    """
    if direction not in DIRECTION_OFFSETS:
        raise ValueError(f"Invalid direction: {direction}. Must be one of {list(DIRECTION_OFFSETS.keys())}")

    tile1 = tile1.upper()
    tile2 = tile2.upper()
    drow, dcol = DIRECTION_OFFSETS[direction]

    matches = []
    height = len(terrain)

    for row in range(height):
        width = len(terrain[row])
        for col in range(width):
            # Check if this position has tile1
            if terrain[row][col] == tile1:
                # Check if neighbor position exists and has tile2
                neighbor_row = row + drow
                neighbor_col = col + dcol

                if (0 <= neighbor_row < height and
                    0 <= neighbor_col < len(terrain[neighbor_row]) and
                    terrain[neighbor_row][neighbor_col] == tile2):
                    matches.append((row, col))

    return matches


def search_all_holes(tile1, direction, tile2):
    """Search all course holes for the neighbor relationship."""
    courses_dir = Path(__file__).parent.parent / "courses"

    if not courses_dir.exists():
        print(f"Error: courses directory not found at {courses_dir}")
        return

    found_any = False

    for country_dir in sorted(courses_dir.iterdir()):
        if not country_dir.is_dir():
            continue

        for hole_file in sorted(country_dir.glob("hole_*.json")):
            try:
                with open(hole_file) as f:
                    data = json.load(f)

                terrain_rows = data.get("terrain", {}).get("rows", [])
                if not terrain_rows:
                    continue

                terrain = parse_terrain_rows(terrain_rows)
                matches = find_neighbor_matches(terrain, tile1, direction, tile2)

                if matches:
                    found_any = True
                    print(f"\n{country_dir.name}/{hole_file.name}:")
                    print(f"  Found {len(matches)} occurrence(s) of {tile1} {direction} {tile2}")
                    for row, col in matches:
                        print(f"    Position: row {row}, col {col}")

            except Exception as e:
                print(f"Error processing {hole_file}: {e}", file=sys.stderr)

    if not found_any:
        print(f"\nNo holes found with {tile1} {direction} {tile2} relationship")


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    tile1 = sys.argv[1]
    direction = sys.argv[2].upper()
    tile2 = sys.argv[3]

    if direction not in DIRECTION_OFFSETS:
        print(f"Error: Invalid direction '{direction}'")
        print(f"Valid directions: {', '.join(DIRECTION_OFFSETS.keys())}")
        sys.exit(1)

    print(f"Searching for {tile1} with {tile2} to the {direction}...")
    search_all_holes(tile1, direction, tile2)


if __name__ == "__main__":
    main()
