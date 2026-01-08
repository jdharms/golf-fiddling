"""
NES Open Tournament Golf - Intelligent Forest Fill Algorithm

Deterministic algorithm based on tile family constraints and tree exertion matching,
using arc consistency for bidirectional constraint propagation.
"""

from __future__ import annotations
from collections import deque

# Constants
PLACEHOLDER_TILE = 0x100  # 256 - outside NES tile range, clearly a meta value

OOB_BORDER_START = 0x80  # Out of Bounds border tiles
OOB_BORDER_END = 0x9B  # Range: $80-$9B inclusive

# Universal fallback tile - works with any family, exerts all zeros.
# Used sparingly when constraints are otherwise unsatisfiable.
INNER_BORDER = 0x3F

FOREST_FILL = frozenset({0xA0, 0xA1, 0xA2, 0xA3})
FOREST_BORDER = frozenset(range(0xA4, 0xBC))  # $A4-$BB inclusive
ALL_FOREST_TILES = FOREST_FILL | FOREST_BORDER

# Direction constants
UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
DIRECTIONS = (UP, RIGHT, DOWN, LEFT)
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}
DIRECTION_DELTAS = {
    UP: (-1, 0),
    RIGHT: (0, 1),
    DOWN: (1, 0),
    LEFT: (0, -1),
}

# Tile exertion data: {tile_id: (up, right, down, left)}
# Each direction is a tuple of bits representing tree exertions.
# Two adjacent tiles match if their exertions on the shared edge are identical.
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

# Group tiles by family (fill tile first for preference during selection)
FAMILY_TILES = {
    0xA0: (0xA0, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9),
    0xA1: (0xA1, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF),
    0xA2: (0xA2, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5),
    0xA3: (0xA3, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xBB),
}


def get_family_for_position(row: int, col: int, orientation: int = 0xA0) -> int:
    """
    Get the fill tile family for a position given an orientation.

    The 2x4 tiling pattern repeats as:
        Row 0: O, O+1, O+2, O+3, O, O+1, ...
        Row 1: O+2, O+3, O, O+1, O+2, ...

    Args:
        row: Row position
        col: Column position
        orientation: Fill tile at position (0,0), one of 0xA0-0xA3

    Returns:
        The family fill tile (0xA0-0xA3) for this position
    """
    base = orientation - 0xA0
    offset = (col + 2 * (row % 2)) % 4
    family_index = (base + offset) % 4
    return 0xA0 + family_index


def get_zero_exertion(family: int, direction: int) -> tuple[int, ...]:
    """Get the all-zeros exertion tuple matching a family's edge bit-width."""
    fill_exertion = TILE_EXERTIONS[family][direction]
    return tuple(0 for _ in fill_exertion)


def is_all_zeros(exertion: tuple[int, ...]) -> bool:
    """Check if an exertion is all zeros (regardless of bit-width)."""
    return all(b == 0 for b in exertion)


def count_ones(tile: int) -> int:
    """Count total 1-bits in a tile's exertions (higher = more "fill-like")."""
    return sum(sum(bits) for bits in TILE_EXERTIONS[tile])


class ForestFillRegion:
    """
    Represents a contiguous region to be filled with forest tiles.
    May contain placeholder tiles and existing forest tiles that are contiguous.
    """

    def __init__(self, cells: set[tuple[int, int]]):
        self.cells = cells

    def contains_tile(self, tile: tuple[int, int]) -> bool:
        return tile in self.cells


