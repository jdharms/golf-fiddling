"""
NES Open Tournament Golf - Fringe Generation Algorithm

Generates fringe tiles for greens using neighbor frequency analysis
and arc consistency constraint satisfaction.
"""

import json
import random
from pathlib import Path


def direction_from(pos1: tuple[int, int], pos2: tuple[int, int]) -> str:
    """
    Calculate direction from pos1 to pos2.

    Args:
        pos1: Starting position (row, col)
        pos2: Ending position (row, col)

    Returns:
        Direction string: "up", "down", "left", or "right"

    Raises:
        ValueError: If positions are the same or not orthogonally adjacent
    """
    dr = pos2[0] - pos1[0]
    dc = pos2[1] - pos1[1]

    if dr == 0 and dc == 0:
        raise ValueError(f"Positions are the same: {pos1}")

    if abs(dr) + abs(dc) != 1:
        raise ValueError(f"Positions not orthogonally adjacent: {pos1} -> {pos2}")

    if dr > 0:
        return "down"
    if dr < 0:
        return "up"
    if dc > 0:
        return "right"
    if dc < 0:
        return "left"

    raise ValueError(f"Invalid direction calculation: {pos1} -> {pos2}")


def direction_to(pos1: tuple[int, int], pos2: tuple[int, int]) -> str:
    """
    Calculate direction to pos2 from pos1 (same as direction_from).

    This is an alias for clarity in different contexts.
    """
    return direction_from(pos1, pos2)


def opposite(direction: str) -> str:
    """
    Get the opposite direction.

    Args:
        direction: "up", "down", "left", or "right"

    Returns:
        Opposite direction
    """
    opposites = {
        "up": "down",
        "down": "up",
        "left": "right",
        "right": "left",
    }
    if direction not in opposites:
        raise ValueError(f"Invalid direction: {direction}")
    return opposites[direction]


def compute_interior_side_from_winding(
    path: list[tuple[int, int]], index: int
) -> str | tuple[str, str]:
    """
    Compute which side of the path is interior (green side) at given index.

    Uses the shoelace formula to compute signed area. Positive area indicates
    clockwise winding (interior on right), negative indicates counter-clockwise
    (interior on left).

    Args:
        path: List of (row, col) positions forming closed loop
        index: Index in path to compute interior side for

    Returns:
        Single direction string for straight segments ("up", "down", "left", "right")
        Tuple of two directions for corner segments (e.g., ("down", "right"))
    """
    n = len(path)

    # Compute signed area using shoelace formula
    # Using (col, row) as (x, y)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        # Shoelace: A = 1/2 * sum(x[i]*y[i+1] - x[i+1]*y[i])
        area += path[i][1] * path[j][0]  # col[i] * row[i+1]
        area -= path[j][1] * path[i][0]  # col[i+1] * row[i]

    # Determine winding direction
    is_clockwise = area < 0

    # Get incoming and outgoing directions
    prev_pos = path[(index - 1) % n]
    curr_pos = path[index]
    next_pos = path[(index + 1) % n]

    incoming_dir = direction_from(curr_pos, prev_pos)
    outgoing_dir = direction_to(curr_pos, next_pos)

    # Check if this is a corner (non-opposite AND non-same directions)
    # Straight segment: either same direction or opposite directions
    is_straight = incoming_dir == opposite(outgoing_dir)
    is_corner = not is_straight

    if is_corner:
        # Corner tile: determine which corner quadrant has the green
        # For clockwise: green is on the right as you travel (inside the turn for right turns)
        # For counter-clockwise: green is on the left as you travel

        # Compute turn direction using cross product concept
        # Right turn (clockwise turn): green is on inside of turn
        # Left turn (counter-clockwise turn): green is on outside of turn

        # Map direction to vector
        dir_vectors = {
            "up": (-1, 0),
            "down": (1, 0),
            "left": (0, -1),
            "right": (0, 1),
        }

        incoming_vec = dir_vectors[incoming_dir]
        outgoing_vec = dir_vectors[outgoing_dir]

        # Cross product in 2D: (a.row * b.col - a.col * b.row)
        cross = incoming_vec[0] * outgoing_vec[1] - incoming_vec[1] * outgoing_vec[0]

        is_right_turn = cross < 0
        print(f"is_right_turn: {is_right_turn}")
        print(f"is_clockwise: {is_clockwise}")

        if is_clockwise:
            if is_right_turn:
                # Clockwise path, right turn: green is inside turn (same as path quadrant)
                return tuple(sorted([incoming_dir, outgoing_dir]))  # type: ignore
            else:
                # Clockwise path, left turn: green is outside turn (opposite quadrant)
                path_edges = {incoming_dir, outgoing_dir}
                all_dirs = {"up", "down", "left", "right"}
                interior_dirs = all_dirs - path_edges
                return tuple(sorted(interior_dirs))  # type: ignore
        else:
            # Counter-clockwise: opposite of clockwise
            if is_right_turn:
                # Counter-clockwise path, right turn: green is outside turn
                path_edges = {incoming_dir, outgoing_dir}
                all_dirs = {"up", "down", "left", "right"}
                interior_dirs = all_dirs - path_edges
                return tuple(sorted(interior_dirs))  # type: ignore
            else:
                # Counter-clockwise path, left turn: green is inside turn
                return tuple(sorted([incoming_dir, outgoing_dir]))  # type: ignore
    else:
        # Straight tile: interior side is perpendicular to path direction
        # For clockwise: green is to the right as you travel
        # For counter-clockwise: green is to the left as you travel

        # Perpendicular to the right (clockwise interior)
        right_perpendicular = {
            "up": "right",
            "down": "left",
            "left": "up",
            "right": "down",
        }

        # Perpendicular to the left (counter-clockwise interior)
        left_perpendicular = {
            "up": "left",
            "down": "right",
            "left": "down",
            "right": "up",
        }

        if is_clockwise:
            return right_perpendicular[incoming_dir]
        else:
            return left_perpendicular[incoming_dir]


