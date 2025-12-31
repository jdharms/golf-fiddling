"""
Integration tests for forest fill algorithm using real hole data.

These tests use hole_18_with_placeholders.json which is UK hole 18
with a large placeholder region (199 tiles) for testing the forest fill algorithm.

CURRENT STATUS: FAILING - Algorithm only fills 77/199 tiles successfully.
The issue appears to be with neighbor constraint matching - many cells
report "No valid tile found" even though valid forest tiles should exist.
"""

import pytest
from pathlib import Path

from golf.formats.hole_data import HoleData
from golf.core.neighbor_validator import TerrainNeighborValidator
from editor.controllers.forest_fill import ForestFiller, PLACEHOLDER_TILE


@pytest.fixture
def neighbor_validator():
    """Load the terrain neighbor validator."""
    return TerrainNeighborValidator()


@pytest.fixture
def forest_filler(neighbor_validator):
    """Create a ForestFiller instance."""
    return ForestFiller(neighbor_validator)


@pytest.fixture
def hole_18_with_placeholders():
    """Load hole 18 with placeholder tiles."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    hole_path = fixtures_dir / "hole_18_with_placeholders.json"
    hole_data = HoleData()
    hole_data.load(str(hole_path))
    return hole_data


def test_detect_placeholder_regions(forest_filler, hole_18_with_placeholders):
    """Test that placeholder regions are detected correctly."""
    terrain = hole_18_with_placeholders.terrain

    # Count placeholder tiles manually
    placeholder_count = sum(
        1 for row in terrain for tile in row if tile == PLACEHOLDER_TILE
    )

    print(f"\nTotal placeholder tiles in test data: {placeholder_count}")

    # Detect regions
    regions = forest_filler.detect_regions(terrain)

    print(f"Number of regions detected: {len(regions)}")
    for i, region in enumerate(regions):
        print(f"  Region {i+1}: {len(region.cells)} cells")
        print(f"    Distance field entries: {len(region.distance_field)}")
        print(f"    OOB cells found: {len(region.oob_cells)}")
        if region.distance_field:
            min_dist = min(region.distance_field.values())
            max_dist = max(region.distance_field.values())
            print(f"    Distance range: {min_dist} to {max_dist}")

    assert len(regions) > 0, "Should detect at least one placeholder region"

    # Total cells across all regions should match placeholder count
    total_region_cells = sum(len(region.cells) for region in regions)
    assert total_region_cells == placeholder_count, \
        f"Region cells ({total_region_cells}) should match placeholder count ({placeholder_count})"


# @pytest.mark.xfail(reason="BUG: Only fills 77/199 tiles - neighbor validation issue")
def test_fill_placeholder_regions(forest_filler, hole_18_with_placeholders):
    """Test that placeholder regions are filled with valid forest tiles.

    EXPECTED: All 199 placeholder tiles should be replaced with valid forest tiles
    ACTUAL: Only 77 tiles are filled, 122 report "No valid tile found"

    The bug is likely in _get_valid_tiles() method - it's not correctly
    querying the neighbor validator to find compatible tiles.
    """
    terrain = hole_18_with_placeholders.terrain

    # Detect regions
    regions = forest_filler.detect_regions(terrain)

    assert len(regions) > 0, "Should detect at least one region"

    # Fill all regions
    all_changes = {}
    for i, region in enumerate(regions):
        print(f"\nFilling region {i+1} with {len(region.cells)} cells...")
        changes = forest_filler.fill_region(terrain, region)
        print(f"  Generated {len(changes)} tile changes")
        all_changes.update(changes)

    print(f"\nTotal changes: {len(all_changes)}")

    # Should have filled all placeholders
    placeholder_count = sum(
        1 for row in terrain for tile in row if tile == PLACEHOLDER_TILE
    )

    assert len(all_changes) > 0, "Should generate some changes"
    print(f"  Placeholders: {placeholder_count}, Changes: {len(all_changes)}")

    # Apply changes to a copy of terrain
    import copy
    filled_terrain = copy.deepcopy(terrain)
    for (row, col), tile in all_changes.items():
        filled_terrain[row][col] = tile

    # Check that no placeholders remain
    remaining_placeholders = sum(
        1 for row in filled_terrain for tile in row if tile == PLACEHOLDER_TILE
    )

    print(f"  Remaining placeholders: {remaining_placeholders}")

    # Verify all filled tiles are valid forest tiles
    from editor.controllers.forest_fill import FOREST_FILL, FOREST_BORDER
    valid_forest_tiles = FOREST_FILL | FOREST_BORDER

    invalid_tiles = []
    for (row, col), tile in all_changes.items():
        if tile not in valid_forest_tiles:
            invalid_tiles.append((row, col, tile))

    if invalid_tiles:
        print(f"\nInvalid tiles filled (not forest tiles):")
        for row, col, tile in invalid_tiles[:10]:  # Show first 10
            print(f"  ({row}, {col}): 0x{tile:02X}")

    assert len(invalid_tiles) == 0, \
        f"All filled tiles should be forest tiles, found {len(invalid_tiles)} invalid"


# @pytest.mark.xfail(reason="Depends on test_fill_placeholder_regions which is failing")
def test_neighbor_validation_after_fill(forest_filler, neighbor_validator, hole_18_with_placeholders):
    """Test that filled regions have valid neighbor relationships.

    This test will fail until test_fill_placeholder_regions is fixed,
    since we can't validate neighbors of tiles that weren't filled.
    """
    terrain = hole_18_with_placeholders.terrain

    # Detect and fill regions
    regions = forest_filler.detect_regions(terrain)
    all_changes = {}
    for region in regions:
        changes = forest_filler.fill_region(terrain, region)
        all_changes.update(changes)

    # Apply changes
    import copy
    filled_terrain = copy.deepcopy(terrain)
    for (row, col), tile in all_changes.items():
        filled_terrain[row][col] = tile

    # Validate neighbors
    invalid_tiles = neighbor_validator.get_invalid_tiles(filled_terrain)

    if invalid_tiles:
        print(f"\n{len(invalid_tiles)} tiles with invalid neighbors:")
        for row, col in list(invalid_tiles)[:10]:  # Show first 10
            tile = filled_terrain[row][col]
            print(f"  ({row}, {col}): 0x{tile:02X}")

            # Check each neighbor
            for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                        ("left", (0, -1)), ("right", (0, 1))]:
                nr, nc = row + dr, col + dc
                if 0 <= nr < len(filled_terrain) and 0 <= nc < len(filled_terrain[0]):
                    neighbor = filled_terrain[nr][nc]
                    tile_hex = f"0x{tile:02X}"
                    neighbor_hex = f"0x{neighbor:02X}"

                    if tile_hex in neighbor_validator.neighbors:
                        valid_neighbors = neighbor_validator.neighbors[tile_hex].get(direction, [])
                        if neighbor_hex not in valid_neighbors:
                            print(f"    {direction}: {neighbor_hex} (invalid)")

    assert len(invalid_tiles) == 0, \
        f"All filled tiles should have valid neighbors, found {len(invalid_tiles)} invalid"


"""
DEBUGGING NOTES FOR NEXT SESSION:

The forest fill algorithm is partially working but has a critical bug in _get_valid_tiles().

Symptoms:
- Region detection works perfectly (finds 199 placeholder tiles in 1 region)
- Distance field calculation works (distances range from 1 to 15)
- Only 77/199 tiles get filled successfully
- 122 tiles report "No valid tile found"

Test case to reproduce:
- Load: tests/fixtures/hole_18_with_placeholders.json
- Failing cell example: (3, 13) with down neighbor 0x94 (148)

Key issue:
The neighbor validator uses decimal string keys like "148" not hex like "0x94".
This was partially fixed but the algorithm still fails to find valid tiles.

Next debugging steps:
1. Verify neighbor validator keys are correct format (str(tile_value))
2. Check if forest tiles (0xA0-0xBB) exist in neighbor validator data
3. Manually test: can any forest tile have 0x94 as a down neighbor?
4. Print debug info for one failing cell to see what valid_in_direction contains

The fix is likely in how we're querying the validator's neighbor relationships.
"""


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
