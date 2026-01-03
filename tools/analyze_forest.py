#!/usr/bin/env python3
"""
NES Open Tournament Golf - Forest Fill Feasibility Analyzer

Analyzes terrain_neighbors.json to assess the feasibility of automatic forest fill.
Focuses on transitions from rough/OOB borders -> forest borders -> forest fill.
"""

import json
from collections import defaultdict
from pathlib import Path

# Tile categories from appendix
INNER_BORDER = 0x3F  # Rough/OOB boundary (no trees)
FOREST_FILL = range(0xA0, 0xA4)  # $A0-$A3: horizontal repeating pattern
FOREST_BORDER = range(0xA4, 0xBC)  # $A4-$BB: complex border tiles
OOB_BORDER = range(0x80, 0x9C)  # $80-$9B: out of bounds border

SHALLOW_ROUGH = 0x25
DEEP_ROUGH = 0xDF


def load_neighbor_data() -> dict:
    """Load terrain_neighbors.json."""
    data_file = (
        Path(__file__).parent.parent / "data" / "tables" / "terrain_neighbors.json"
    )
    with open(data_file) as f:
        return json.load(f)


def hex_to_int(hex_str: str) -> int:
    """Convert '0xA4' to 164."""
    return int(hex_str, 16)


def int_to_hex(val: int) -> str:
    """Convert 164 to '0xA4'."""
    return f"0x{val:02X}"


def categorize_tile(tile: int) -> str:
    """Categorize a tile by its function."""
    if tile == INNER_BORDER:
        return "inner_border"
    elif tile in FOREST_FILL:
        return "forest_fill"
    elif tile in FOREST_BORDER:
        return "forest_border"
    elif tile in OOB_BORDER:
        return "oob_border"
    elif tile == SHALLOW_ROUGH:
        return "shallow_rough"
    elif tile == DEEP_ROUGH:
        return "deep_rough"
    else:
        return "other"


def analyze_coverage(neighbors: dict) -> None:
    """Check which forest tiles have neighbor data."""
    print("\n" + "=" * 70)
    print("COVERAGE ANALYSIS")
    print("=" * 70)

    # Check forest fill tiles
    print("\nForest Fill ($A0-$A3):")
    for tile_val in FOREST_FILL:
        tile_hex = int_to_hex(tile_val)
        if tile_hex in neighbors:
            total_neighbors = sum(
                len(neighbors[tile_hex][d]) for d in ["up", "down", "left", "right"]
            )
            print(f"  {tile_hex}: ✓ ({total_neighbors} total neighbor relationships)")
        else:
            print(f"  {tile_hex}: ✗ NO DATA")

    # Check forest border tiles
    print(f"\nForest Border ($A4-$BB): {len(list(FOREST_BORDER))} tiles")
    missing = []
    present = []
    for tile_val in FOREST_BORDER:
        tile_hex = int_to_hex(tile_val)
        if tile_hex in neighbors:
            present.append(tile_hex)
        else:
            missing.append(tile_hex)

    print(f"  Present: {len(present)}/{len(list(FOREST_BORDER))}")
    print(f"  Missing: {len(missing)}/{len(list(FOREST_BORDER))}")
    if missing:
        print(
            f"  Missing tiles: {', '.join(missing[:10])}"
            + (" ..." if len(missing) > 10 else "")
        )

    # Check inner border
    inner_hex = int_to_hex(INNER_BORDER)
    if inner_hex in neighbors:
        total = sum(
            len(neighbors[inner_hex][d]) for d in ["up", "down", "left", "right"]
        )
        print(f"\nInner Border ($3F): ✓ ({total} total neighbor relationships)")
    else:
        print("\nInner Border ($3F): ✗ NO DATA")


