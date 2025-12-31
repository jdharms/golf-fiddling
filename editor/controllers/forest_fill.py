"""
NES Open Tournament Golf - Intelligent Forest Fill Algorithm

Implements specialized forest fill that detects placeholder tiles and replaces them
with Forest Border and Forest Fill tiles based on distance from OOB border.
"""

from typing import List, Dict, Set, Tuple, Optional
from collections import deque

from golf.core.neighbor_validator import TerrainNeighborValidator


# Constants
PLACEHOLDER_TILE = 0x100  # 256 - outside NES tile range, clearly a meta value

OOB_BORDER_START = 0x80  # Out of Bounds border tiles
OOB_BORDER_END = 0x9B    # Range: $80-$9B inclusive

INNER_BORDER = 0x3F  # User can manually place these, they'll be preserved

FOREST_FILL = {0xA0, 0xA1, 0xA2, 0xA3}
FOREST_BORDER = set(range(0xA4, 0xBC))  # $A4-$BB inclusive

BORDER_DISTANCE_THRESHOLD = 3  # Cells at distance ≤ 3 from OOB get border tiles


class ForestFillRegion:
    """Represents a contiguous region of placeholder tiles to be filled with forest."""

    def __init__(self, cells: Set[Tuple[int, int]]):
        self.cells = cells  # Placeholder tile cells in this region
        self.distance_field: Dict[Tuple[int, int], int] = {}  # Manhattan distance to nearest OOB border
        self.oob_cells: Set[Tuple[int, int]] = set()  # Nearby OOB border ($80-$9B) tiles

    def calculate_distance_field(self, terrain: List[List[int]]):
        """Calculate Manhattan distance from each placeholder to nearest OOB border using BFS."""
        # First, find all OOB border tiles near this region
        self._find_nearby_oob_tiles(terrain)

        if not self.oob_cells:
            # No OOB border found - use distance to terrain edge as fallback
            self._calculate_distance_to_edge(terrain)
            return

        # BFS from all OOB border tiles to compute distances
        queue = deque()
        visited = set()

        # Start from all OOB border tiles with distance 0
        for oob_cell in self.oob_cells:
            queue.append((oob_cell, 0))
            visited.add(oob_cell)

        # BFS to find distance to each placeholder
        while queue:
            (row, col), dist = queue.popleft()

            # If this is a placeholder cell, record its distance
            if (row, col) in self.cells:
                self.distance_field[(row, col)] = dist

            # Explore neighbors
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = row + dr, col + dc

                # Check bounds
                if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                    continue

                if (nr, nc) in visited:
                    continue

                visited.add((nr, nc))
                queue.append(((nr, nc), dist + 1))

    def _find_nearby_oob_tiles(self, terrain: List[List[int]]):
        """Find OOB border tiles near this placeholder region."""
        # Check cells adjacent to placeholder region
        for row, col in self.cells:
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                nr, nc = row + dr, col + dc

                # Check bounds
                if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                    continue

                tile = terrain[nr][nc]
                if OOB_BORDER_START <= tile <= OOB_BORDER_END:
                    self.oob_cells.add((nr, nc))

    def _calculate_distance_to_edge(self, terrain: List[List[int]]):
        """Fallback: calculate distance to terrain edge if no OOB border found."""
        height = len(terrain)
        width = len(terrain[0]) if height > 0 else 0

        for row, col in self.cells:
            # Manhattan distance to nearest edge
            dist_to_edge = min(row, col, height - 1 - row, width - 1 - col)
            self.distance_field[(row, col)] = dist_to_edge + 1  # +1 so edge isn't 0

    def get_border_depth(self) -> int:
        """Heuristic: determine how deep the border layer should be."""
        if not self.distance_field:
            return 2  # Default

        max_distance = max(self.distance_field.values())
        return min(3, max_distance // 3)  # Border depth: min(3, max_dist / 3)


class PatternTracker:
    """Tracks horizontal pattern phase for forest fill ($A0-$A3)."""

    def __init__(self):
        self.region_start_col: Optional[int] = None

    def get_phase(self, col: int) -> int:
        """Get pattern phase (0-3) for column."""
        if self.region_start_col is None:
            self.region_start_col = col
            return 0

        return (col - self.region_start_col) % 4

    def get_expected_tile(self, col: int) -> int:
        """Get expected fill tile: $A0 + phase"""
        phase = self.get_phase(col)
        return 0xA0 + phase


class ForestFiller:
    """Intelligent forest fill algorithm using Wave Function Collapse."""

    def __init__(self, neighbor_validator: TerrainNeighborValidator):
        self.validator = neighbor_validator
        self.placeholder_tile = PLACEHOLDER_TILE

    def detect_regions(self, terrain: List[List[int]]) -> List[ForestFillRegion]:
        """Find all contiguous regions of placeholder tiles."""
        if not terrain:
            return []

        height = len(terrain)
        width = len(terrain[0]) if height > 0 else 0

        visited = set()
        regions = []

        # Flood fill from each unvisited placeholder
        for row in range(height):
            for col in range(width):
                if (row, col) in visited:
                    continue

                if terrain[row][col] != PLACEHOLDER_TILE:
                    continue

                # Found unvisited placeholder - flood fill to find region
                region_cells = self._flood_fill_placeholder(terrain, row, col, visited)
                if region_cells:
                    region = ForestFillRegion(region_cells)
                    region.calculate_distance_field(terrain)
                    regions.append(region)

        return regions

    def _flood_fill_placeholder(self, terrain: List[List[int]], start_row: int, start_col: int,
                                 visited: Set[Tuple[int, int]]) -> Set[Tuple[int, int]]:
        """Flood fill to find all connected placeholder tiles."""
        height = len(terrain)
        width = len(terrain[0])

        region_cells = set()
        queue = deque([(start_row, start_col)])
        visited.add((start_row, start_col))

        while queue:
            row, col = queue.popleft()
            region_cells.add((row, col))

            # Check 4-connected neighbors
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = row + dr, col + dc

                # Check bounds
                if nr < 0 or nr >= height or nc < 0 or nc >= width:
                    continue

                if (nr, nc) in visited:
                    continue

                # Only continue if it's also a placeholder
                if terrain[nr][nc] != PLACEHOLDER_TILE:
                    continue

                visited.add((nr, nc))
                queue.append((nr, nc))

        return region_cells

    def fill_region(self, terrain: List[List[int]], region: ForestFillRegion) -> Dict[Tuple[int, int], int]:
        """Fill a placeholder region using Wave Function Collapse with lookahead."""
        # Initialize superposition for each cell
        superposition: Dict[Tuple[int, int], Set[int]] = {}

        for cell in region.cells:
            # Start with all forest tiles as possibilities
            superposition[cell] = FOREST_FILL | FOREST_BORDER

        # Initial constraint propagation from existing terrain
        for cell in region.cells:
            self._propagate_constraints(cell, terrain, region, superposition, {})

        # Track pattern for each row
        pattern_trackers: Dict[int, PatternTracker] = {}

        # Wave function collapse loop with lookahead
        collapsed: Dict[Tuple[int, int], int] = {}

        while len(collapsed) < len(region.cells):
            # Find cell with minimum entropy (excluding contradicted cells)
            min_entropy_cell = self._find_min_entropy_cell(superposition, collapsed)

            if min_entropy_cell is None:
                # No more cells to collapse (all remaining have contradictions)
                break

            row, col = min_entropy_cell
            possibilities = list(superposition[min_entropy_cell])

            if not possibilities:
                # This cell has a contradiction - skip it and mark as collapsed with a fallback
                print(f"Warning: No valid tile found for ({row}, {col}), using fallback")
                # Use a neutral fill tile as fallback
                fallback_tile = 0xA0  # Basic forest fill
                collapsed[min_entropy_cell] = fallback_tile
                superposition[min_entropy_cell] = {fallback_tile}
                # Don't propagate from fallback to avoid cascading issues
                continue

            # Get scoring parameters
            distance = region.distance_field.get((row, col), 999)
            if row not in pattern_trackers:
                pattern_trackers[row] = PatternTracker()
            pattern_phase = pattern_trackers[row].get_phase(col)
            use_border = distance <= BORDER_DISTANCE_THRESHOLD

            # Select best tile with lookahead (picks least bad if all create contradictions)
            best_tile = self._select_tile_with_lookahead(
                possibilities, min_entropy_cell, terrain, region,
                superposition, collapsed, distance, pattern_phase, use_border
            )

            if best_tile is None:
                # This really shouldn't happen, but fallback to first possibility
                print(f"Warning: Could not select tile for ({row}, {col}), using fallback")
                best_tile = possibilities[0]

            # Collapse this cell
            collapsed[min_entropy_cell] = best_tile
            superposition[min_entropy_cell] = {best_tile}

            # Propagate constraints
            self._propagate_constraints(min_entropy_cell, terrain, region, superposition, collapsed)

        return collapsed

    def _select_tile_with_lookahead(self, possibilities: List[int], cell: Tuple[int, int],
                                     terrain: List[List[int]], region: ForestFillRegion,
                                     superposition: Dict[Tuple[int, int], Set[int]],
                                     collapsed: Dict[Tuple[int, int], int],
                                     distance: int, pattern_phase: int, use_border: bool) -> Optional[int]:
        """Select best tile that creates fewest contradictions."""
        # Score all possibilities
        tile_scores = []
        for tile in possibilities:
            pattern_score = self._score_tile(tile, distance, pattern_phase, use_border)

            # Test if this tile would create contradictions
            test_superposition = {c: p.copy() for c, p in superposition.items()}
            test_collapsed = collapsed.copy()

            # Collapse with this tile
            test_collapsed[cell] = tile
            test_superposition[cell] = {tile}

            # Propagate
            self._propagate_constraints(cell, terrain, region, test_superposition, test_collapsed)

            # Count contradictions and cells with reduced possibilities
            contradictions = sum(
                1 for c in region.cells
                if c not in test_collapsed and len(test_superposition[c]) == 0
            )

            # Count how much we reduced total entropy (lower is better)
            total_reduced_possibilities = sum(
                len(superposition[c]) - len(test_superposition[c])
                for c in region.cells
                if c not in test_collapsed and len(test_superposition[c]) > 0
            )

            # Combined score: prioritize no contradictions, then pattern match, then less entropy reduction
            combined_score = (
                -contradictions * 1000,  # Negative because we want to minimize
                pattern_score,           # Positive because higher is better
                -total_reduced_possibilities  # Negative because we want to minimize
            )

            tile_scores.append((combined_score, tile))

        # Sort by combined score (descending)
        tile_scores.sort(reverse=True)

        # Return best tile (even if it creates some contradictions)
        return tile_scores[0][1] if tile_scores else None

    def _find_min_entropy_cell(self, superposition: Dict[Tuple[int, int], Set[int]],
                               collapsed: Dict[Tuple[int, int], int]) -> Optional[Tuple[int, int]]:
        """Find uncollapsed cell with minimum entropy (fewest possibilities), excluding contradictions."""
        min_entropy = float('inf')
        min_cell = None
        has_contradiction = None

        for cell, possibilities in superposition.items():
            if cell in collapsed:
                continue

            entropy = len(possibilities)
            if entropy == 0:
                # Track contradictions but don't prioritize them
                if has_contradiction is None:
                    has_contradiction = cell
                continue

            if entropy < min_entropy:
                min_entropy = entropy
                min_cell = cell

        # Prefer cells with possibilities, but return contradiction if that's all we have
        return min_cell if min_cell is not None else has_contradiction

    def _propagate_constraints(self, cell: Tuple[int, int], terrain: List[List[int]],
                               region: ForestFillRegion,
                               superposition: Dict[Tuple[int, int], Set[int]],
                               collapsed: Dict[Tuple[int, int], int]):
        """Propagate constraints from a cell to its neighbors."""
        queue = deque([cell])

        while queue:
            current = queue.popleft()
            row, col = current

            # For each neighbor direction
            for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                       ("left", (0, -1)), ("right", (0, 1))]:
                nr, nc = row + dr, col + dc
                neighbor_cell = (nr, nc)

                # Skip if out of bounds
                if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                    continue

                # Skip if not in our region
                if neighbor_cell not in region.cells:
                    continue

                # Skip if already collapsed
                if neighbor_cell in collapsed:
                    continue

                # Calculate what tiles are still valid for this neighbor
                old_possibilities = superposition[neighbor_cell].copy()
                new_possibilities = self._get_constrained_possibilities(
                    neighbor_cell, terrain, region, superposition, collapsed
                )

                # Update possibilities
                superposition[neighbor_cell] = new_possibilities

                # If possibilities changed, propagate to its neighbors
                if new_possibilities != old_possibilities:
                    queue.append(neighbor_cell)

    def _get_constrained_possibilities(self, cell: Tuple[int, int], terrain: List[List[int]],
                                       region: ForestFillRegion,
                                       superposition: Dict[Tuple[int, int], Set[int]],
                                       collapsed: Dict[Tuple[int, int], int]) -> Set[int]:
        """Get valid tile possibilities for a cell based on current constraints."""
        row, col = cell
        current_possibilities = superposition.get(cell, FOREST_FILL | FOREST_BORDER)

        # Check each direction for constraints
        for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                   ("left", (0, -1)), ("right", (0, 1))]:
            nr, nc = row + dr, col + dc

            # Skip if out of bounds
            if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                continue

            # Get neighbor tile value
            neighbor_cell = (nr, nc)
            if neighbor_cell in collapsed:
                neighbor_tile = collapsed[neighbor_cell]
            elif terrain[nr][nc] != PLACEHOLDER_TILE:
                neighbor_tile = terrain[nr][nc]
            else:
                # Neighbor is uncollapsed placeholder - no constraint yet
                continue

            # Filter possibilities based on this neighbor
            valid_for_this_neighbor = set()
            for candidate in current_possibilities:
                if candidate not in self.validator.neighbors:
                    continue

                valid_neighbors = self.validator.neighbors[candidate].get(direction, set())
                if neighbor_tile in valid_neighbors:
                    valid_for_this_neighbor.add(candidate)

            # Intersect with current possibilities
            current_possibilities &= valid_for_this_neighbor

        return current_possibilities

    def _select_best_tile(self, valid_tiles: Set[int], distance: int,
                         pattern_phase: int, use_border: bool) -> Optional[int]:
        """Select best tile from valid candidates based on scoring."""
        if not valid_tiles:
            return None

        # Score each candidate
        scored = []
        for tile in valid_tiles:
            score = self._score_tile(tile, distance, pattern_phase, use_border)
            scored.append((score, tile))

        # Sort by score (descending) and return best
        scored.sort(reverse=True)
        return scored[0][1]

    def _score_tile(self, tile: int, distance: int, pattern_phase: int, use_border: bool) -> int:
        """Score a candidate tile."""
        score = 0

        # Category match (highest priority)
        is_border = tile in FOREST_BORDER
        is_fill = tile in FOREST_FILL

        if use_border and is_border:
            score += 100
        elif not use_border and is_fill:
            score += 100

        # Pattern alignment (for fill tiles)
        if is_fill:
            expected_tile = 0xA0 + pattern_phase
            if tile == expected_tile:
                score += 50

        return score

    @staticmethod
    def is_placeholder(tile_value: int) -> bool:
        """Check if tile is the placeholder that should be replaced."""
        return tile_value == PLACEHOLDER_TILE
