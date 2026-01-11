#!/usr/bin/env python3
"""
NES Open Tournament Golf - Greens Neighbor Analyzer

Analyzes all course data to extract valid greens tile neighbor relationships
for specific tile ranges ($48-$6F and $74-$83).
Produces a JSON file mapping each tile to its valid neighbors in each direction.
"""

import json
from collections import defaultdict
from pathlib import Path

from golf.formats.hole_data import HoleData


def is_target_tile(tile_idx: int) -> bool:
    """
    Check if tile is in target ranges $48-$6F or $74-$83.

    Args:
        tile_idx: Tile index to check

    Returns:
        True if tile is in target ranges, False otherwise
    """
    return (0x48 <= tile_idx <= 0x6F) or (0x74 <= tile_idx <= 0x83)


def analyze_greens_neighbors() -> dict:
    """
    Analyze all 54 holes to extract valid greens tile neighbor relationships.
    Only tracks relationships where BOTH tiles are in target ranges.

    Returns:
        Dictionary with metadata and neighbor relationships:
        {
            "metadata": {...},
            "neighbors": {
                "0x48": {"up": [...], "down": [...], "left": [...], "right": [...]},
                ...
            }
        }
    """
    neighbors: dict[int, dict[str, dict[int, int]]] = defaultdict(
        lambda: {"up": {}, "down": {}, "left": {}, "right": {}}
    )

    courses_dir = Path(__file__).parent.parent / "courses"
    total_holes = 0

    for course_name in ["japan", "us", "uk"]:
        course_dir = courses_dir / course_name
        print(f"\nAnalyzing {course_name.upper()} course...")

        for hole_num in range(1, 19):
            hole_file = course_dir / f"hole_{hole_num:02d}.json"

            if not hole_file.exists():
                print(f"  Warning: {hole_file} not found")
                continue

            try:
                hole_data = HoleData()
                hole_data.load(str(hole_file))

                # Iterate through greens (24x24 grid) and record neighbor relationships
                for row_idx, row in enumerate(hole_data.greens):
                    for col_idx, tile_idx in enumerate(row):
                        tile = tile_idx

                        # Skip if current tile is not in target ranges
                        if not is_target_tile(tile):
                            continue

                        # Check up
                        if row_idx > 0:
                            neighbor = hole_data.greens[row_idx - 1][col_idx]
                            # Only record if neighbor is also in target ranges
                            if is_target_tile(neighbor):
                                neighbors[tile]["up"][neighbor] = (
                                    neighbors[tile]["up"].get(neighbor, 0) + 1
                                )

                        # Check down
                        if row_idx < len(hole_data.greens) - 1:
                            neighbor = hole_data.greens[row_idx + 1][col_idx]
                            if is_target_tile(neighbor):
                                neighbors[tile]["down"][neighbor] = (
                                    neighbors[tile]["down"].get(neighbor, 0) + 1
                                )

                        # Check left
                        if col_idx > 0:
                            neighbor = hole_data.greens[row_idx][col_idx - 1]
                            if is_target_tile(neighbor):
                                neighbors[tile]["left"][neighbor] = (
                                    neighbors[tile]["left"].get(neighbor, 0) + 1
                                )

                        # Check right
                        if col_idx < len(row) - 1:
                            neighbor = hole_data.greens[row_idx][col_idx + 1]
                            if is_target_tile(neighbor):
                                neighbors[tile]["right"][neighbor] = (
                                    neighbors[tile]["right"].get(neighbor, 0) + 1
                                )

                total_holes += 1
                print(f"  Hole {hole_num:2d}: OK")

            except Exception as e:
                print(f"  Error processing hole {hole_num}: {e}")

    print(f"\nAnalyzed {total_holes} holes successfully")

    # Convert frequency dicts to JSON format with hex keys
    neighbors_json = {}
    for tile_idx in sorted(neighbors.keys()):
        tile_hex = f"0x{tile_idx:02X}"
        neighbors_json[tile_hex] = {
            "up": {
                f"0x{n:02X}": count for n, count in neighbors[tile_idx]["up"].items()
            },
            "down": {
                f"0x{n:02X}": count for n, count in neighbors[tile_idx]["down"].items()
            },
            "left": {
                f"0x{n:02X}": count for n, count in neighbors[tile_idx]["left"].items()
            },
            "right": {
                f"0x{n:02X}": count for n, count in neighbors[tile_idx]["right"].items()
            },
        }

    # Calculate statistics
    total_relationships = sum(
        len(dirs["up"]) + len(dirs["down"]) + len(dirs["left"]) + len(dirs["right"])
        for dirs in neighbors_json.values()
    )

    result = {
        "metadata": {
            "total_holes_analyzed": total_holes,
            "total_unique_tiles": len(neighbors_json),
            "total_relationships": total_relationships,
            "analysis_tool": "golf-analyze-greens-neighbors",
            "tile_ranges": ["0x48-0x6F", "0x74-0x83"],
        },
        "neighbors": neighbors_json,
    }

    return result


def main():
    """Command-line entry point."""
    print("NES Open Tournament Golf - Greens Neighbor Analyzer")
    print("=" * 50)
    print("Analyzing tile ranges: $48-$6F, $74-$83")

    # Analyze all neighbors
    result = analyze_greens_neighbors()

    # Create output directory
    output_dir = Path(__file__).parent.parent / "data" / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write to JSON file
    output_file = output_dir / "greens_neighbors.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✓ Saved neighbor data to: {output_file}")
    print("\nStatistics:")
    print(f"  Total holes analyzed: {result['metadata']['total_holes_analyzed']}")
    print(f"  Unique tiles: {result['metadata']['total_unique_tiles']}")
    print(
        f"  Total neighbor relationships: {result['metadata']['total_relationships']}"
    )


if __name__ == "__main__":
    main()
