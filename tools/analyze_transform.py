"""
Analyze compression tables to find backward mappings for terrain tiles.

This tool helps determine which terrain tiles have unique "source" tiles
in the horizontal and vertical transformation tables, enabling "drag left"
and "drag up" operations in the editor.
"""

import json


def get_valid_terrain_tiles() -> list[int]:
    """Get the list of valid terrain tiles from the editor picker."""
    return [0x25, 0x27] + list(range(0x35, 0x3D)) + list(range(0x3E, 0xC0)) + [0xDF]


def create_reverse_mapping(table: list[int]) -> dict[int, list[int]]:
    """Create a reverse mapping from output tiles to input tiles."""
    reverse = {}
    for input_tile, output_tile in enumerate(table):
        if output_tile not in reverse:
            reverse[output_tile] = []
        reverse[output_tile].append(input_tile)
    return reverse


def analyze_tile_set(tables: dict, mode: str, valid_tiles: set[int], title: str):
    """Analyze a single tileset (terrain or greens)."""

    horiz_table = tables[mode]["horizontal_table"]
    vert_table = tables[mode]["vertical_table"]

    horiz_reverse = create_reverse_mapping(horiz_table)
    vert_reverse = create_reverse_mapping(vert_table)

    unique_both = []
    unique_horiz_only = []
    unique_vert_only = []
    ambiguous_horiz = []
    ambiguous_vert = []
    unreachable_horiz = []
    unreachable_vert = []

    for tile in sorted(valid_tiles):
        horiz_sources = horiz_reverse.get(tile, [])
        vert_sources = vert_reverse.get(tile, [])

        horiz_unique = len(horiz_sources) == 1
        vert_unique = len(vert_sources) == 1
        horiz_reachable = len(horiz_sources) > 0
        vert_reachable = len(vert_sources) > 0

        if horiz_unique and vert_unique:
            unique_both.append((tile, horiz_sources[0], vert_sources[0]))
        elif horiz_unique and not vert_unique:
            unique_horiz_only.append((tile, horiz_sources[0], vert_sources))
        elif vert_unique and not horiz_unique:
            unique_vert_only.append((tile, horiz_sources, vert_sources[0]))
        elif not horiz_reachable and not vert_reachable:
            pass
        elif len(horiz_sources) > 1:
            ambiguous_horiz.append((tile, horiz_sources))
        elif len(vert_sources) > 1:
            ambiguous_vert.append((tile, vert_sources))

        if not horiz_reachable:
            unreachable_horiz.append(tile)
        if not vert_reachable:
            unreachable_vert.append(tile)

    print(f"\n{title}")
    print("=" * 70)
    print(f"Total valid tiles: {len(valid_tiles)}")

    print("\n✓ Tiles with UNIQUE backward mappings (both directions):")
    print(f"  Count: {len(unique_both)}")
    if unique_both:
        for tile, h_src, v_src in unique_both[:10]:
            print(f"    0x{tile:02X} <- H: 0x{h_src:02X}, V: 0x{v_src:02X}")
        if len(unique_both) > 10:
            print(f"    ... and {len(unique_both) - 10} more")

    print("\n◐ Tiles with UNIQUE horizontal mapping only:")
    print(f"  Count: {len(unique_horiz_only)}")

    print("\n◑ Tiles with UNIQUE vertical mapping only:")
    print(f"  Count: {len(unique_vert_only)}")

    print("\n✗ Tiles with MULTIPLE possible sources (ambiguous):")
    print(f"  Horizontal: {len(ambiguous_horiz)}")
    print(f"  Vertical: {len(ambiguous_vert)}")

    print("\n⊘ Tiles with NO backward mapping (unreachable):")
    print(f"  Unreachable via horizontal: {len(unreachable_horiz)}")
    print(f"  Unreachable via vertical: {len(unreachable_vert)}")

    return {
        "unique_both": len(unique_both),
        "unique_horiz": len(unique_horiz_only),
        "unique_vert": len(unique_vert_only),
        "ambiguous_horiz": len(ambiguous_horiz),
        "ambiguous_vert": len(ambiguous_vert),
        "unreachable_horiz": len(unreachable_horiz),
        "unreachable_vert": len(unreachable_vert),
    }


def main(tables_path: str = "data/tables/compression_tables.json"):
    """Analyze the compression tables for backward mappings."""

    # Load compression tables
    with open(tables_path) as f:
        tables = json.load(f)

    # Analyze terrain
    valid_terrain = set(get_valid_terrain_tiles())
    terrain_results = analyze_tile_set(
        tables, "terrain", valid_terrain, "TERRAIN TILES"
    )

    # Analyze greens
    valid_greens = set([0x29, 0x2C] + list(range(0x30, 0xA0)) + [0xB0])
    greens_results = analyze_tile_set(tables, "greens", valid_greens, "GREENS TILES")

    # Print final summary
    print("\n" + "=" * 70)
    print("SUMMARY FOR 'DRAG LEFT/UP' IMPLEMENTATION")
    print("=" * 70)
    print("\nTerrain:")
    print(f"  Fully reversible (both directions): {terrain_results['unique_both']}")
    print(
        f"  Partially reversible: {terrain_results['unique_horiz'] + terrain_results['unique_vert']}"
    )
    print("\nGreens:")
    print(f"  Fully reversible (both directions): {greens_results['unique_both']}")
    print(
        f"  Partially reversible: {greens_results['unique_horiz'] + greens_results['unique_vert']}"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
