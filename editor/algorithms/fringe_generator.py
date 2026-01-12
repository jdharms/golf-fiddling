"""
NES Open Tournament Golf - Fringe Generation Algorithm

Generates fringe tiles for greens using neighbor frequency analysis
and arc consistency constraint satisfaction.
"""

import json
import random
from pathlib import Path


# =============================================================================
# Direction Constants and Utilities
# =============================================================================

DIRECTIONS = ("up", "down", "left", "right")

OPPOSITES = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
}

# 90° clockwise rotation (used for "right-hand" perpendicular)
ROTATE_CW = {
    "up": "right",
    "right": "down",
    "down": "left",
    "left": "up",
}

# 90° counter-clockwise rotation (used for "left-hand" perpendicular)
ROTATE_CCW = {
    "up": "left",
    "left": "down",
    "down": "right",
    "right": "up",
}

# Direction vectors as (delta_col, delta_row) for cross product calculation
# Using (col, row) as (x, y) in screen coordinates
DIR_VECTORS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


def direction_from(pos1: tuple[int, int], pos2: tuple[int, int]) -> str:
    """
    Calculate direction from pos1 to pos2.

    Args:
        pos1: Starting position (row, col)
        pos2: Ending position (row, col)

    Returns:
        Direction string: "up", "down", "left", or "right"

    Raises:
        ValueError: If positions are not orthogonally adjacent
    """
    dr = pos2[0] - pos1[0]
    dc = pos2[1] - pos1[1]

    if (dr, dc) == (-1, 0):
        return "up"
    elif (dr, dc) == (1, 0):
        return "down"
    elif (dr, dc) == (0, -1):
        return "left"
    elif (dr, dc) == (0, 1):
        return "right"
    else:
        raise ValueError(f"Positions not orthogonally adjacent: {pos1} -> {pos2}")


def direction_to(pos1: tuple[int, int], pos2: tuple[int, int]) -> str:
    """Alias for direction_from, for semantic clarity in different contexts."""
    return direction_from(pos1, pos2)


def opposite(direction: str) -> str:
    """Get the opposite direction."""
    return OPPOSITES[direction]


# =============================================================================
# Geometry Calculations
# =============================================================================

def compute_signed_area(path: list[tuple[int, int]]) -> float:
    """
    Compute signed area of closed path using shoelace formula.

    Uses (col, row) as (x, y) in screen coordinates where row increases downward.

    Returns:
        Positive value for clockwise winding
        Negative value for counter-clockwise winding
    """
    n = len(path)
    area = 0.0

    for i in range(n):
        j = (i + 1) % n
        # Use (col, row) as (x, y)
        x_i, y_i = path[i][1], path[i][0]
        x_j, y_j = path[j][1], path[j][0]
        area += x_i * y_j - x_j * y_i

    return area / 2.0


def compute_cross_product(dir1: str, dir2: str) -> int:
    """
    Compute 2D cross product of two direction vectors.

    In screen coordinates (y increases downward):
        Positive result = clockwise rotation (right turn)
        Negative result = counter-clockwise rotation (left turn)
    """
    v1 = DIR_VECTORS[dir1]
    v2 = DIR_VECTORS[dir2]
    return v1[0] * v2[1] - v1[1] * v2[0]


def compute_interior_side(
    path: list[tuple[int, int]],
    index: int,
    is_clockwise: bool
) -> str | tuple[str, str]:
    """
    Determine which side of the path is interior (putting surface) at given index.

    For clockwise paths, interior is on the right side of travel direction.
    For counter-clockwise paths, interior is on the left side.

    Args:
        path: Closed loop of (row, col) positions
        index: Position in path to compute interior for
        is_clockwise: Whether path winds clockwise

    Returns:
        For straight segments: single direction string
        For corners: tuple of two direction strings (sorted)
    """
    n = len(path)
    prev_pos = path[(index - 1) % n]
    curr_pos = path[index]
    next_pos = path[(index + 1) % n]

    # Directions from current tile toward its path neighbors
    to_prev = direction_from(curr_pos, prev_pos)
    to_next = direction_from(curr_pos, next_pos)

    # Determine if this is a straight segment or corner
    is_straight = (to_prev == opposite(to_next))

    if is_straight:
        # For straight segments, interior is perpendicular to travel direction
        # Travel direction is to_next (direction we're moving along the path)
        travel_dir = to_next
        if is_clockwise:
            return ROTATE_CW[travel_dir]
        else:
            return ROTATE_CCW[travel_dir]
    else:
        # For corners, we need to determine convex vs concave
        # Travel INTO this tile is opposite of to_prev
        # Travel OUT OF this tile is to_next
        travel_in = opposite(to_prev)
        travel_out = to_next

        # Determine turn direction using cross product
        cross = compute_cross_product(travel_in, travel_out)
        is_right_turn = cross > 0

        # Build edge sets
        path_edges = tuple(sorted([to_prev, to_next]))
        all_dirs = set(DIRECTIONS)
        non_path_edges = tuple(sorted(all_dirs - set(path_edges)))

        # Determine if corner is convex or concave from interior's perspective
        # Convex: interior bulges into this corner (like rectangle corner)
        # Concave: interior has a bay here
        #
        # For clockwise path:
        #   - Right turn = convex (turning toward interior)
        #   - Left turn = concave (turning away from interior)
        # For CCW path: opposite
        is_convex = (is_clockwise == is_right_turn)

        if is_convex:
            # Green is in the corner of the tile (between path edges)
            return path_edges
        else:
            # Green is opposite the corner (on non-path edge side)
            return non_path_edges


