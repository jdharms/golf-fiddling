#!/usr/bin/env python3
"""
Analyze NES Open Tournament Golf hole data.
Usage: python analyze.py <directory_of_json_files>
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
import numpy as np


def percentile_stats(values):
    """Return min/25th/50th/75th/max statistics."""
    if not values:
        raise ValueError("values cannot be empty in percentile_stats call")
    arr = np.array(values)
    return {
        "min": float(np.min(arr)),
        "25th": float(np.percentile(arr, 25)),
        "50th": float(np.percentile(arr, 50)),
        "75th": float(np.percentile(arr, 75)),
        "max": float(np.max(arr)),
        "count": len(values),
    }


def count_on_green_tiles(greens_data):
    """Count tiles with value >= 0x30 in the greens rows."""
    count = 0
    for row in greens_data["rows"]:
        # Each row is a space-separated string of hex values
        hex_values = row.split()
        for hv in hex_values:
            if int(hv, 16) >= 0x30:
                count += 1
    return count


def load_hole_data(filepath):
    """Load a single hole JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def analyze_holes(directory):
    """Analyze all hole JSON files in the given directory."""
    dir_path = Path(directory)
    json_files = sorted(dir_path.glob("hole*.json"))

    if not json_files:
        print(f"No JSON files found in {directory}")
        sys.exit(1)

    print(f"Found {len(json_files)} hole files\n")

    # Data collectors
    distance_by_par = defaultdict(list)
    scroll_limit_to_height = defaultdict(set)
    height_to_scroll_limit = defaultdict(set)
    odd_height_holes = []
    on_green_counts = []
    compression_ratios = []
    all_holes = []

    for filepath in json_files:
        data = load_hole_data(filepath)
        all_holes.append((filepath.name, data))

        # Distance by par
        par = data["par"]
        distance = data["distance"]
        distance_by_par[par].append(distance)

        # Scroll limit and terrain height
        scroll_limit = data["scroll_limit"]
        terrain_height = data["terrain"]["height"]
        scroll_limit_to_height[scroll_limit].add(terrain_height)
        height_to_scroll_limit[terrain_height].add(scroll_limit)

        # Odd terrain height check
        if terrain_height % 2 == 1:
            odd_height_holes.append((filepath.name, data["hole"], terrain_height))

        # On-green tile count
        on_green = count_on_green_tiles(data["greens"])
        on_green_counts.append(on_green)

        # Compression ratio
        terrain_width = data["terrain"]["width"]
        compressed_size = data["_debug"]["terrain_compressed_size"]
        uncompressed_size = terrain_width * terrain_height
        ratio = compressed_size / uncompressed_size
        compression_ratios.append(ratio)

    # === Report ===
    print("=" * 60)
    print("DISTANCE STATISTICS BY PAR")
    print("=" * 60)
    for par in sorted(distance_by_par.keys()):
        stats = percentile_stats(distance_by_par[par])
        print(f"\nPar {par} (n={stats['count']}):")
        print(f"  Min:  {stats['min']:.0f}")
        print(f"  25th: {stats['25th']:.1f}")
        print(f"  50th: {stats['50th']:.1f}")
        print(f"  75th: {stats['75th']:.1f}")
        print(f"  Max:  {stats['max']:.0f}")

    print("\n" + "=" * 60)
    print("SCROLL_LIMIT vs TERRAIN HEIGHT ANALYSIS")
    print("=" * 60)

    print("\nScroll limit -> Terrain heights mapping:")
    for sl in sorted(scroll_limit_to_height.keys()):
        heights = sorted(scroll_limit_to_height[sl])
        print(f"  scroll_limit={sl}: heights={heights}")

    print("\nTerrain height -> Scroll limits mapping:")
    for h in sorted(height_to_scroll_limit.keys()):
        limits = sorted(height_to_scroll_limit[h])
        print(f"  height={h}: scroll_limits={limits}")

    # Check if it's a function (each scroll_limit maps to exactly one height)
    is_function_sl_to_h = all(len(v) == 1 for v in scroll_limit_to_height.values())
    is_function_h_to_sl = all(len(v) == 1 for v in height_to_scroll_limit.values())
    is_bijection = is_function_sl_to_h and is_function_h_to_sl

    print(f"\nIs scroll_limit -> height a function? {is_function_sl_to_h}")
    print(f"Is height -> scroll_limit a function? {is_function_h_to_sl}")
    print(f"Is the relationship a bijection? {is_bijection}")

    if is_function_sl_to_h:
        print("\nFormula inference (scroll_limit -> height):")
        pairs = [(sl, list(h)[0]) for sl, h in scroll_limit_to_height.items()]
        pairs.sort()
        # Check if linear relationship exists
        if len(pairs) >= 2:
            diffs = [(pairs[i+1][0] - pairs[i][0], pairs[i+1][1] - pairs[i][1]) 
                     for i in range(len(pairs)-1)]
            print(f"  Data points: {pairs}")
            # Try to find pattern
            sl0, h0 = pairs[0]
            if all(d[0] != 0 and d[1]/d[0] == diffs[0][1]/diffs[0][0] for d in diffs if d[0] != 0):
                slope = diffs[0][1] / diffs[0][0]
                intercept = h0 - slope * sl0
                print(f"  Appears linear: height = {slope} * scroll_limit + {intercept}")

    print("\n" + "=" * 60)
    print("ODD TERRAIN HEIGHT CHECK")
    print("=" * 60)
    if odd_height_holes:
        print(f"\nHoles with odd terrain height ({len(odd_height_holes)} found):")
        for filename, hole_num, height in odd_height_holes:
            print(f"  {filename}: Hole {hole_num}, height={height}")
    else:
        print("\nNo holes have odd terrain height.")

    print("\n" + "=" * 60)
    print("ON-GREEN TILE COUNT STATISTICS")
    print("=" * 60)
    stats = percentile_stats(on_green_counts)
    print(f"\nTiles on green (value >= 0x30) across all holes (n={stats['count']}):")
    print(f"  Min:  {stats['min']:.0f}")
    print(f"  25th: {stats['25th']:.1f}")
    print(f"  50th: {stats['50th']:.1f}")
    print(f"  75th: {stats['75th']:.1f}")
    print(f"  Max:  {stats['max']:.0f}")

    print("\n" + "=" * 60)
    print("TERRAIN COMPRESSION RATIO")
    print("=" * 60)
    ratio_stats = percentile_stats(compression_ratios)
    print(f"\nCompression ratio = compressed_size / (width * height)")
    print(f"Average: {np.mean(compression_ratios):.4f}")
    print(f"Std dev: {np.std(compression_ratios):.4f}")
    print(f"\nDistribution:")
    print(f"  Min:  {ratio_stats['min']:.4f}")
    print(f"  25th: {ratio_stats['25th']:.4f}")
    print(f"  50th: {ratio_stats['50th']:.4f}")
    print(f"  75th: {ratio_stats['75th']:.4f}")
    print(f"  Max:  {ratio_stats['max']:.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <directory_of_json_files>")
        sys.exit(1)

    analyze_holes(sys.argv[1])