class CellConstraints:
    """
    Tracks achievable exertions for a single cell.

    For each direction, maintains the set of exertion tuples that are still
    achievable given current constraints. Arc consistency narrows these sets
    until stable.
    """

    def __init__(self, family: int):
        self.family = family
        # Initialize with all exertions achievable by family tiles
        self.achievable: dict[int, set[tuple[int, ...]]] = {
            d: set() for d in DIRECTIONS
        }
        for tile in FAMILY_TILES[family]:
            ex = TILE_EXERTIONS[tile]
            for d in DIRECTIONS:
                self.achievable[d].add(ex[d])

        # Cache valid tiles (tiles consistent with current achievable sets)
        self._valid_tiles: set[int] | None = None

    def constrain_direction(self, direction: int, allowed: set[tuple[int, ...]]) -> bool:
        """
        Restrict achievable exertions in a direction to intersection with allowed.

        Returns True if any change was made.
        """
        old = self.achievable[direction]
        new = old & allowed
        if new != old:
            self.achievable[direction] = new
            self._valid_tiles = None  # Invalidate cache
            return True
        return False

    def constrain_to_single(self, direction: int, value: tuple[int, ...]) -> bool:
        """Constrain a direction to exactly one value."""
        return self.constrain_direction(direction, {value})

    def get_valid_tiles(self) -> set[int]:
        """Get tiles from family that satisfy all current constraints."""
        if self._valid_tiles is not None:
            return self._valid_tiles

        valid = set()
        for tile in FAMILY_TILES[self.family]:
            ex = TILE_EXERTIONS[tile]
            if all(ex[d] in self.achievable[d] for d in DIRECTIONS):
                valid.add(tile)

        self._valid_tiles = valid
        return valid

    def recompute_achievable_from_valid_tiles(self) -> set[int]:
        """
        Recompute achievable sets based on valid tiles only.

        Returns set of directions that changed.
        """
        valid = self.get_valid_tiles()
        if not valid:
            return set()

        changed_directions = set()
        for d in DIRECTIONS:
            new_achievable = {TILE_EXERTIONS[t][d] for t in valid}
            if new_achievable != self.achievable[d]:
                self.achievable[d] = new_achievable
                changed_directions.add(d)

        return changed_directions

    def is_empty(self) -> bool:
        """Check if no valid tiles remain."""
        return len(self.get_valid_tiles()) == 0

    def select_best_tile(self) -> int | None:
        """Select tile with maximum 1-bits (prefers fill tiles)."""
        valid = self.get_valid_tiles()
        if not valid:
            return None
        return max(valid, key=count_ones)