def analyze_transitions(neighbors: dict) -> None:
    """Analyze transitions between tile categories."""
    print("\n" + "=" * 70)
    print("TRANSITION ANALYSIS")
    print("=" * 70)

    # What tiles appear next to Inner Border?
    print("\nTiles adjacent to Inner Border ($3F):")
    inner_hex = int_to_hex(INNER_BORDER)
    if inner_hex in neighbors:
        adjacent_tiles = set()
        for direction in ["up", "down", "left", "right"]:
            for neighbor_hex in neighbors[inner_hex][direction]:
                adjacent_tiles.add(neighbor_hex)

        # Categorize them
        by_category = defaultdict(list)
        for tile_hex in sorted(adjacent_tiles):
            tile_val = hex_to_int(tile_hex)
            category = categorize_tile(tile_val)
            by_category[category].append(tile_hex)

        for category in sorted(by_category.keys()):
            tiles = by_category[category]
            print(
                f"  {category}: {len(tiles)} tiles - {', '.join(tiles[:8])}"
                + (" ..." if len(tiles) > 8 else "")
            )

    # What leads TO forest fill?
    print("\nTiles that have Forest Fill as neighbors:")
    tiles_with_fill_neighbors = []
    for tile_hex, dirs in neighbors.items():
        for direction in ["up", "down", "left", "right"]:
            for neighbor_hex in dirs[direction]:
                neighbor_val = hex_to_int(neighbor_hex)
                if neighbor_val in FOREST_FILL:
                    tiles_with_fill_neighbors.append(hex_to_int(tile_hex))
                    break

    by_category = defaultdict(list)
    for tile_val in sorted(set(tiles_with_fill_neighbors)):
        category = categorize_tile(tile_val)
        by_category[category].append(int_to_hex(tile_val))

    for category in sorted(by_category.keys()):
        tiles = by_category[category]
        print(f"  {category}: {len(tiles)} tiles")
        if category == "forest_border":
            print(f"    {', '.join(tiles[:12])}" + (" ..." if len(tiles) > 12 else ""))


def analyze_forest_fill_pattern(neighbors: dict) -> None:
    """Analyze if Forest Fill maintains horizontal repeat pattern."""
    print("\n" + "=" * 70)
    print("FOREST FILL PATTERN ANALYSIS")
    print("=" * 70)

    print("\nForest Fill should repeat as: $A0, $A1, $A2, $A3, $A0, $A1, ...")
    print("Checking left/right neighbor relationships:\n")

    fill_tiles = [int_to_hex(v) for v in FOREST_FILL]

    for i, tile_hex in enumerate(fill_tiles):
        if tile_hex not in neighbors:
            continue

        left_neighbors = [hex_to_int(n) for n in neighbors[tile_hex]["left"]]
        right_neighbors = [hex_to_int(n) for n in neighbors[tile_hex]["right"]]

        # Expected neighbors in pattern
        expected_left = 0xA0 + ((i - 1) % 4)
        expected_right = 0xA0 + ((i + 1) % 4)

        print(f"{tile_hex}:")
        print(
            f"  Left neighbors: {', '.join(int_to_hex(n) for n in sorted(left_neighbors))}"
        )
        print(
            f"  Expected left: {int_to_hex(expected_left)} - {'✓' if expected_left in left_neighbors else '✗ NOT FOUND'}"
        )
        print(
            f"  Right neighbors: {', '.join(int_to_hex(n) for n in sorted(right_neighbors))}"
        )
        print(
            f"  Expected right: {int_to_hex(expected_right)} - {'✓' if expected_right in right_neighbors else '✗ NOT FOUND'}"
        )
        print()


def analyze_boundary_depth(neighbors: dict) -> None:
    """Analyze how deep forest borders typically go."""
    print("\n" + "=" * 70)
    print("BOUNDARY DEPTH ANALYSIS")
    print("=" * 70)

    print("\nForest Border tiles that neighbor other Forest Border tiles:")
    print("(This shows which border tiles appear in multi-tile-deep borders)\n")

    border_to_border = []
    for tile_val in FOREST_BORDER:
        tile_hex = int_to_hex(tile_val)
        if tile_hex not in neighbors:
            continue

        has_border_neighbor = False
        for direction in ["up", "down", "left", "right"]:
            for neighbor_hex in neighbors[tile_hex][direction]:
                neighbor_val = hex_to_int(neighbor_hex)
                if neighbor_val in FOREST_BORDER:
                    has_border_neighbor = True
                    break
            if has_border_neighbor:
                break

        if has_border_neighbor:
            border_to_border.append(tile_hex)

    print(
        f"Border tiles with border neighbors: {len(border_to_border)}/{len(list(FOREST_BORDER))}"
    )
    print(
        f"  Tiles: {', '.join(border_to_border[:15])}"
        + (" ..." if len(border_to_border) > 15 else "")
    )

    # Find which border tiles ONLY neighbor fill (these are the "innermost" border)
    print("\nForest Border tiles that neighbor Forest Fill:")
    print("(These are the innermost border tiles, adjacent to fill)\n")

    border_to_fill = []
    for tile_val in FOREST_BORDER:
        tile_hex = int_to_hex(tile_val)
        if tile_hex not in neighbors:
            continue

        has_fill_neighbor = False
        for direction in ["up", "down", "left", "right"]:
            for neighbor_hex in neighbors[tile_hex][direction]:
                neighbor_val = hex_to_int(neighbor_hex)
                if neighbor_val in FOREST_FILL:
                    has_fill_neighbor = True
                    break
            if has_fill_neighbor:
                break

        if has_fill_neighbor:
            border_to_fill.append(tile_hex)

    print(
        f"Border tiles adjacent to fill: {len(border_to_fill)}/{len(list(FOREST_BORDER))}"
    )
    print(
        f"  Tiles: {', '.join(border_to_fill[:15])}"
        + (" ..." if len(border_to_fill) > 15 else "")
    )


