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

BORDER_DISTANCE_THRESHOLD = 1  # Cells at distance ≤ 1 from OOB get border tiles


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


class Decision:
    """Represents a WFC decision that can be backtracked."""
    def __init__(self, cell: Tuple[int, int], chosen_tile: int, alternatives: List[int],
                 superposition_snapshot: Dict[Tuple[int, int], Set[int]],
                 collapsed_snapshot: Dict[Tuple[int, int], int]):
        self.cell = cell
        self.chosen_tile = chosen_tile
        self.alternatives = alternatives  # Remaining tiles to try (sorted by score)
        self.superposition_snapshot = superposition_snapshot
        self.collapsed_snapshot = collapsed_snapshot


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

    def fill_region(self, terrain: List[List[int]], region: ForestFillRegion,
                    max_backtracks: int = 0) -> Dict[Tuple[int, int], int]:
        """Fill a placeholder region using two-phase WFC with optional backtracking.

        Args:
            terrain: The terrain grid
            region: The region to fill
            max_backtracks: Maximum number of backtracks before giving up (default 0 = disabled)
                          Set to > 0 to enable backtracking (try 50-100 for small regions)

        Returns:
            Dict mapping (row, col) to tile values for filled cells
        """
        # Initialize superposition for each cell
        superposition: Dict[Tuple[int, int], Set[int]] = {}
        for cell in region.cells:
            superposition[cell] = FOREST_FILL | FOREST_BORDER

        # Initial constraint propagation from existing terrain
        for cell in region.cells:
            self._propagate_constraints(cell, terrain, region, superposition, {})

        # Track pattern for each row
        pattern_trackers: Dict[int, PatternTracker] = {}

        # Single-pass WFC collapse (no border/interior separation)
        collapsed: Dict[Tuple[int, int], int] = {}
        cells_to_collapse = region.cells.copy()

        if max_backtracks > 0:
            # Use backtracking version
            decision_stack: List[Decision] = []
            backtrack_count = 0

            collapsed, backtrack_count = self._collapse_phase_with_backtracking(
                cells_to_collapse, superposition, collapsed, terrain, region,
                pattern_trackers, decision_stack, backtrack_count, max_backtracks,
                use_border=False  # Single pass, no border distinction
            )

            if backtrack_count > 0:
                print(f"  Backtracked {backtrack_count} times to resolve contradictions")
        else:
            # Single-pass non-backtracking version
            while cells_to_collapse:
                # Find cell with minimum entropy across entire region
                min_entropy_cell = self._find_min_entropy_cell_in_set(
                    cells_to_collapse, superposition, collapsed
                )

                if min_entropy_cell is None:
                    # No more valid cells to collapse
                    break

                row, col = min_entropy_cell

                # Initialize pattern tracker for this row if needed
                if row not in pattern_trackers:
                    pattern_trackers[row] = PatternTracker()

                pattern_phase = pattern_trackers[row].get_phase(col)
                distance = region.distance_field.get(min_entropy_cell, 999)

                # Determine if this should be border based on distance
                use_border = distance <= BORDER_DISTANCE_THRESHOLD

                # Collapse with frequency-weighted scoring
                tile = self._collapse_cell(
                    min_entropy_cell, superposition, collapsed, terrain, region,
                    use_border=use_border, pattern_phase=pattern_phase
                )

                collapsed[min_entropy_cell] = tile
                superposition[min_entropy_cell] = {tile}
                cells_to_collapse.discard(min_entropy_cell)

                # Propagate constraints
                self._propagate_constraints(min_entropy_cell, terrain, region, superposition, collapsed)

        return collapsed

    def _collapse_phase_with_backtracking(
            self,
            cells_to_collapse: Set[Tuple[int, int]],
            superposition: Dict[Tuple[int, int], Set[int]],
            collapsed: Dict[Tuple[int, int], int],
            terrain: List[List[int]],
            region: ForestFillRegion,
            pattern_trackers: Dict[int, PatternTracker],
            decision_stack: List[Decision],
            backtrack_count: int,
            max_backtracks: int,
            use_border: bool
    ) -> Tuple[Dict[Tuple[int, int], int], int]:
        """Collapse a phase (border or interior) with backtracking on contradictions."""

        while cells_to_collapse:
            # Find cell with minimum entropy
            min_entropy_cell = self._find_min_entropy_cell_in_set(
                cells_to_collapse, superposition, collapsed
            )

            if min_entropy_cell is None:
                # Contradiction detected - try backtracking
                if not decision_stack or backtrack_count >= max_backtracks:
                    # Can't backtrack or hit limit - give up on this phase
                    print(f"  Warning: {len(cells_to_collapse)} cells remain uncollapsed")
                    break

                # Backtrack to previous decision
                backtrack_count += 1
                while decision_stack:
                    last_decision = decision_stack[-1]

                    if not last_decision.alternatives:
                        # No more alternatives for this decision - pop and continue backtracking
                        decision_stack.pop()
                        continue

                    # Try next alternative
                    next_tile = last_decision.alternatives.pop(0)

                    # Restore state from snapshot (in-place to preserve references)
                    superposition.clear()
                    for cell, poss in last_decision.superposition_snapshot.items():
                        superposition[cell] = poss.copy()

                    collapsed.clear()
                    collapsed.update(last_decision.collapsed_snapshot)

                    # Recalculate cells_to_collapse (all uncollapsed cells in single pass)
                    cells_to_collapse.clear()
                    cells_to_collapse.update({cell for cell in region.cells if cell not in collapsed})

                    # Apply alternative choice
                    collapsed[last_decision.cell] = next_tile
                    superposition[last_decision.cell] = {next_tile}
                    cells_to_collapse.discard(last_decision.cell)

                    # Propagate constraints
                    self._propagate_constraints(last_decision.cell, terrain, region, superposition, collapsed)

                    # If still have alternatives, keep decision on stack
                    if not last_decision.alternatives:
                        decision_stack.pop()

                    # Break out of backtracking loop to continue with restored state
                    break
                else:
                    # Exhausted all decisions - give up
                    print(f"  Warning: Exhausted backtrack stack, {len(cells_to_collapse)} cells remain")
                    break

                # Continue with next cell after backtracking
                continue

            # Normal collapse
            row, col = min_entropy_cell

            # Initialize pattern tracker for this row if needed
            if row not in pattern_trackers:
                pattern_trackers[row] = PatternTracker()
            pattern_phase = pattern_trackers[row].get_phase(col)

            # Determine if this should be border based on distance
            distance = region.distance_field.get(min_entropy_cell, 999)
            use_border_for_cell = distance <= BORDER_DISTANCE_THRESHOLD

            # Get possibilities and score them
            possibilities = list(superposition.get(min_entropy_cell, set()))

            if not possibilities:
                # Empty possibilities - trigger backtracking on next iteration
                min_entropy_cell = None
                continue

            # Score all possibilities to get alternatives
            scored = []
            for tile in possibilities:
                score = self._score_tile_with_context(
                    tile, min_entropy_cell, terrain, collapsed,
                    distance, pattern_phase, use_border_for_cell
                )
                scored.append((score, tile))

            # Sort by score descending
            scored.sort(reverse=True)
            sorted_tiles = [tile for score, tile in scored]

            chosen_tile = sorted_tiles[0]
            alternatives = sorted_tiles[1:] if len(sorted_tiles) > 1 else []

            # Save decision if we have alternatives (for potential backtracking)
            if alternatives:
                decision = Decision(
                    cell=min_entropy_cell,
                    chosen_tile=chosen_tile,
                    alternatives=alternatives,
                    superposition_snapshot={cell: poss.copy() for cell, poss in superposition.items()},
                    collapsed_snapshot=collapsed.copy()
                )
                decision_stack.append(decision)

            # Collapse
            collapsed[min_entropy_cell] = chosen_tile
            superposition[min_entropy_cell] = {chosen_tile}
            cells_to_collapse.discard(min_entropy_cell)

            # Propagate constraints
            self._propagate_constraints(min_entropy_cell, terrain, region, superposition, collapsed)

        return collapsed, backtrack_count

    def _collapse_cell(self, cell: Tuple[int, int], superposition: Dict[Tuple[int, int], Set[int]],
                       collapsed: Dict[Tuple[int, int], int], terrain: List[List[int]],
                       region: ForestFillRegion, use_border: bool, pattern_phase: int = 0) -> int:
        """Collapse a cell with phase-aware scoring."""
        possibilities = list(superposition.get(cell, set()))

        if not possibilities:
            # Contradiction - try to find ANY valid tile based on neighbor constraints
            all_tiles = FOREST_BORDER if use_border else FOREST_FILL
            # Calculate what tiles would be valid given current neighbors
            valid_tiles = self._get_constrained_possibilities(
                cell, terrain, region, superposition, collapsed
            )

            if valid_tiles:
                # Use any valid tile we can find
                possibilities = list(valid_tiles)
            else:
                # Last resort: try expanding to all forest tiles
                all_forest = FOREST_FILL | FOREST_BORDER
                valid_tiles = set()
                for tile in all_forest:
                    # Manually check if this tile would work
                    if self._is_tile_valid_for_cell(cell, tile, terrain, collapsed):
                        valid_tiles.add(tile)

                if valid_tiles:
                    possibilities = list(valid_tiles)
                else:
                    # True contradiction - use fallback but log warning
                    print(f"Warning: No valid tile found for {cell}, using fallback")
                    return 0xA4 if use_border else 0xA0

        if use_border:
            # Border phase: use standard WFC with lookahead for robustness
            row, col = cell
            distance = region.distance_field.get(cell, 1)
            return self._select_tile_with_lookahead(
                possibilities, cell, terrain, region, superposition, collapsed,
                distance, pattern_phase, use_border
            )
        else:
            # Fill phase: aggressive fill preference with context-aware scoring
            scored = []
            for tile in possibilities:
                score = self._score_tile_with_context(
                    tile, cell, terrain, collapsed,
                    region.distance_field.get(cell, 999),
                    pattern_phase, use_border=False
                )
                scored.append((score, tile))

            # Sort by score descending and return best
            scored.sort(reverse=True)
            return scored[0][1]

    def _is_tile_valid_for_cell(self, cell: Tuple[int, int], tile: int,
                                 terrain: List[List[int]],
                                 collapsed: Dict[Tuple[int, int], int]) -> bool:
        """Check if a tile would be valid for a cell based on its neighbors."""
        row, col = cell

        # Check each direction
        for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                   ("left", (0, -1)), ("right", (0, 1))]:
            nr, nc = row + dr, col + dc

            # Skip if out of bounds
            if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                continue

            # Get neighbor tile
            if (nr, nc) in collapsed:
                neighbor_tile = collapsed[(nr, nc)]
            elif terrain[nr][nc] != PLACEHOLDER_TILE:
                neighbor_tile = terrain[nr][nc]
            else:
                # Neighbor is uncollapsed placeholder - no constraint
                continue

            # Check if this tile can have this neighbor
            if tile not in self.validator.neighbors:
                # Tile not in validator data - can't validate
                return False

            valid_neighbors = self.validator.neighbors[tile].get(direction, set())
            if neighbor_tile not in valid_neighbors:
                return False

        return True

    def _select_tile_with_lookahead(self, possibilities: List[int], cell: Tuple[int, int],
                                     terrain: List[List[int]], region: ForestFillRegion,
                                     superposition: Dict[Tuple[int, int], Set[int]],
                                     collapsed: Dict[Tuple[int, int], int],
                                     distance: int, pattern_phase: int, use_border: bool) -> Optional[int]:
        """Select best tile that creates fewest contradictions."""
        # Score all possibilities
        tile_scores = []
        for tile in possibilities:
            pattern_score = self._score_tile_with_context(
                tile, cell, terrain, collapsed, distance, pattern_phase, use_border
            )

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

    def _find_min_entropy_cell_in_set(self, cell_set: Set[Tuple[int, int]],
                                      superposition: Dict[Tuple[int, int], Set[int]],
                                      collapsed: Dict[Tuple[int, int], int]):
        """Returns (cell, has_contradiction) tuple."""
        min_entropy = float('inf')
        min_cell = None
        has_contradiction = False

        for cell in cell_set:
            if cell in collapsed:
                continue

            entropy = len(superposition.get(cell, set()))
            if entropy == 0:
                has_contradiction = True
                continue

            if entropy < min_entropy:
                min_entropy = entropy
                min_cell = cell

        return min_cell, has_contradiction

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

    def _score_tile_with_context(self, tile: int, cell: Tuple[int, int],
                                  terrain: List[List[int]],
                                  collapsed: Dict[Tuple[int, int], int],
                                  distance: int, pattern_phase: int,
                                  use_border: bool) -> int:
        """Score a tile considering both intrinsic properties and neighbor context."""
        import math

        # Base score from pattern/category
        base_score = self._score_tile(tile, distance, pattern_phase, use_border)

        # Add frequency bonus based on existing neighbors
        frequency_score = 0
        row, col = cell
        neighbor_count = 0

        for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                    ("left", (0, -1)), ("right", (0, 1))]:
            nr, nc = row + dr, col + dc

            # Skip out of bounds
            if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                continue

            # Get neighbor tile if it's collapsed or non-placeholder
            neighbor_tile = None
            if (nr, nc) in collapsed:
                neighbor_tile = collapsed[(nr, nc)]
            elif terrain[nr][nc] != self.placeholder_tile:
                neighbor_tile = terrain[nr][nc]

            if neighbor_tile is not None:
                # Get frequency of this relationship
                freq = self.validator.get_neighbor_frequency(tile, neighbor_tile, direction)
                if freq > 0:
                    # Logarithmic scoring: log2(1 + count) to prevent extremes
                    frequency_score += 50 * math.log2(1 + freq)
                    neighbor_count += 1

                    # Bonus for fill-to-fill connections to encourage continuation
                    is_tile_fill = tile in FOREST_FILL
                    is_neighbor_fill = neighbor_tile in FOREST_FILL
                    if is_tile_fill and is_neighbor_fill:
                        # Extra bonus for continuing fill patterns
                        frequency_score += 30

        # Normalize by number of neighbors checked (average contribution)
        if neighbor_count > 0:
            frequency_score = frequency_score / neighbor_count

        return base_score + int(frequency_score)

    @staticmethod
    def is_placeholder(tile_value: int) -> bool:
        """Check if tile is the placeholder that should be replaced."""
        return tile_value == PLACEHOLDER_TILE
