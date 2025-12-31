#!/usr/bin/env python3
"""
NES Open Tournament Golf - Terrain Neighbor Analyzer

Analyzes all course data to extract valid terrain tile neighbor relationships.
Produces a JSON file mapping each tile to its valid neighbors in each direction.
"""

import json
from pathlib import Path
from typing import Dict, Set, Tuple
from collections import defaultdict

from golf.formats.hole_data import HoleData


def analyze_neighbors() -> Dict:
    """
    Analyze all 54 holes to extract valid terrain tile neighbor relationships.

    Returns:
        Dictionary with metadata and neighbor relationships:
        {
            "metadata": {...},
            "neighbors": {
                "0x25": {"up": [...], "down": [...], "left": [...], "right": [...]},
                ...
            }
        }
    """
    neighbors: Dict[int, Dict[str, Dict[int, int]]] = defaultdict(
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

                # Iterate through terrain and record neighbor relationships
                for row_idx, row in enumerate(hole_data.terrain):
                    for col_idx, tile_idx in enumerate(row):
                        tile = tile_idx

                        # Check up
                        if row_idx > 0:
                            neighbor = hole_data.terrain[row_idx - 1][col_idx]
                            neighbors[tile]["up"][neighbor] = neighbors[tile]["up"].get(neighbor, 0) + 1

                        # Check down
                        if row_idx < len(hole_data.terrain) - 1:
                            neighbor = hole_data.terrain[row_idx + 1][col_idx]
                            neighbors[tile]["down"][neighbor] = neighbors[tile]["down"].get(neighbor, 0) + 1

                        # Check left
                        if col_idx > 0:
                            neighbor = hole_data.terrain[row_idx][col_idx - 1]
                            neighbors[tile]["left"][neighbor] = neighbors[tile]["left"].get(neighbor, 0) + 1

                        # Check right
                        if col_idx < len(row) - 1:
                            neighbor = hole_data.terrain[row_idx][col_idx + 1]
                            neighbors[tile]["right"][neighbor] = neighbors[tile]["right"].get(neighbor, 0) + 1

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
            "up": {f"0x{n:02X}": count for n, count in neighbors[tile_idx]["up"].items()},
            "down": {f"0x{n:02X}": count for n, count in neighbors[tile_idx]["down"].items()},
            "left": {f"0x{n:02X}": count for n, count in neighbors[tile_idx]["left"].items()},
            "right": {f"0x{n:02X}": count for n, count in neighbors[tile_idx]["right"].items()},
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
            "analysis_tool": "golf-analyze-neighbors",
        },
        "neighbors": neighbors_json,
    }

    return result


def main():
    """Command-line entry point."""
    print("NES Open Tournament Golf - Terrain Neighbor Analyzer")
    print("=" * 50)

    # Analyze all neighbors
    result = analyze_neighbors()

    # Create output directory
    output_dir = Path(__file__).parent.parent / "data" / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write to JSON file
    output_file = output_dir / "terrain_neighbors.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✓ Saved neighbor data to: {output_file}")
    print(f"\nStatistics:")
    print(f"  Total holes analyzed: {result['metadata']['total_holes_analyzed']}")
    print(f"  Unique tiles: {result['metadata']['total_unique_tiles']}")
    print(f"  Total neighbor relationships: {result['metadata']['total_relationships']}")


if __name__ == "__main__":
    main()