def make_shape_key(
    path_edges: tuple[str, str],
    interior_side: str | tuple[str, str]
) -> str:
    """
    Create shape key string matching classification_index format.

    Format: "path=(dir1,dir2) interior=dir" or "path=(dir1,dir2) interior=(dir1,dir2)"
    Directions are sorted alphabetically within each group.
    """
    path_str = f"({','.join(sorted(path_edges))})"

    if isinstance(interior_side, tuple):
        interior_str = f"({','.join(sorted(interior_side))})"
    else:
        interior_str = interior_side

    return f"path={path_str} interior={interior_str}"


# =============================================================================
# Main Generator Class
# =============================================================================

class FringeGenerator:
    """
    Generates fringe tiles using neighbor frequency analysis and arc consistency.

    Algorithm:
        1. Load empirical neighbor frequency data from analyzed greens
        2. For each path position, determine shape classification (corner type,
           interior direction) based on path geometry
        3. Build candidate tile sets from classification index
        4. Use arc consistency (AC-3) to filter incompatible candidates
        5. Greedily assign tiles, respecting neighbor compatibility
    """

    def __init__(self):
        """Initialize generator with empty data structures."""
        self.neighbor_freq: dict[int, dict[str, dict[int, int]]] = {}
        self.classification_index: dict[str, list[int]] = {}
        self.freq_threshold: int = 1
        self._data_loaded: bool = False

    def load_data(self, data_path: Path | None = None) -> None:
        """
        Load neighbor frequency data and classification index from JSON.

        Args:
            data_path: Path to greens_neighbors.json. If None, uses default
                       location at data/tables/greens_neighbors.json
        """
        if data_path is None:
            data_path = (
                Path(__file__).parent.parent.parent
                / "data" / "tables" / "greens_neighbors.json"
            )

        with open(data_path) as f:
            data = json.load(f)

        # Convert neighbor frequency data from hex strings to integers
        self.neighbor_freq = {}
        for tile_hex, directions in data["neighbors"].items():
            tile_id = int(tile_hex, 16)
            self.neighbor_freq[tile_id] = {}
            for direction, neighbor_counts in directions.items():
                self.neighbor_freq[tile_id][direction] = {
                    int(neighbor_hex, 16): count
                    for neighbor_hex, count in neighbor_counts.items()
                }

        # Convert classification index tile values from hex to int
        self.classification_index = {}
        for shape_key, tile_hexes in data["classification_index"].items():
            self.classification_index[shape_key] = [
                int(t, 16) for t in tile_hexes
            ]

        self._data_loaded = True

    def generate(
        self,
        path: list[tuple[int, int]]
    ) -> list[tuple[tuple[int, int], int]]:
        """
        Generate fringe tiles for a closed path.

        Args:
            path: Ordered list of (row, col) positions forming a closed loop.
                  Must be traced in order (clockwise or counter-clockwise).

        Returns:
            List of ((row, col), tile_id) tuples assigning a tile to each position.

        Raises:
            RuntimeError: If data not loaded
            ValueError: If path is invalid or no valid tile assignment exists
        """
        if not self._data_loaded:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        self._validate_path(path)

        # Determine winding direction
        is_clockwise = compute_signed_area(path) > 0

        # Step 1: Build candidate sets based on shape classification
        candidates = self._build_candidate_sets(path, is_clockwise)

        # Step 2: Arc consistency filtering
        self._arc_consistency_filter(candidates, path)

        # Verify all positions still have candidates
        for i, cands in enumerate(candidates):
            if not cands:
                raise ValueError(
                    f"No valid candidates remaining for position {i} ({path[i]}) "
                    f"after arc consistency filtering"
                )

        # Step 3: Backtracking assignment
        assignment = self._backtracking_assign(candidates, path)

        return list(zip(path, assignment))

    def _validate_path(self, path: list[tuple[int, int]]) -> None:
        """
        Validate that path is suitable for fringe generation.

        Checks:
            - Minimum length of 4 positions
            - All moves are orthogonally adjacent
            - No duplicate positions
        """
        if len(path) < 4:
            raise ValueError(
                f"Path too short: {len(path)} positions (minimum 4 required)"
            )

        # Check all moves are orthogonal
        n = len(path)
        for i in range(n):
            curr = path[i]
            next_ = path[(i + 1) % n]
            dr = abs(next_[0] - curr[0])
            dc = abs(next_[1] - curr[1])
            if dr + dc != 1:
                raise ValueError(
                    f"Non-orthogonal move at index {i}: {curr} -> {next_}"
                )

        # Check for duplicates
        if len(set(path)) != len(path):
            raise ValueError("Path contains duplicate positions")

    def _build_candidate_sets(
        self,
        path: list[tuple[int, int]],
        is_clockwise: bool
    ) -> list[set[int]]:
        """
        Build candidate tile sets for each position based on shape classification.

        Each position gets candidates from the classification index entry
        matching its (path_edges, interior_side) shape key.
        """
        candidates = []
        n = len(path)

        for i in range(n):
            prev_pos = path[(i - 1) % n]
            curr_pos = path[i]
            next_pos = path[(i + 1) % n]

            # Path edges are directions from this tile to its path neighbors
            to_prev = direction_from(curr_pos, prev_pos)
            to_next = direction_from(curr_pos, next_pos)
            path_edges = (to_prev, to_next)

            # Compute interior side based on path geometry
            interior_side = compute_interior_side(path, i, is_clockwise)

            # Look up candidates from classification index
            shape_key = make_shape_key(path_edges, interior_side)

            if shape_key not in self.classification_index:
                raise ValueError(
                    f"Unknown shape key '{shape_key}' at position {i} ({curr_pos})"
                )

            candidates.append(set(self.classification_index[shape_key]))

        return candidates

    def _is_compatible(self, tile_a: int, direction: str, tile_b: int) -> bool:
        """
        Check if tile_a can have tile_b as neighbor in given direction.

        Uses frequency threshold to filter out spurious/accidental adjacencies
        from the training data.
        """
        neighbors = self.neighbor_freq.get(tile_a, {}).get(direction, {})
        return neighbors.get(tile_b, 0) >= self.freq_threshold

    def _arc_consistency_filter(
        self,
        candidates: list[set[int]],
        path: list[tuple[int, int]]
    ) -> None:
        """
        Filter candidates using arc consistency (AC-3 algorithm).

        Iteratively removes candidates that have no compatible neighbor
        in the adjacent position, until reaching a fixed point.

        Modifies candidates list in place.
        """
        n = len(candidates)
        changed = True

        while changed:
            changed = False

            for i in range(n):
                j = (i + 1) % n
                dir_i_to_j = direction_to(path[i], path[j])

                # Filter candidates[i]: keep tiles with at least one compatible neighbor in j
                valid_i = {
                    tile_i for tile_i in candidates[i]
                    if any(
                        self._is_compatible(tile_i, dir_i_to_j, tile_j)
                        for tile_j in candidates[j]
                    )
                }
                if valid_i < candidates[i]:
                    candidates[i] = valid_i
                    changed = True

                # Filter candidates[j]: keep tiles with at least one compatible neighbor in i
                valid_j = {
                    tile_j for tile_j in candidates[j]
                    if any(
                        self._is_compatible(tile_i, dir_i_to_j, tile_j)
                        for tile_i in candidates[i]
                    )
                }
                if valid_j < candidates[j]:
                    print(f"replacing {candidates[j]} with {valid_j}")
                    candidates[j] = valid_j
                    changed = True

    def _backtracking_assign(
        self,
        candidates: list[set[int]],
        path: list[tuple[int, int]]
    ) -> list[int]:
        """
        Assign tiles using backtracking search.

        Unlike greedy assignment, this correctly handles the cycle closure
        constraint by exploring alternatives when a path doesn't work out.
        """
        n = len(candidates)
        last_to_first_dir = direction_to(path[-1], path[0])

        def is_valid_extension(assignment: list[int], next_tile: int) -> bool:
            pos = len(assignment)

            # Check compatibility with previous tile
            if pos > 0:
                prev_tile = assignment[-1]
                prev_dir = direction_to(path[pos - 1], path[pos])
                if not self._is_compatible(prev_tile, prev_dir, next_tile):
                    return False

            # Check closure constraint at final position
            if pos == n - 1:
                first_tile = assignment[0]
                if not self._is_compatible(next_tile, last_to_first_dir, first_tile):
                    return False

            return True

        def backtrack(assignment: list[int]) -> list[int] | None:
            if len(assignment) == n:
                return assignment

            pos = len(assignment)
            # Shuffle for variety in output
            tile_list = list(candidates[pos])
            random.shuffle(tile_list)

            for tile in tile_list:
                if is_valid_extension(assignment, tile):
                    result = backtrack(assignment + [tile])
                    if result is not None:
                        return result

            return None

        result = backtrack([])
        if result is None:
            raise ValueError(
                "No valid tile assignment found. This may indicate incompatible "
                "path geometry or insufficient tile variety in training data."
            )

        return result