def analyze_feasibility(neighbors: dict) -> None:
    """High-level feasibility assessment."""
    print("\n" + "=" * 70)
    print("AUTOMATIC FILL FEASIBILITY ASSESSMENT")
    print("=" * 70)

    issues = []

    # Check forest fill coverage
    fill_coverage = sum(1 for v in FOREST_FILL if int_to_hex(v) in neighbors)
    if fill_coverage < len(list(FOREST_FILL)):
        issues.append(f"⚠ Only {fill_coverage}/4 forest fill tiles have neighbor data")
    else:
        print("✓ All 4 forest fill tiles have neighbor data")

    # Check forest border coverage
    border_coverage = sum(1 for v in FOREST_BORDER if int_to_hex(v) in neighbors)
    border_total = len(list(FOREST_BORDER))
    coverage_pct = (border_coverage / border_total) * 100
    if coverage_pct < 80:
        issues.append(
            f"⚠ Only {coverage_pct:.0f}% of forest border tiles have neighbor data"
        )
    else:
        print(f"✓ {coverage_pct:.0f}% of forest border tiles have neighbor data")

    # Check inner border
    if int_to_hex(INNER_BORDER) in neighbors:
        print("✓ Inner border ($3F) has neighbor data")
    else:
        issues.append("⚠ Inner border ($3F) missing from neighbor data")

    # Check if we can find paths from border to fill
    border_tiles_leading_to_fill = 0
    for tile_val in FOREST_BORDER:
        tile_hex = int_to_hex(tile_val)
        if tile_hex not in neighbors:
            continue

        for direction in ["up", "down", "left", "right"]:
            for neighbor_hex in neighbors[tile_hex][direction]:
                if hex_to_int(neighbor_hex) in FOREST_FILL:
                    border_tiles_leading_to_fill += 1
                    break

    if border_tiles_leading_to_fill > 0:
        print(f"✓ {border_tiles_leading_to_fill} border tiles have paths to fill tiles")
    else:
        issues.append("⚠ No clear paths from border to fill tiles")

    print("\n" + "-" * 70)
    if issues:
        print("\nPotential Issues:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✓ No obvious blockers detected!")

    print("\nRecommendation:")
    if len(issues) <= 1 and coverage_pct >= 70:
        print("  🟢 FEASIBLE - Neighbor data appears sufficient for automatic fill")
        print("  Suggested approach:")
        print("    1. Flood fill from Inner Border inward")
        print("    2. Use distance field to determine border vs. fill regions")
        print("    3. Query neighbor data for valid tile choices at each position")
        print("    4. Prefer high-frequency patterns from vanilla courses")
    elif len(issues) <= 2:
        print("  🟡 MODERATELY FEASIBLE - May require fallback strategies")
        print("  Gaps in neighbor data might need manual pattern definition")
    else:
        print("  🔴 CHALLENGING - Significant data gaps or complexity")


def main():
    """Command-line entry point."""
    print("=" * 70)
    print("NES Open Tournament Golf - Forest Fill Feasibility Analyzer")
    print("=" * 70)

    # Load neighbor data
    data = load_neighbor_data()
    neighbors = data["neighbors"]

    print("\nLoaded neighbor data:")
    print(f"  Total unique tiles: {data['metadata']['total_unique_tiles']}")
    print(f"  Total relationships: {data['metadata']['total_relationships']}")

    # Run analyses
    analyze_coverage(neighbors)
    analyze_transitions(neighbors)
    analyze_forest_fill_pattern(neighbors)
    analyze_boundary_depth(neighbors)
    analyze_feasibility(neighbors)

    print("\n" + "=" * 70)
    print("Analysis complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