class BetterForestFiller:
    """
    Forest fill algorithm using arc consistency for constraint propagation.

    Algorithm overview:
    1. Assign each cell to a family based on position and orientation
    2. Initialize achievable exertion sets:
       - All family exertions for unconstrained edges
       - Restricted for external edges (must be zero) and pre-assigned neighbors
    3. Propagate constraints bidirectionally until stable (arc consistency)
    4. If any cell has no valid tiles, introduce INNER_BORDER and re-propagate
    5. Assign tiles: pick best valid tile for each cell

    INNER_BORDER (0x3F) serves as a universal fallback that exerts all zeros
    and can be placed at any family position. It's used sparingly to resolve
    otherwise unsatisfiable constraint conflicts.
    """

    def __init__(self, debug: bool = False):
        self.debug = debug

    def detect_regions(self, terrain: list[list[int]]) -> list[ForestFillRegion]:
        """
        Find contiguous regions of placeholder tiles using flood fill.
        Also includes existing forest tiles that are contiguous with placeholders.

        Args:
            terrain: 2D grid of tile IDs, indexed as terrain[row][col]

        Returns:
            List of ForestFillRegion objects containing connected cells.
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
                if tile != PLACEHOLDER_TILE:
                    continue

                # BFS to find contiguous region
                region_cells: set[tuple[int, int]] = set()
                queue = deque([(row, col)])
                visited.add((row, col))

                while queue:
                    cr, cc = queue.popleft()
                    region_cells.add((cr, cc))

                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = cr + dr, cc + dc
                        if (nr, nc) in visited:
                            continue
                        if 0 <= nr < height and 0 <= nc < width:
                            neighbor_tile = terrain[nr][nc]
                            if neighbor_tile == PLACEHOLDER_TILE or neighbor_tile in ALL_FOREST_TILES:
                                visited.add((nr, nc))
                                queue.append((nr, nc))

                regions.append(ForestFillRegion(region_cells))

        return regions

    def _classify_edges(
        self,
        cells_to_fill: set[tuple[int, int]],
        pre_assigned: dict[tuple[int, int], int],
        inner_border_cells: set[tuple[int, int]],
        terrain_height: int,
        terrain_width: int,
    ) -> tuple[
        dict[tuple[int, int], set[int]],  # external_edges
        dict[tuple[int, int], set[int]],  # screen_edges
        dict[tuple[int, int], set[int]],  # pre_assigned_edges
        dict[tuple[int, int], set[int]],  # inner_border_edges
        dict[tuple[int, int], set[int]],  # internal_edges
    ]:
        """Classify each cell's edges by what they border."""
        external_edges: dict[tuple[int, int], set[int]] = {}
        screen_edges: dict[tuple[int, int], set[int]] = {}
        pre_assigned_edges: dict[tuple[int, int], set[int]] = {}
        inner_border_edges: dict[tuple[int, int], set[int]] = {}
        internal_edges: dict[tuple[int, int], set[int]] = {}

        for cell in cells_to_fill:
            external_edges[cell] = set()
            screen_edges[cell] = set()
            pre_assigned_edges[cell] = set()
            inner_border_edges[cell] = set()
            internal_edges[cell] = set()
            row, col = cell

            for direction, (dr, dc) in DIRECTION_DELTAS.items():
                neighbor = (row + dr, col + dc)
                nr, nc = neighbor

                if neighbor in cells_to_fill:
                    internal_edges[cell].add(direction)
                elif neighbor in inner_border_cells:
                    inner_border_edges[cell].add(direction)
                elif neighbor in pre_assigned:
                    pre_assigned_edges[cell].add(direction)
                else:
                    external_edges[cell].add(direction)
                    if nr < 0 or nr >= terrain_height or nc < 0 or nc >= terrain_width:
                        screen_edges[cell].add(direction)

        return external_edges, screen_edges, pre_assigned_edges, inner_border_edges, internal_edges

    def _initialize_constraints(
        self,
        cells_to_fill: set[tuple[int, int]],
        cell_families: dict[tuple[int, int], int],
        pre_assigned: dict[tuple[int, int], int],
        external_edges: dict[tuple[int, int], set[int]],
        screen_edges: dict[tuple[int, int], set[int]],
        pre_assigned_edges: dict[tuple[int, int], set[int]],
        inner_border_edges: dict[tuple[int, int], set[int]],
        terrain: list[list[int]],
        terrain_height: int,
        terrain_width: int,
    ) -> dict[tuple[int, int], CellConstraints]:
        """Initialize constraint objects for each cell."""
        constraints: dict[tuple[int, int], CellConstraints] = {}

        for cell in cells_to_fill:
            family = cell_families[cell]
            constraints[cell] = CellConstraints(family)
            row, col = cell

            # Constrain external non-screen edges
            for direction in external_edges[cell]:
                if direction in screen_edges[cell]:
                    continue  # Screen edges have no constraint

                dr, dc = DIRECTION_DELTAS[direction]
                nr, nc = row + dr, col + dc

                if terrain and 0 <= nr < terrain_height and 0 <= nc < terrain_width:
                    neighbor_tile = terrain[nr][nc]
                    if neighbor_tile in TILE_EXERTIONS:
                        # External forest neighbor: must match its exertion
                        opposite = OPPOSITE[direction]
                        required = TILE_EXERTIONS[neighbor_tile][opposite]
                        constraints[cell].constrain_to_single(direction, required)
                    else:
                        # Non-forest neighbor: must exert zero
                        zero = get_zero_exertion(family, direction)
                        constraints[cell].constrain_to_single(direction, zero)
                else:
                    # Out of terrain bounds (shouldn't happen if not screen edge)
                    zero = get_zero_exertion(family, direction)
                    constraints[cell].constrain_to_single(direction, zero)

            # Constrain edges adjacent to pre-assigned cells
            for direction in pre_assigned_edges[cell]:
                dr, dc = DIRECTION_DELTAS[direction]
                neighbor = (row + dr, col + dc)
                neighbor_tile = pre_assigned[neighbor]
                opposite = OPPOSITE[direction]
                required = TILE_EXERTIONS[neighbor_tile][opposite]
                constraints[cell].constrain_to_single(direction, required)

            # Constrain edges adjacent to INNER_BORDER cells
            # INNER_BORDER is compatible with any zero exertion regardless of bit-width
            for direction in inner_border_edges[cell]:
                # Find all zero-exerting values this cell can achieve in this direction
                zero_exertions = {
                    ex for ex in constraints[cell].achievable[direction]
                    if is_all_zeros(ex)
                }
                if zero_exertions:
                    constraints[cell].constrain_direction(direction, zero_exertions)
                else:
                    # No zero option available - constrain to expected zero anyway
                    # (will likely become empty and need INNER_BORDER)
                    zero = get_zero_exertion(family, direction)
                    constraints[cell].constrain_to_single(direction, zero)

        return constraints

    def _propagate_arc_consistency(
        self,
        cells_to_fill: set[tuple[int, int]],
        constraints: dict[tuple[int, int], CellConstraints],
        internal_edges: dict[tuple[int, int], set[int]],
    ) -> None:
        """
        Propagate constraints until arc consistent.

        Uses a worklist algorithm: when a cell's achievable set narrows,
        its neighbors are re-examined.
        """
        # Initialize worklist with all internal edge pairs
        # Each item is (cell, direction) meaning "check cell's constraint toward that direction"
        worklist: deque[tuple[tuple[int, int], int]] = deque()
        in_worklist: set[tuple[tuple[int, int], int]] = set()

        for cell in cells_to_fill:
            for direction in internal_edges[cell]:
                item = (cell, direction)
                worklist.append(item)
                in_worklist.add(item)

        max_iterations = len(cells_to_fill) * 50 + 500
        iterations = 0

        while worklist and iterations < max_iterations:
            iterations += 1
            cell, direction = worklist.popleft()
            in_worklist.discard((cell, direction))

            row, col = cell
            dr, dc = DIRECTION_DELTAS[direction]
            neighbor = (row + dr, col + dc)

            if neighbor not in constraints:
                continue

            opposite = OPPOSITE[direction]
            cell_constraints = constraints[cell]
            neighbor_constraints = constraints[neighbor]

            # Get what each can currently achieve toward the other
            cell_can = cell_constraints.achievable[direction]
            neighbor_can = neighbor_constraints.achievable[opposite]

            # They must match - compute intersection
            common = cell_can & neighbor_can

            if not common:
                # No valid matching possible - constraint failure
                # Leave as-is; will be detected later
                continue

            # Narrow both sides to common values
            cell_changed = cell_constraints.constrain_direction(direction, common)
            neighbor_changed = neighbor_constraints.constrain_direction(opposite, common)

            # If a cell's achievable set changed, recompute valid tiles and
            # potentially narrow other edges, then add ALL edges (including
            # the one we just processed from the neighbor's perspective)
            if cell_changed:
                other_changed = cell_constraints.recompute_achievable_from_valid_tiles()
                # Add all changed internal edges to worklist
                for d in other_changed:
                    if d in internal_edges[cell]:
                        item = (cell, d)
                        if item not in in_worklist:
                            worklist.append(item)
                            in_worklist.add(item)
                # Also re-check edges FROM neighbors TO this cell, since our
                # achievable set changed and neighbors might need to re-narrow
                for d in internal_edges[cell]:
                    dr2, dc2 = DIRECTION_DELTAS[d]
                    nb = (row + dr2, col + dc2)
                    if nb in constraints:
                        opp = OPPOSITE[d]
                        item = (nb, opp)
                        if item not in in_worklist:
                            worklist.append(item)
                            in_worklist.add(item)

            if neighbor_changed:
                other_changed = neighbor_constraints.recompute_achievable_from_valid_tiles()
                nr, nc = neighbor
                for d in other_changed:
                    if d in internal_edges.get(neighbor, set()):
                        item = (neighbor, d)
                        if item not in in_worklist:
                            worklist.append(item)
                            in_worklist.add(item)
                # Also re-check edges FROM this cell and other neighbors TO neighbor
                for d in internal_edges.get(neighbor, set()):
                    dr2, dc2 = DIRECTION_DELTAS[d]
                    nb = (nr + dr2, nc + dc2)
                    if nb in constraints:
                        opp = OPPOSITE[d]
                        item = (nb, opp)
                        if item not in in_worklist:
                            worklist.append(item)
                            in_worklist.add(item)

    def _fill_with_orientation(
        self,
        region: ForestFillRegion,
        orientation: int,
        terrain: list[list[int]],
    ) -> tuple[dict[tuple[int, int], int], int, int]:
        """
        Fill a region using arc consistency constraint propagation.

        Returns:
            (tile_assignments, failure_count, inner_border_count)
        """
        terrain_height = len(terrain) if terrain else 0
        terrain_width = len(terrain[0]) if terrain and terrain[0] else 0

        # Separate pre-assigned forest cells from cells to fill
        pre_assigned: dict[tuple[int, int], int] = {}
        cells_to_fill: set[tuple[int, int]] = set()

        for cell in region.cells:
            row, col = cell
            if terrain and 0 <= row < terrain_height and 0 <= col < terrain_width:
                existing_tile = terrain[row][col]
                if existing_tile in TILE_EXERTIONS:
                    pre_assigned[cell] = existing_tile
                else:
                    cells_to_fill.add(cell)
            else:
                cells_to_fill.add(cell)

        if not cells_to_fill:
            return dict(pre_assigned), 0, 0

        # Assign families based on position
        cell_families = {
            cell: get_family_for_position(cell[0], cell[1], orientation)
            for cell in cells_to_fill
        }

        # Count pre-assigned tiles in wrong family (orientation mismatch)
        family_mismatches = sum(
            1 for cell, tile in pre_assigned.items()
            if TILE_FAMILY[tile] != get_family_for_position(cell[0], cell[1], orientation)
        )

        # Iteratively solve with INNER_BORDER fallback
        inner_border_cells: set[tuple[int, int]] = set()
        max_inner_border_iterations = len(cells_to_fill) + 1

        for _ in range(max_inner_border_iterations):
            # Remove cells assigned to INNER_BORDER from cells_to_fill
            current_cells = cells_to_fill - inner_border_cells

            if not current_cells:
                break

            # Classify edges
            (
                external_edges,
                screen_edges,
                pre_assigned_edges,
                inner_border_edges,
                internal_edges,
            ) = self._classify_edges(
                current_cells,
                pre_assigned,
                inner_border_cells,
                terrain_height,
                terrain_width,
            )

            # Initialize constraints
            constraints = self._initialize_constraints(
                current_cells,
                cell_families,
                pre_assigned,
                external_edges,
                screen_edges,
                pre_assigned_edges,
                inner_border_edges,
                terrain,
                terrain_height,
                terrain_width,
            )

            # After initial constraints, recompute achievable sets for all cells.
            # This ensures constraints on one edge (e.g., from pre-assigned neighbor)
            # propagate to other edges of the same cell before arc consistency starts.
            for cell in current_cells:
                constraints[cell].recompute_achievable_from_valid_tiles()

            # Propagate arc consistency
            self._propagate_arc_consistency(current_cells, constraints, internal_edges)

            # Find cells with no valid tiles
            new_inner_border = False
            for cell in current_cells:
                if constraints[cell].is_empty():
                    inner_border_cells.add(cell)
                    new_inner_border = True

            if not new_inner_border:
                # All cells have valid tiles, we're done
                break

        # Final assignment
        assigned: dict[tuple[int, int], int] = {}

        # Assign INNER_BORDER to cells that needed it
        for cell in inner_border_cells:
            assigned[cell] = INNER_BORDER

        # Assign best tiles to remaining cells
        final_cells = cells_to_fill - inner_border_cells
        if final_cells:
            # Re-run constraint initialization and propagation one more time
            # with inner_border_cells finalized
            (
                external_edges,
                screen_edges,
                pre_assigned_edges,
                inner_border_edges,
                internal_edges,
            ) = self._classify_edges(
                final_cells,
                pre_assigned,
                inner_border_cells,
                terrain_height,
                terrain_width,
            )

            constraints = self._initialize_constraints(
                final_cells,
                cell_families,
                pre_assigned,
                external_edges,
                screen_edges,
                pre_assigned_edges,
                inner_border_edges,
                terrain,
                terrain_height,
                terrain_width,
            )

            # Recompute achievable sets after initial constraints
            for cell in final_cells:
                constraints[cell].recompute_achievable_from_valid_tiles()

            self._propagate_arc_consistency(final_cells, constraints, internal_edges)

            for cell in final_cells:
                tile = constraints[cell].select_best_tile()
                if tile is not None:
                    assigned[cell] = tile
                else:
                    # Shouldn't happen after INNER_BORDER iteration, but fallback
                    assigned[cell] = INNER_BORDER
                    inner_border_cells.add(cell)

        # Count edge failures
        edge_failures = self._count_edge_failures(
            cells_to_fill,
            assigned,
            cell_families,
            pre_assigned,
            inner_border_cells,
            terrain,
            terrain_height,
            terrain_width,
        )

        # Merge pre-assigned cells
        assigned.update(pre_assigned)

        total_failures = family_mismatches + edge_failures
        return assigned, total_failures, len(inner_border_cells)

    def _count_edge_failures(
        self,
        cells_to_fill: set[tuple[int, int]],
        assigned: dict[tuple[int, int], int],
        cell_families: dict[tuple[int, int], int],
        pre_assigned: dict[tuple[int, int], int],
        inner_border_cells: set[tuple[int, int]],
        terrain: list[list[int]],
        terrain_height: int,
        terrain_width: int,
    ) -> int:
        """Count edges that don't properly match."""
        failures = 0
        checked_pairs: set[tuple[tuple[int, int], tuple[int, int]]] = set()

        for cell in cells_to_fill:
            tile = assigned.get(cell)
            if tile is None:
                continue

            row, col = cell
            family = cell_families[cell]

            # Get exertions (INNER_BORDER exerts all zeros)
            if tile == INNER_BORDER:
                tile_ex = tuple(get_zero_exertion(family, d) for d in DIRECTIONS)
            else:
                tile_ex = TILE_EXERTIONS[tile]

            for direction, (dr, dc) in DIRECTION_DELTAS.items():
                nr, nc = row + dr, col + dc
                neighbor = (nr, nc)

                # Check external edges (non-screen must be zero)
                if neighbor not in cells_to_fill and neighbor not in pre_assigned:
                    if nr < 0 or nr >= terrain_height or nc < 0 or nc >= terrain_width:
                        continue  # Screen edge, no constraint

                    # Check what the external tile expects
                    if terrain and 0 <= nr < terrain_height and 0 <= nc < terrain_width:
                        neighbor_tile = terrain[nr][nc]
                        if neighbor_tile in TILE_EXERTIONS:
                            opposite = OPPOSITE[direction]
                            expected = TILE_EXERTIONS[neighbor_tile][opposite]
                            if tile_ex[direction] != expected:
                                failures += 1
                        else:
                            # Non-forest neighbor, must be zero
                            zero = get_zero_exertion(family, direction)
                            if tile_ex[direction] != zero:
                                failures += 1
                    continue

                # Check pre-assigned edges
                if neighbor in pre_assigned:
                    neighbor_tile = pre_assigned[neighbor]
                    opposite = OPPOSITE[direction]
                    expected = TILE_EXERTIONS[neighbor_tile][opposite]
                    if tile_ex[direction] != expected:
                        failures += 1
                    continue

                # Check internal edges (avoid double-counting)
                if neighbor in cells_to_fill:
                    pair = (min(cell, neighbor), max(cell, neighbor))
                    if pair in checked_pairs:
                        continue
                    checked_pairs.add(pair)

                    neighbor_tile = assigned.get(neighbor)
                    if neighbor_tile is None:
                        continue

                    opposite = OPPOSITE[direction]
                    neighbor_family = cell_families[neighbor]

                    if neighbor_tile == INNER_BORDER:
                        neighbor_ex = get_zero_exertion(neighbor_family, opposite)
                    else:
                        neighbor_ex = TILE_EXERTIONS[neighbor_tile][opposite]

                    if tile_ex[direction] != neighbor_ex:
                        failures += 1

        return failures

    def _select_best_orientation(
        self,
        region: ForestFillRegion,
        terrain: list[list[int]],
    ) -> int:
        """Try all orientations, pick best by: fewest failures, fewest INNER_BORDERs, most fills."""
        best_orientation = 0xA0
        best_failures = float('inf')
        best_inner_count = float('inf')
        best_fill_count = -1

        for orientation in [0xA0, 0xA1, 0xA2, 0xA3]:
            result, failures, inner_count = self._fill_with_orientation(
                region, orientation, terrain
            )
            fill_count = sum(1 for t in result.values() if t in FOREST_FILL)

            # Priority: fewer failures > fewer INNER_BORDERs > more fill tiles
            if (
                failures < best_failures
                or (failures == best_failures and inner_count < best_inner_count)
                or (
                    failures == best_failures
                    and inner_count == best_inner_count
                    and fill_count > best_fill_count
                )
            ):
                best_failures = failures
                best_inner_count = inner_count
                best_fill_count = fill_count
                best_orientation = orientation

        return best_orientation

    def fill_region(
        self,
        terrain: list[list[int]],
        region: ForestFillRegion,
        orientation: int | None = None,
    ) -> dict[tuple[int, int], int]:
        """
        Fill a region with forest tiles.

        Args:
            terrain: 2D grid of tile IDs
            region: Region to fill
            orientation: Force orientation (0xA0-0xA3), or None to auto-select

        Returns:
            Mapping from (row, col) to tile ID
        """
        if orientation is None:
            orientation = self._select_best_orientation(region, terrain)

        result, _, _ = self._fill_with_orientation(region, orientation, terrain)
        return result

    @staticmethod
    def is_placeholder(tile_value: int) -> bool:
        """Check if tile is the placeholder that should be replaced."""
        return tile_value == PLACEHOLDER_TILE