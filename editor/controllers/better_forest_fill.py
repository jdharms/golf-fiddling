"""
NES Open Tournament Golf - Intelligent Forest Fill Algorithm

Deterministic algorithm based on tile family constraints and tree exertion matching.
"""

# Constants
PLACEHOLDER_TILE = 0x100  # 256 - outside NES tile range, clearly a meta value

OOB_BORDER_START = 0x80  # Out of Bounds border tiles
OOB_BORDER_END = 0x9B  # Range: $80-$9B inclusive

INNER_BORDER = 0x3F  # User can manually place these, they'll be preserved

FOREST_FILL = frozenset({0xA0, 0xA1, 0xA2, 0xA3})
FOREST_BORDER = frozenset(range(0xA4, 0xBC))  # $A4-$BB inclusive
ALL_FOREST_TILES = FOREST_FILL | FOREST_BORDER

# Direction constants
UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}
# Deltas are (row_delta, col_delta) to match (row, col) tuple convention
DIRECTION_DELTAS = {
    UP: (-1, 0),     # row decreases = toward top of screen
    RIGHT: (0, 1),   # col increases = toward right
    DOWN: (1, 0),    # row increases = toward bottom of screen
    LEFT: (0, -1),   # col decreases = toward left
}

# Tile exertion data: {tile_id: (up, right, down, left)}
# Each direction is a tuple of bits representing tree exertions.
# Single-bit edges use (b,), double-bit edges use (b1, b2).
# Two adjacent tiles match if their exertions on the shared edge are identical.
#
# Family pattern:
#   A0, A3: down is 2-bit, others are 1-bit
#   A1, A2: up is 2-bit, others are 1-bit

TILE_EXERTIONS = {
    # A0 family - down is 2-bit
    0xA0: ((1,), (1,), (1, 1), (1,)),
    0xA4: ((1,), (1,), (0, 1), (0,)),
    0xA5: ((1,), (0,), (0, 0), (0,)),
    0xA6: ((1,), (0,), (1, 0), (1,)),
    0xA7: ((0,), (0,), (1, 0), (1,)),
    0xA8: ((0,), (1,), (1, 1), (1,)),
    0xA9: ((0,), (1,), (0, 1), (0,)),

    # A1 family - up is 2-bit
    0xA1: ((1, 1), (1,), (1,), (1,)),
    0xAA: ((1, 1), (1,), (0,), (0,)),
    0xAB: ((1, 0), (0,), (0,), (0,)),
    0xAC: ((1, 0), (0,), (1,), (1,)),
    0xAD: ((0, 0), (0,), (1,), (1,)),
    0xAE: ((0, 1), (1,), (1,), (1,)),
    0xAF: ((0, 1), (1,), (0,), (0,)),

    # A2 family - up is 2-bit
    0xA2: ((1, 1), (1,), (1,), (1,)),
    0xB0: ((0, 1), (1,), (1,), (0,)),
    0xB1: ((0, 0), (0,), (1,), (0,)),
    0xB2: ((1, 0), (0,), (1,), (1,)),
    0xB3: ((1, 0), (0,), (0,), (1,)),
    0xB4: ((1, 1), (1,), (0,), (1,)),
    0xB5: ((0, 1), (1,), (0,), (0,)),

    # A3 family - down is 2-bit
    0xA3: ((1,), (1,), (1, 1), (1,)),
    0xB6: ((0,), (1,), (1, 1), (0,)),
    0xB7: ((0,), (0,), (1, 0), (0,)),
    0xB8: ((1,), (0,), (1, 0), (1,)),
    0xB9: ((1,), (0,), (0, 0), (1,)),
    0xBA: ((1,), (1,), (0, 1), (1,)),
    0xBB: ((0,), (1,), (0, 1), (0,)),
}

# Map each tile to its family's fill tile
TILE_FAMILY = {
    0xA0: 0xA0, 0xA4: 0xA0, 0xA5: 0xA0, 0xA6: 0xA0,
    0xA7: 0xA0, 0xA8: 0xA0, 0xA9: 0xA0,
    0xA1: 0xA1, 0xAA: 0xA1, 0xAB: 0xA1, 0xAC: 0xA1,
    0xAD: 0xA1, 0xAE: 0xA1, 0xAF: 0xA1,
    0xA2: 0xA2, 0xB0: 0xA2, 0xB1: 0xA2, 0xB2: 0xA2,
    0xB3: 0xA2, 0xB4: 0xA2, 0xB5: 0xA2,
    0xA3: 0xA3, 0xB6: 0xA3, 0xB7: 0xA3, 0xB8: 0xA3,
    0xB9: 0xA3, 0xBA: 0xA3, 0xBB: 0xA3,
}