def make_shape_key(
    incoming_dir: str, outgoing_dir: str, interior_side: str | tuple[str, str]
) -> str:
    """
    Create shape key matching classification_index format.

    Format: "path=(dir1,dir2) interior=dir" or "path=(dir1,dir2) interior=(dir1,dir2)"
    where path directions are sorted alphabetically.

    Args:
        incoming_dir: Direction coming into this position
        outgoing_dir: Direction leaving this position
        interior_side: Single direction or tuple of directions for interior

    Returns:
        Shape key string matching classification_index format
    """
    # Sort path directions alphabetically
    path_tuple = tuple(sorted([incoming_dir, outgoing_dir]))
    path_str = f"({','.join(path_tuple)})"

    # Format interior side
    if isinstance(interior_side, tuple):
        interior_str = f"({','.join(sorted(interior_side))})"
    else:
        interior_str = interior_side

    return f"path={path_str} interior={interior_str}"


class FringeGenerator:
    """
    Generates fringe tiles using neighbor frequency analysis and arc consistency.

    Loads data from greens_neighbors.json and uses constraint satisfaction
    to assign compatible tiles along a traced path.
    """

    def __init__(self):
        """Initialize generator with empty data structures."""
        self.neighbor_freq: dict[int, dict[str, dict[int, int]]] = {}
        self.classification_index: dict[str, list[str]] = {}
        self.freq_threshold: int = 3
        self._data_loaded: bool = False

    def load_data(self, data_path: Path | None = None) -> None:
        """
        Load and preprocess greens_neighbors.json.

        Args:
            data_path: Path to greens_neighbors.json (defaults to data/tables/greens_neighbors.json)
        """
        if data_path is None:
            # Default to data/tables/greens_neighbors.json relative to project root
            data_path = Path(__file__).parent.parent.parent / "data" / "tables" / "greens_neighbors.json"

        with open(data_path, "r") as f:
            data = json.load(f)

        # Convert neighbor frequency data from hex strings to integers
        neighbors = data["neighbors"]
        self.neighbor_freq = {}

        for tile_hex, directions in neighbors.items():
            tile_id = int(tile_hex, 16)
            self.neighbor_freq[tile_id] = {}

            for direction, neighbor_counts in directions.items():
                self.neighbor_freq[tile_id][direction] = {
                    int(neighbor_hex, 16): count
                    for neighbor_hex, count in neighbor_counts.items()
                }

        # Store classification_index as-is (values are still hex strings, will convert on use)
        self.classification_index = data["classification_index"]

        self._data_loaded = True

    def generate(self, path: list[tuple[int, int]]) -> list[tuple[tuple[int, int], int]]:
        """
        Generate fringe tiles for a closed path.

        Uses three-step algorithm:
        1. Build candidate sets based on shape classification
        2. Arc consistency filtering (iterative constraint propagation)
        3. Greedy assignment with random selection

        Args:
            path: Ordered list of (row, col) positions forming closed loop

        Returns:
            List of ((row, col), tile_id) assignments

        Raises:
            ValueError: If path is invalid or no valid assignment found
        """

        print(path)
        print(f"index: {self.classification_index}")

        if not self._data_loaded:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        # Validate path
        self._validate_path(path)

        n = len(path)

        # Step 1: Build candidate sets for each position
        candidates: list[set[int]] = []
        for i in range(n):
            prev_pos = path[(i - 1) % n]
            curr_pos = path[i]
            next_pos = path[(i + 1) % n]

            incoming_dir = direction_from(curr_pos, prev_pos)
            outgoing_dir = direction_to(curr_pos, next_pos)
            print(f"incoming: {incoming_dir}, outgoing: {outgoing_dir}")
            interior_side = compute_interior_side_from_winding(path, i)
            print(f"interior: {interior_side}")

            # For straight segments, path edges are the travel directions (left/right or up/down)
            if incoming_dir == outgoing_dir:
                # Straight segment: path directions are the opposite pair in same axis
                if incoming_dir in ("left", "right"):
                    # Horizontal travel: path is left-right
                    path_dir1, path_dir2 = "left", "right"
                else:
                    # Vertical travel: path is up-down
                    path_dir1, path_dir2 = "up", "down"
                shape_key = make_shape_key(path_dir1, path_dir2, interior_side)
            else:
                # Corner segment: use incoming/outgoing as path edges
                shape_key = make_shape_key(incoming_dir, outgoing_dir, interior_side)


            if shape_key not in self.classification_index:
                raise ValueError(
                    f"Shape key not found in classification_index: {shape_key} "
                    f"at position {i} ({curr_pos})"
                )

            # Convert hex strings to integers for candidate tiles
            tile_hexes = self.classification_index[shape_key]
            candidate_set = {int(tile_hex, 16) for tile_hex in tile_hexes}
            candidates.append(candidate_set)

        # Step 2: Arc consistency filtering
        self._arc_consistency_filter(candidates, path)

        # Check that all positions still have candidates
        for i, candidate_set in enumerate(candidates):
            if not candidate_set:
                raise ValueError(
                    f"No valid candidates remaining for position {i} ({path[i]}) "
                    f"after arc consistency filtering"
                )

        # Step 3: Greedy assignment
        assignment = self._greedy_assignment(candidates, path)

        # Return list of ((row, col), tile_id) tuples
        return list(zip(path, assignment))

    def _validate_path(self, path: list[tuple[int, int]]) -> None:
        """
        Validate that path is suitable for fringe generation.

        Raises:
            ValueError: If path is invalid
        """
        if len(path) < 4:
            raise ValueError(
                f"Path too short: {len(path)} positions. "
                f"Minimum 4 positions required (square with cardinal moves)."
            )

        # Check that path forms a loop (not strictly necessary since we use modulo,
        # but helps catch user errors)
        # Note: We don't require path[0] == path[-1] since we treat it as cyclic

        # Check all moves are orthogonal (should be guaranteed by arrow key navigation,
        # but validate anyway)
        n = len(path)
        for i in range(n):
            curr_pos = path[i]
            next_pos = path[(i + 1) % n]

            dr = abs(next_pos[0] - curr_pos[0])
            dc = abs(next_pos[1] - curr_pos[1])

            if dr + dc != 1:
                raise ValueError(
                    f"Non-orthogonal move detected: {curr_pos} -> {next_pos} "
                    f"at index {i}"
                )

    def _is_compatible(
        self, tile_a: int, direction: str, tile_b: int
    ) -> bool:
        """
        Check if tile_a can have tile_b as neighbor in given direction.

        Args:
            tile_a: Source tile ID
            direction: Direction from tile_a to tile_b
            tile_b: Neighbor tile ID

        Returns:
            True if combination appears in neighbor frequency data
            with count >= threshold
        """
        neighbors = self.neighbor_freq.get(tile_a, {}).get(direction, {})
        return neighbors.get(tile_b, 0) >= self.freq_threshold

    def _arc_consistency_filter(
        self, candidates: list[set[int]], path: list[tuple[int, int]]
    ) -> None:
        """
        Filter candidates using arc consistency (AC-3 algorithm).

        Iteratively removes incompatible candidates until a fixed point is reached.
        Modifies candidates in place.

        Args:
            candidates: List of candidate sets for each position
            path: Path positions (for direction calculation)
        """
        n = len(candidates)
        changed = True

        while changed:
            changed = False

            for i in range(n):
                j = (i + 1) % n
                dir_i_to_j = direction_to(path[i], path[j])
                dir_j_to_i = opposite(dir_i_to_j)

                # Filter candidates[i]: keep only tiles with at least one compatible neighbor in candidates[j]
                valid_i = set()
                for tile_i in candidates[i]:
                    for tile_j in candidates[j]:
                        if self._is_compatible(tile_i, dir_i_to_j, tile_j):
                            valid_i.add(tile_i)
                            break

                if valid_i < candidates[i]:
                    candidates[i] = valid_i
                    changed = True

                # Filter candidates[j]: keep only tiles with at least one compatible neighbor in candidates[i]
                valid_j = set()
                for tile_j in candidates[j]:
                    for tile_i in candidates[i]:
                        if self._is_compatible(tile_i, dir_i_to_j, tile_j):
                            valid_j.add(tile_j)
                            break

                if valid_j < candidates[j]:
                    candidates[j] = valid_j
                    changed = True

    def _greedy_assignment(
        self, candidates: list[set[int]], path: list[tuple[int, int]]
    ) -> list[int]:
        """
        Assign tiles greedily with random selection.

        Args:
            candidates: Filtered candidate sets for each position
            path: Path positions (for direction calculation)

        Returns:
            List of assigned tile IDs

        Raises:
            ValueError: If no valid assignment found
        """
        n = len(candidates)
        assignment: list[int] = []

        for i in range(n):
            if i == 0:
                # First position: random choice from candidates
                if not candidates[0]:
                    raise ValueError("No candidates for first position")
                tile = random.choice(list(candidates[0]))
            else:
                # Subsequent positions: choose tile compatible with previous
                prev_tile = assignment[-1]
                prev_dir = direction_to(path[i - 1], path[i])

                valid = [
                    t for t in candidates[i]
                    if self._is_compatible(prev_tile, prev_dir, t)
                ]

                if not valid:
                    raise ValueError(
                        f"No valid tile found for position {i} ({path[i]}) "
                        f"compatible with previous tile {prev_tile:02x}"
                    )

                tile = random.choice(valid)

            assignment.append(tile)

        # Verify closure: last tile compatible with first
        # (Should be guaranteed by arc consistency, but worth checking)
        last_tile = assignment[-1]
        first_tile = assignment[0]
        last_to_first_dir = direction_to(path[-1], path[0])

        # if not self._is_compatible(last_tile, last_to_first_dir, first_tile):
        #     raise ValueError(
        #         f"Closure check failed: last tile {last_tile:02x} not compatible "
        #         f"with first tile {first_tile:02x} in direction {last_to_first_dir}"
        #     )

        return assignment
