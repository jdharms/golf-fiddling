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


def compute_interior_side(path_edges, interior_edges, exterior_edges):
    """
    Compute the interior side of a fringe tile.

    For corners: interior_side is the quadrant (tuple of 2 directions).
    For straights: interior_side is a single direction.

    Args:
        path_edges: List of directions that are path edges
        interior_edges: List of directions that are interior (green) edges
        exterior_edges: List of directions that are exterior (rough) edges

    Returns:
        Interior side as a direction string or tuple, or 'ambiguous'
    """
    opposites = {"up": "down", "down": "up", "left": "right", "right": "left"}

    if set(path_edges) in [{"up", "down"}, {"left", "right"}]:
        # Straight tile - interior is one of the perpendicular directions
        if len(interior_edges) == 1:
            return interior_edges[0]
    else:
        # Corner tile - interior is a quadrant
        # If non-path edges are interior, that's the interior side
        # If non-path edges are exterior, interior is the opposite quadrant
        if len(interior_edges) == 2:
            return tuple(sorted(interior_edges))  # e.g., ('left', 'up') for NW
        elif len(exterior_edges) == 2:
            return tuple(sorted(opposites[e] for e in exterior_edges))  # opposite

    return "ambiguous"


def classify_tile(tile_id, neighbor_data):
    """
    Classify a fringe tile based on its neighbor patterns.

    Args:
        tile_id: Tile hex ID (e.g., '0x48')
        neighbor_data: Dictionary with 'up', 'down', 'left', 'right' neighbor counts

    Returns:
        Classification dictionary with tile, path, interior_side, and ambiguous fields
    """
    FRINGE_THRESHOLD = 4
    DOMINANCE_RATIO = 2.0

    path_edges = []
    interior_edges = []
    exterior_edges = []
    ambiguous_edges = []

    for direction in ["up", "down", "left", "right"]:
        neighbors = neighbor_data.get(direction, {})

        rough_count = neighbors.get("0x00", 0)
        green_count = neighbors.get("0x30", 0)
        fringe_count = sum(
            count for tile, count in neighbors.items() if tile not in ("0x00", "0x30")
        )

        # Path edge: predominantly fringe neighbors
        if fringe_count >= FRINGE_THRESHOLD and fringe_count > (
            rough_count + green_count
        ):
            path_edges.append(direction)
        # Interior edge: predominantly putting surface
        elif green_count > rough_count * DOMINANCE_RATIO:
            interior_edges.append(direction)
        # Exterior edge: predominantly rough
        elif rough_count > green_count * DOMINANCE_RATIO:
            exterior_edges.append(direction)
        else:
            ambiguous_edges.append(direction)

    # Derive interior_side from non-path edges
    if len(path_edges) != 2:
        return {
            "error": "expected exactly 2 path edges",
            "path": path_edges,
            "interior_edges": interior_edges,
            "exterior_edges": exterior_edges,
            "ambiguous": ambiguous_edges,
        }

    interior_side = compute_interior_side(path_edges, interior_edges, exterior_edges)

    return {
        "tile": tile_id,
        "path": tuple(sorted(path_edges)),
        "interior_side": interior_side,
        "ambiguous": ambiguous_edges,
    }


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
                            # Record if neighbor is in target ranges
                            if is_target_tile(neighbor):
                                neighbors[tile]["up"][neighbor] = (
                                    neighbors[tile]["up"].get(neighbor, 0) + 1
                                )
                            # Or record as 0x00 if neighbor is:
                            #     < 0x30 (out of range)
                            #     or in range (0x70, 0x74)
                            #     or in range (0x84, 0x88)
                            elif (neighbor < 0x30 or
                                  neighbor in range(0x70, 0x74) or
                                  neighbor in range(0x84, 0x88)
                            ):
                                neighbors[tile]["up"][0x00] = (
                                    neighbors[tile]["up"].get(0x00, 0) + 1
                                )
                            # Or record as 0x30 if neighbor is >= 0x30 (out of range)
                            else:
                                neighbors[tile]["up"][0x30] = (
                                    neighbors[tile]["up"].get(0x30, 0) + 1
                                )

                        # Check down
                        if row_idx < len(hole_data.greens) - 1:
                            neighbor = hole_data.greens[row_idx + 1][col_idx]
                            # Record if neighbor is in target ranges
                            if is_target_tile(neighbor):
                                neighbors[tile]["down"][neighbor] = (
                                    neighbors[tile]["down"].get(neighbor, 0) + 1
                                )
                            # Or record as 0x00 if neighbor is < 0x30 (out of range)
                            elif (neighbor < 0x30 or
                                  neighbor in range(0x70, 0x74) or
                                  neighbor in range(0x84, 0x88)
                            ):
                                neighbors[tile]["down"][0x00] = (
                                    neighbors[tile]["down"].get(0x00, 0) + 1
                                )
                            # Or record as 0x30 if neighbor is >= 0x30 (out of range)
                            else:
                                neighbors[tile]["down"][0x30] = (
                                    neighbors[tile]["down"].get(0x30, 0) + 1
                                )

                        # Check left
                        if col_idx > 0:
                            neighbor = hole_data.greens[row_idx][col_idx - 1]
                            # Record if neighbor is in target ranges
                            if is_target_tile(neighbor):
                                neighbors[tile]["left"][neighbor] = (
                                    neighbors[tile]["left"].get(neighbor, 0) + 1
                                )
                            # Or record as 0x00 if neighbor is < 0x30 (out of range)
                            elif (neighbor < 0x30 or
                                  neighbor in range(0x70, 0x74) or
                                  neighbor in range(0x84, 0x88)
                            ):
                                neighbors[tile]["left"][0x00] = (
                                    neighbors[tile]["left"].get(0x00, 0) + 1
                                )
                            # Or record as 0x30 if neighbor is >= 0x30 (out of range)
                            else:
                                neighbors[tile]["left"][0x30] = (
                                    neighbors[tile]["left"].get(0x30, 0) + 1
                                )

                        # Check right
                        if col_idx < len(row) - 1:
                            neighbor = hole_data.greens[row_idx][col_idx + 1]
                            # Record if neighbor is in target ranges
                            if is_target_tile(neighbor):
                                neighbors[tile]["right"][neighbor] = (
                                    neighbors[tile]["right"].get(neighbor, 0) + 1
                                )
                            # Or record as 0x00 if neighbor is < 0x30 (out of range)
                            elif (neighbor < 0x30 or
                                  neighbor in range(0x70, 0x74) or
                                  neighbor in range(0x84, 0x88)
                            ):
                                neighbors[tile]["right"][0x00] = (
                                    neighbors[tile]["right"].get(0x00, 0) + 1
                                )
                            # Or record as 0x30 if neighbor is >= 0x30 (out of range)
                            else:
                                neighbors[tile]["right"][0x30] = (
                                    neighbors[tile]["right"].get(0x30, 0) + 1
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

    # Classify tiles based on neighbor patterns
    print("\nClassifying tiles...")
    classifications = {}
    for tile_id, neighbor_data in neighbors_json.items():
        classification = classify_tile(tile_id, neighbor_data)
        classifications[tile_id] = classification

    # Count classification results
    tiles_with_errors = sum(1 for c in classifications.values() if "error" in c)
    tiles_classified = len(classifications) - tiles_with_errors

    # Build reverse mapping: (path, interior_side) -> [tiles]
    print("Building classification index...")
    classification_index = {}
    for tile_id, classification in classifications.items():
        # Skip tiles with errors
        if "error" in classification:
            continue

        # Normalize path (already sorted tuple)
        path = classification["path"]

        # Normalize interior_side
        interior_side = classification["interior_side"]
        if isinstance(interior_side, list):
            # Convert to sorted tuple for consistency
            interior_side = tuple(sorted(interior_side))

        # Create key from (path, interior_side)
        key = (path, interior_side)

        # Add tile to this classification bucket
        if key not in classification_index:
            classification_index[key] = []
        classification_index[key].append(tile_id)

    # Convert to JSON-serializable format with string keys
    classification_index_json = {}
    for (path, interior_side), tiles in sorted(classification_index.items()):
        # Format: "path=(down,right) interior=(down,right)"
        path_str = f"({','.join(path)})"
        if isinstance(interior_side, tuple):
            interior_str = f"({','.join(interior_side)})"
        else:
            interior_str = interior_side
        key_str = f"path={path_str} interior={interior_str}"
        classification_index_json[key_str] = sorted(tiles)

    result = {
        "metadata": {
            "total_holes_analyzed": total_holes,
            "total_unique_tiles": len(neighbors_json),
            "total_relationships": total_relationships,
            "tiles_classified": tiles_classified,
            "tiles_with_errors": tiles_with_errors,
            "unique_classifications": len(classification_index_json),
            "analysis_tool": "golf-analyze-greens-neighbors",
            "tile_ranges": ["0x48-0x6F", "0x74-0x83"],
        },
        "neighbors": neighbors_json,
        "classifications": classifications,
        "classification_index": classification_index_json,
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
    print(f"  Tiles classified: {result['metadata']['tiles_classified']}")
    print(f"  Tiles with errors: {result['metadata']['tiles_with_errors']}")
    print(f"  Unique classifications: {result['metadata']['unique_classifications']}")


if __name__ == "__main__":
    main()