# Group tiles by family (fill tile first, then border tiles)
FAMILY_TILES = {
    0xA0: [0xA0, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9],
    0xA1: [0xA1, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF],
    0xA2: [0xA2, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5],
    0xA3: [0xA3, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xBB],
}


def get_family_for_position(row: int, col: int, orientation: int = 0xA0) -> int:
    """
    Get the fill tile family for a position given an orientation.

    The 2x4 tiling pattern repeats as:
        Row 0: O, O+1, O+2, O+3, O, O+1, ...
        Row 1: O+2, O+3, O, O+1, O+2, ...

    Where O is the orientation (0xA0-0xA3) determining the top-left tile.

    Args:
        row: Row position
        col: Column position
        orientation: Fill tile at position (0,0), one of 0xA0-0xA3

    Returns:
        The family fill tile (0xA0-0xA3) for this position
    """
    base = orientation - 0xA0  # 0, 1, 2, or 3
    offset = (col + 2 * (row % 2)) % 4
    family_index = (base + offset) % 4
    return 0xA0 + family_index


def count_ones(exertions: tuple[tuple[int, ...], ...]) -> int:
    """Count total 1-bits across all directions in a tile's exertions."""
    return sum(sum(bits) for bits in exertions)


def exertion_is_zero(bits: tuple[int, ...]) -> bool:
    """Check if all exertion bits are 0 (no trees on this edge)."""
    return all(b == 0 for b in bits)


def select_best_tile(
    family: int,
    constraints: dict[int, tuple[int, ...]],
) -> int | None:
    """
    Select the best tile from a family given directional constraints.

    Constraints specify the EXACT exertion required in each direction
    (to match what neighbors expect/provide).

    Among valid tiles, returns the one with maximum total 1-bits
    (to maximize fill pattern compression).

    Args:
        family: The fill tile family (0xA0-0xA3)
        constraints: Map from direction to required exertion bits

    Returns:
        Best tile ID, or None if no valid tile exists
    """
    best_tile = None
    best_score = -1

    for tile in FAMILY_TILES[family]:
        exertions = TILE_EXERTIONS[tile]
        valid = True

        for direction, required_bits in constraints.items():
            tile_bits = exertions[direction]
            # Must match exactly
            if tile_bits != required_bits:
                valid = False
                break

        if valid:
            score = count_ones(exertions)
            if score > best_score:
                best_score = score
                best_tile = tile

    return best_tile


class ForestFillRegion:
    """Represents a contiguous region of placeholder tiles to be filled with forest."""

    def __init__(self, cells: set[tuple[int, int]]):
        self.cells = cells
        self.distance_field: dict[tuple[int, int], int] = {}
        self.oob_cells: set[tuple[int, int]] = set()

    def contains_tile(self, tile: tuple[int, int]) -> bool:
        return tile in self.cells


class BetterForestFiller:
    """
    Deterministic forest fill algorithm based on tile family constraints.

    Algorithm overview:
    1. Assign each cell to a family (A0-A3) based on position and orientation
    2. Initialize constraints: external edges must exert 0
    3. Propagate constraints inward: if a cell's best tile exerts less than
       full on an internal edge, the neighbor gets constrained
    4. Once stable, assign each cell its best valid tile (maximizing 1-bits)
    """

    def __init__(
        self, debug: bool = True
    ):
        self.placeholder_tile = PLACEHOLDER_TILE
        self.debug = debug

    def detect_regions(self, terrain: list[list[int]]) -> list[ForestFillRegion]:
        """
        Find contiguous regions of placeholder tiles using flood fill.
        Also includes existing forest tiles that are contiguous with placeholders.

        Args:
            terrain: 2D grid of tile IDs, indexed as terrain[row][col]

        Returns:
            List of ForestFillRegion objects, each containing connected
            placeholder cells (and any adjacent forest tiles) and adjacent OOB border cells.
            Cell coordinates are (row, col) tuples.
            Only regions containing at least one placeholder tile are returned.
        """
        if not terrain or not terrain[0]:
            return []

        height = len(terrain)
        width = len(terrain[0])
        visited: set[tuple[int, int]] = set()
        regions: list[ForestFillRegion] = []

        for row in range(height):
            for col in range(width):
                if (row, col) in visited:
                    continue
                tile = terrain[row][col]
                # Only START a region from a placeholder tile
                # (forest tiles will be included if contiguous with placeholders)
                if tile != PLACEHOLDER_TILE:
                    continue

                # BFS to find contiguous region
                region_cells: set[tuple[int, int]] = set()
                oob_cells: set[tuple[int, int]] = set()
                queue = [(row, col)]
                visited.add((row, col))

                while queue:
                    cr, cc = queue.pop(0)
                    region_cells.add((cr, cc))

                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = cr + dr, cc + dc
                        if (nr, nc) in visited:
                            continue

                        if 0 <= nr < height and 0 <= nc < width:
                            neighbor_tile = terrain[nr][nc]
                            # Include placeholders and forest tiles in region
                            if neighbor_tile == PLACEHOLDER_TILE or neighbor_tile in ALL_FOREST_TILES:
                                visited.add((nr, nc))
                                queue.append((nr, nc))
                            elif OOB_BORDER_START <= neighbor_tile <= OOB_BORDER_END:
                                oob_cells.add((nr, nc))

                region = ForestFillRegion(region_cells)
                region.oob_cells = oob_cells
                regions.append(region)

        return regions

    def _get_external_directions(
        self, cell: tuple[int, int], region: ForestFillRegion
    ) -> set[int]:
        """
        Get directions where this cell faces outside the region.

        Args:
            cell: (row, col) position
            region: The forest region being filled

        Returns:
            Set of direction constants (UP, RIGHT, DOWN, LEFT) for external edges
        """
        row, col = cell
        external = set()

        for direction, (dr, dc) in DIRECTION_DELTAS.items():
            neighbor = (row + dr, col + dc)
            if neighbor not in region.cells:
                external.add(direction)

        return external

    def _select_best_orientation(
        self,
        region: ForestFillRegion,
        terrain: list[list[int]] | None = None,
    ) -> int:
        """
        Select the best orientation for a region by trying all four
        and picking the one with fewest failures, then most fill tiles.

        Args:
            region: The forest region to fill
            terrain: The terrain grid for neighbor lookup

        Returns:
            Best orientation (0xA0-0xA3)
        """
        best_orientation = 0xA0
        best_failures = float('inf')
        best_fill_count = -1

        for orientation in [0xA0, 0xA1, 0xA2, 0xA3]:
            result, failures = self._fill_with_orientation(
                region, orientation, terrain
            )
            fill_count = sum(1 for tile in result.values() if tile in FOREST_FILL)

            # Prefer fewer failures, then more fill tiles
            if (failures < best_failures or
                (failures == best_failures and fill_count > best_fill_count)):
                best_failures = failures
                best_fill_count = fill_count
                best_orientation = orientation

        return best_orientation

    def _fill_with_orientation(
        self,
        region: ForestFillRegion,
        orientation: int,
        terrain: list[list[int]] | None = None,
    ) -> tuple[dict[tuple[int, int], int], int]:
        """
        Fill a region with a specific orientation.

        Args:
            region: The forest region to fill
            orientation: Which fill tile (0xA0-0xA3) goes at the origin
            terrain: The terrain grid for neighbor lookup and bounds detection

        Returns:
            Tuple of (mapping from (row, col) to tile ID, number of failures)
        """
        terrain_height = len(terrain) if terrain else 0
        terrain_width = len(terrain[0]) if terrain and terrain[0] else 0

        # Step 1: Identify cells that already have forest tiles (pre-assigned)
        # These will be preserved and used as constraint sources
        pre_assigned: dict[tuple[int, int], int] = {}
        cells_to_fill: set[tuple[int, int]] = set()

        for cell in region.cells:
            row, col = cell
            if terrain and 0 <= row < terrain_height and 0 <= col < terrain_width:
                existing_tile = terrain[row][col]
                if existing_tile in TILE_EXERTIONS:
                    # This cell already has a forest tile - preserve it
                    pre_assigned[cell] = existing_tile
                else:
                    cells_to_fill.add(cell)
            else:
                cells_to_fill.add(cell)

        # Step 2: Check compatibility of pre-assigned tiles with this orientation
        # Count how many pre-assigned tiles are in the "wrong" family for their position
        family_mismatches = 0
        for cell, tile in pre_assigned.items():
            expected_family = get_family_for_position(cell[0], cell[1], orientation)
            actual_family = TILE_FAMILY[tile]
            if actual_family != expected_family:
                family_mismatches += 1

        # Step 3: Assign families to cells that need filling based on position
        cell_families = {
            cell: get_family_for_position(cell[0], cell[1], orientation)
            for cell in cells_to_fill
        }

        # Step 4: Compute distance from boundary for cells to fill
        # Boundary includes: external edges AND edges adjacent to pre-assigned cells
        external_dirs: dict[tuple[int, int], set[int]] = {}
        screen_edge_dirs: dict[tuple[int, int], set[int]] = {}
        pre_assigned_dirs: dict[tuple[int, int], set[int]] = {}
        distance: dict[tuple[int, int], int] = {}

        for cell in cells_to_fill:
            external_dirs[cell] = set()
            screen_edge_dirs[cell] = set()
            pre_assigned_dirs[cell] = set()
            row, col = cell
            for direction, (dr, dc) in DIRECTION_DELTAS.items():
                neighbor = (row + dr, col + dc)
                if neighbor not in cells_to_fill:
                    if neighbor in pre_assigned:
                        # Adjacent to a pre-assigned cell inside region
                        pre_assigned_dirs[cell].add(direction)
                    elif neighbor not in region.cells:
                        # External edge (outside region entirely)
                        external_dirs[cell].add(direction)
                        # Check if this is a screen edge
                        nr, nc = neighbor
                        if terrain_height > 0 and terrain_width > 0:
                            if nr < 0 or nr >= terrain_height or nc < 0 or nc >= terrain_width:
                                screen_edge_dirs[cell].add(direction)

        # BFS to compute distances from boundary
        # Boundary = cells with external edges OR adjacent to pre-assigned cells
        queue = []
        for cell in cells_to_fill:
            if external_dirs[cell] or pre_assigned_dirs[cell]:
                distance[cell] = 0
                queue.append(cell)

        while queue:
            cell = queue.pop(0)
            row, col = cell
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                neighbor = (row + dr, col + dc)
                if neighbor in cells_to_fill and neighbor not in distance:
                    distance[neighbor] = distance[cell] + 1
                    queue.append(neighbor)

        # Step 5: Initialize constraints
        # - Screen edges: no constraint
        # - Pre-assigned neighbors: match their exertion
        # - External neighbors: look up tile, match if forest, else 0
        constraints: dict[tuple[int, int], dict[int, tuple[int, ...]]] = {
            cell: {} for cell in cells_to_fill
        }

        for cell in cells_to_fill:
            family = cell_families[cell]
            row, col = cell

            # Handle pre-assigned neighbor constraints
            for direction in pre_assigned_dirs[cell]:
                dr, dc = DIRECTION_DELTAS[direction]
                nr, nc = row + dr, col + dc
                neighbor_tile = pre_assigned[(nr, nc)]
                opposite = OPPOSITE[direction]
                neighbor_exertion = TILE_EXERTIONS[neighbor_tile][opposite]
                constraints[cell][direction] = neighbor_exertion

            # Handle external edge constraints
            for direction in external_dirs[cell]:
                # Skip screen edges - no constraint needed
                if direction in screen_edge_dirs[cell]:
                    continue

                # Get the actual neighbor tile from terrain
                dr, dc = DIRECTION_DELTAS[direction]
                nr, nc = row + dr, col + dc

                if terrain and 0 <= nr < terrain_height and 0 <= nc < terrain_width:
                    neighbor_tile = terrain[nr][nc]
                    opposite = OPPOSITE[direction]

                    if neighbor_tile in TILE_EXERTIONS:
                        # Neighbor is a forest tile - match its exertion toward us
                        neighbor_exertion = TILE_EXERTIONS[neighbor_tile][opposite]
                        constraints[cell][direction] = neighbor_exertion
                    else:
                        # Neighbor is not a forest tile (OOB, etc) - must exert 0
                        fill_exertion = TILE_EXERTIONS[family][direction]
                        constraints[cell][direction] = tuple(0 for _ in fill_exertion)
                else:
                    # Can't look up neighbor - assume OOB, must exert 0
                    fill_exertion = TILE_EXERTIONS[family][direction]
                    constraints[cell][direction] = tuple(0 for _ in fill_exertion)

        # Step 6: Assign tiles using BFS from constraint sources
        # Pre-assigned constraints are SACRED - never overwrite them
        assigned: dict[tuple[int, int], int] = {}

        # Track which constraints came from pre-assigned tiles (sacred, cannot be overwritten)
        sacred_constraints: dict[tuple[int, int], set[int]] = {
            cell: set() for cell in cells_to_fill
        }
        for cell in cells_to_fill:
            for direction in pre_assigned_dirs[cell]:
                if direction in constraints[cell]:
                    sacred_constraints[cell].add(direction)

        # Initialize all cells with best tile for their initial constraints
        for cell in cells_to_fill:
            family = cell_families[cell]
            tile = select_best_tile(family, constraints[cell])
            if tile is None:
                tile = self._find_fallback_tile(family, constraints[cell])
            assigned[cell] = tile

        # Iteratively propagate constraints from border tiles to neighbors
        # Keep iterating until stable
        max_iterations = len(cells_to_fill) + 10
        for iteration in range(max_iterations):
            changed = False

            for cell in cells_to_fill:
                family = cell_families[cell]
                current_tile = assigned[cell]
                row, col = cell

                # Start with sacred constraints (from pre-assigned tiles)
                cell_constraints = dict(constraints[cell])

                # Add constraints from neighbors, but ONLY if:
                # 1. The direction isn't already constrained by a sacred constraint
                # 2. The neighbor is a border tile (not a fill tile)
                for direction, (dr, dc) in DIRECTION_DELTAS.items():
                    # Skip if already has sacred constraint
                    if direction in sacred_constraints[cell]:
                        continue
                    # Skip external edges (handled in initial constraints)
                    if direction in external_dirs[cell]:
                        continue
                    # Skip pre-assigned neighbors (handled in initial constraints)
                    if direction in pre_assigned_dirs[cell]:
                        continue

                    neighbor = (row + dr, col + dc)
                    if neighbor not in assigned:
                        continue

                    neighbor_tile = assigned[neighbor]
                    neighbor_family = cell_families.get(neighbor)

                    # Only propagate constraint if neighbor is a BORDER tile (demoted from fill)
                    if neighbor_family and neighbor_tile == neighbor_family:
                        continue  # Neighbor is still a fill tile, don't constrain based on it

                    opposite = OPPOSITE[direction]
                    neighbor_exertion = TILE_EXERTIONS[neighbor_tile][opposite]
                    cell_constraints[direction] = neighbor_exertion

                # Find best tile satisfying all constraints
                best_tile = select_best_tile(family, cell_constraints)
                if best_tile is None:
                    best_tile = self._find_fallback_tile(family, cell_constraints)

                if assigned[cell] != best_tile:
                    assigned[cell] = best_tile
                    changed = True

            if not changed:
                break

        # Final pass: count failures (edge mismatches)
        tile_failures = 0
        for cell in cells_to_fill:
            tile = assigned[cell]
            tile_ex = TILE_EXERTIONS[tile]
            row, col = cell

            for direction, (dr, dc) in DIRECTION_DELTAS.items():
                # External non-screen edges must be 0
                if direction in external_dirs[cell] and direction not in screen_edge_dirs[cell]:
                    if not all(b == 0 for b in tile_ex[direction]):
                        tile_failures += 1

                # Pre-assigned edges must match
                elif direction in pre_assigned_dirs[cell]:
                    neighbor = (row + dr, col + dc)
                    neighbor_tile = pre_assigned[neighbor]
                    opposite = OPPOSITE[direction]
                    if tile_ex[direction] != TILE_EXERTIONS[neighbor_tile][opposite]:
                        tile_failures += 1

        # Step 7: Merge pre-assigned cells into the result
        # Pre-assigned cells are preserved as-is
        assigned.update(pre_assigned)

        # Total failures = family mismatches (pre-assigned in wrong family) + edge mismatches
        total_failures = family_mismatches + tile_failures

        return assigned, total_failures

    def _find_fallback_tile(
        self, family: int, constraints: dict[int, tuple[int, ...]]
    ) -> int:
        """
        Find a tile that minimizes constraint violations when no perfect match exists.
        """
        best_tile = family  # Default to fill tile
        best_violations = float('inf')

        for tile in FAMILY_TILES[family]:
            exertions = TILE_EXERTIONS[tile]
            violations = 0

            for direction, required_bits in constraints.items():
                tile_bits = exertions[direction]
                # Count bit mismatches
                for tb, rb in zip(tile_bits, required_bits):
                    if tb != rb:
                        violations += 1

            if violations < best_violations:
                best_violations = violations
                best_tile = tile

        return best_tile

    def fill_region(
        self,
        terrain: list[list[int]],
        region: ForestFillRegion,
        max_backtracks: int = 1000,
        orientation: int | None = None,
    ) -> dict[tuple[int, int], int]:
        """
        Fill a region with forest tiles using deterministic algorithm.

        Args:
            terrain: The terrain grid (used for neighbor lookup and bounds)
            region: The region to fill
            max_backtracks: Unused, kept for API compatibility
            orientation: Force a specific orientation (0xA0-0xA3), or None
                        to auto-select the best one

        Returns:
            Mapping from (row, col) cell positions to tile IDs
        """
        if orientation is None:
            orientation = self._select_best_orientation(region, terrain)

        result, _ = self._fill_with_orientation(region, orientation, terrain)
        return result

    @staticmethod
    def is_placeholder(tile_value: int) -> bool:
        """Check if tile is the placeholder that should be replaced."""
        return tile_value == PLACEHOLDER_TILE