"""
NES Open Tournament Golf - Intelligent Forest Fill Algorithm (Revised)

Implements specialized forest fill that detects placeholder tiles and replaces them
with Forest Border and Forest Fill tiles based on distance from OOB border.
"""

from typing import List, Dict, Set, Tuple, Optional
from collections import deque
import math

from golf.core.neighbor_validator import TerrainNeighborValidator


# Constants
PLACEHOLDER_TILE = 0x100  # 256 - outside NES tile range, clearly a meta value

OOB_BORDER_START = 0x80  # Out of Bounds border tiles
OOB_BORDER_END = 0x9B    # Range: $80-$9B inclusive

INNER_BORDER = 0x3F  # User can manually place these, they'll be preserved

FOREST_FILL = frozenset({0xA0, 0xA1, 0xA2, 0xA3})
FOREST_BORDER = frozenset(range(0xA4, 0xBC))  # $A4-$BB inclusive
ALL_FOREST_TILES = FOREST_FILL | FOREST_BORDER

BORDER_DISTANCE_THRESHOLD = 1  # Cells at distance ≤ 1 from OOB get border tiles


class ForestFillRegion:
    """Represents a contiguous region of placeholder tiles to be filled with forest."""

    def __init__(self, cells: Set[Tuple[int, int]]):
        self.cells = cells  # Placeholder tile cells in this region
        self.distance_field: Dict[Tuple[int, int], int] = {}  # Manhattan distance to nearest OOB border
        self.oob_cells: Set[Tuple[int, int]] = set()  # Nearby OOB border ($80-$9B) tiles

    def calculate_distance_field(self, terrain: List[List[int]]):
        """Calculate Manhattan distance from each placeholder to nearest OOB border using BFS."""
        self._find_nearby_oob_tiles(terrain)

        if not self.oob_cells:
            self._calculate_distance_to_edge(terrain)
            return

        queue = deque()
        visited = set()

        for oob_cell in self.oob_cells:
            queue.append((oob_cell, 0))
            visited.add(oob_cell)

        while queue:
            (row, col), dist = queue.popleft()

            if (row, col) in self.cells:
                self.distance_field[(row, col)] = dist

            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = row + dr, col + dc

                if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                    continue

                if (nr, nc) in visited:
                    continue

                visited.add((nr, nc))
                queue.append(((nr, nc), dist + 1))

    def _find_nearby_oob_tiles(self, terrain: List[List[int]]):
        """Find OOB border tiles near this placeholder region."""
        for row, col in self.cells:
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                nr, nc = row + dr, col + dc

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
            dist_to_edge = min(row, col, height - 1 - row, width - 1 - col)
            self.distance_field[(row, col)] = dist_to_edge + 1


class Decision:
    """Represents a WFC decision that can be backtracked."""
    def __init__(self, cell: Tuple[int, int], chosen_tile: int, alternatives: List[int],
                 superposition_snapshot: Dict[Tuple[int, int], Set[int]],
                 collapsed_snapshot: Dict[Tuple[int, int], int]):
        self.cell = cell
        self.chosen_tile = chosen_tile
        self.alternatives = alternatives
        self.superposition_snapshot = superposition_snapshot
        self.collapsed_snapshot = collapsed_snapshot


class ForestFiller:
    """Intelligent forest fill algorithm using Wave Function Collapse."""

    def __init__(self, neighbor_validator: TerrainNeighborValidator, debug: bool = False):
        self.validator = neighbor_validator
        self.placeholder_tile = PLACEHOLDER_TILE
        self.debug = debug

    def detect_regions(self, terrain: List[List[int]]) -> List[ForestFillRegion]:
        """Find all contiguous regions of placeholder tiles."""
        if not terrain:
            return []

        height = len(terrain)
        width = len(terrain[0]) if height > 0 else 0

        visited = set()
        regions = []

        for row in range(height):
            for col in range(width):
                if (row, col) in visited:
                    continue

                if terrain[row][col] != PLACEHOLDER_TILE:
                    continue

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

            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = row + dr, col + dc

                if nr < 0 or nr >= height or nc < 0 or nc >= width:
                    continue

                if (nr, nc) in visited:
                    continue

                if terrain[nr][nc] != PLACEHOLDER_TILE:
                    continue

                visited.add((nr, nc))
                queue.append((nr, nc))

        return region_cells

    def fill_region(self, terrain: List[List[int]], region: ForestFillRegion,
                    max_backtracks: int = 10_000) -> Dict[Tuple[int, int], int]:
        """Fill a placeholder region using WFC with backtracking.

        Args:
            terrain: The terrain grid
            region: The region to fill
            max_backtracks: Maximum backtrack attempts before relaxation fallback

        Returns:
            Dict mapping (row, col) to tile values for filled cells
        """
        # Initialize superposition for each cell
        superposition: Dict[Tuple[int, int], Set[int]] = {}
        for cell in region.cells:
            superposition[cell] = set(ALL_FOREST_TILES)

        # Initial constraint propagation from existing terrain
        collapsed: Dict[Tuple[int, int], int] = {}
        for cell in region.cells:
            self._propagate_constraints(cell, terrain, region, superposition, collapsed)

        # WFC collapse with backtracking
        cells_to_collapse = set(region.cells)
        decision_stack: List[Decision] = []
        backtrack_count = 0

        while cells_to_collapse:
            # Find cell with minimum entropy
            min_entropy_cell, has_contradiction = self._find_min_entropy_cell_in_set(
                cells_to_collapse, superposition, collapsed
            )

            if min_entropy_cell is None:
                if not has_contradiction:
                    # All remaining cells are collapsed - we're done
                    break

                # Contradiction detected - attempt backtracking
                if not decision_stack or backtrack_count >= max_backtracks:
                    if self.debug:
                        self._log_stuck_cells(cells_to_collapse, superposition, collapsed, terrain)

                    # Relaxation fallback: try to fill remaining cells anyway
                    self._relaxation_pass(cells_to_collapse, superposition, collapsed, terrain, region)
                    break

                # Backtrack
                backtrack_count += 1
                restored = self._backtrack(
                    decision_stack, superposition, collapsed, cells_to_collapse,
                    region, terrain
                )

                if not restored:
                    # Exhausted all alternatives
                    if self.debug:
                        print(f"  Exhausted backtrack stack after {backtrack_count} attempts")
                        self._log_stuck_cells(cells_to_collapse, superposition, collapsed, terrain)
                    self._relaxation_pass(cells_to_collapse, superposition, collapsed, terrain, region)
                    break

                continue

            # Normal collapse
            row, col = min_entropy_cell
            distance = region.distance_field.get(min_entropy_cell, 999)
            use_border = distance <= BORDER_DISTANCE_THRESHOLD
            pattern_phase = self._compute_pattern_phase(row, col, collapsed)

            # Get possibilities and score them
            possibilities = list(superposition.get(min_entropy_cell, set()))

            # Score all possibilities with lookahead
            scored = self._score_possibilities_with_lookahead(
                possibilities, min_entropy_cell, terrain, region,
                superposition, collapsed, distance, pattern_phase, use_border
            )

            if not scored:
                # No valid tiles - will trigger backtracking on next iteration
                superposition[min_entropy_cell] = set()
                continue

            sorted_tiles = [tile for score, tile in scored]
            chosen_tile = sorted_tiles[0]
            alternatives = sorted_tiles[1:] if len(sorted_tiles) > 1 else []

            # Only save decision if we have alternatives (memory efficiency)
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

        if backtrack_count > 0 and self.debug:
            print(f"  Backtracked {backtrack_count} times to resolve contradictions")

        return collapsed

    def _find_min_entropy_cell_in_set(
            self,
            cell_set: Set[Tuple[int, int]],
            superposition: Dict[Tuple[int, int], Set[int]],
            collapsed: Dict[Tuple[int, int], int]
    ) -> Tuple[Optional[Tuple[int, int]], bool]:
        """Find uncollapsed cell with minimum entropy.

        Returns:
            (cell, has_contradiction) tuple:
            - (cell, False) if found a cell with possibilities
            - (None, False) if all cells are collapsed (success)
            - (None, True) if uncollapsed cells exist but all have empty possibility sets
        """
        min_entropy = float('inf')
        min_cell = None
        has_uncollapsed = False
        has_contradiction = False

        for cell in cell_set:
            if cell in collapsed:
                continue

            has_uncollapsed = True
            entropy = len(superposition.get(cell, set()))

            if entropy == 0:
                has_contradiction = True
                continue

            if entropy < min_entropy:
                min_entropy = entropy
                min_cell = cell

        if not has_uncollapsed:
            return None, False  # All done

        if min_cell is None and has_contradiction:
            return None, True  # Stuck

        return min_cell, False

    def _backtrack(
            self,
            decision_stack: List[Decision],
            superposition: Dict[Tuple[int, int], Set[int]],
            collapsed: Dict[Tuple[int, int], int],
            cells_to_collapse: Set[Tuple[int, int]],
            region: ForestFillRegion,
            terrain: List[List[int]]
    ) -> bool:
        """Attempt to backtrack to a previous decision and try an alternative.

        Returns:
            True if successfully restored to a new alternative, False if exhausted.
        """
        while decision_stack:
            last_decision = decision_stack[-1]

            if not last_decision.alternatives:
                decision_stack.pop()
                continue

            # Try next alternative
            next_tile = last_decision.alternatives.pop(0)

            # Restore state from snapshot
            superposition.clear()
            for cell, poss in last_decision.superposition_snapshot.items():
                superposition[cell] = poss.copy()

            collapsed.clear()
            collapsed.update(last_decision.collapsed_snapshot)

            # Recalculate cells_to_collapse
            cells_to_collapse.clear()
            cells_to_collapse.update({cell for cell in region.cells if cell not in collapsed})

            # Apply alternative choice
            collapsed[last_decision.cell] = next_tile
            superposition[last_decision.cell] = {next_tile}
            cells_to_collapse.discard(last_decision.cell)

            # Propagate constraints
            self._propagate_constraints(last_decision.cell, terrain, region, superposition, collapsed)

            # Remove decision from stack if no more alternatives
            if not last_decision.alternatives:
                decision_stack.pop()

            return True

        return False

    def _relaxation_pass(
            self,
            cells_to_collapse: Set[Tuple[int, int]],
            superposition: Dict[Tuple[int, int], Set[int]],
            collapsed: Dict[Tuple[int, int], int],
            terrain: List[List[int]],
            region: ForestFillRegion
    ):
        """Last-resort pass: fill remaining cells with any valid tile, relaxing constraints."""
        remaining = [c for c in cells_to_collapse if c not in collapsed]

        if self.debug and remaining:
            print(f"  Relaxation pass for {len(remaining)} remaining cells")

        for cell in remaining:
            # Try constrained possibilities first
            valid = self._get_constrained_possibilities(cell, terrain, region, superposition, collapsed)

            if valid:
                # Pick the best one by score
                row, col = cell
                distance = region.distance_field.get(cell, 999)
                use_border = distance <= BORDER_DISTANCE_THRESHOLD
                pattern_phase = self._compute_pattern_phase(row, col, collapsed)

                best_tile = self._select_best_tile(valid, distance, pattern_phase, use_border)
                if best_tile is not None:
                    collapsed[cell] = best_tile
                    superposition[cell] = {best_tile}
                    cells_to_collapse.discard(cell)
                    continue

            # Try ALL forest tiles, checking only immediate neighbor validity
            fallback = self._pick_fallback_tile(cell, terrain, collapsed)
            if fallback is not None:
                collapsed[cell] = fallback
                superposition[cell] = {fallback}
                cells_to_collapse.discard(cell)
                if self.debug:
                    print(f"    Used fallback tile ${fallback:02X} for {cell}")
            else:
                if self.debug:
                    print(f"    FAILED to fill {cell} - no valid tile found")

    def _pick_fallback_tile(
            self,
            cell: Tuple[int, int],
            terrain: List[List[int]],
            collapsed: Dict[Tuple[int, int], int]
    ) -> Optional[int]:
        """Pick a fallback tile when normal constraint satisfaction fails.

        Tries all forest tiles and picks one that has at least partial neighbor compatibility.
        """
        row, col = cell
        best_tile = None
        best_score = -1

        for tile in ALL_FOREST_TILES:
            score = 0
            valid_directions = 0

            for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                        ("left", (0, -1)), ("right", (0, 1))]:
                nr, nc = row + dr, col + dc

                if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                    valid_directions += 1  # Edge is always "valid"
                    continue

                neighbor_tile = None
                if (nr, nc) in collapsed:
                    neighbor_tile = collapsed[(nr, nc)]
                elif terrain[nr][nc] != PLACEHOLDER_TILE:
                    neighbor_tile = terrain[nr][nc]

                if neighbor_tile is None:
                    valid_directions += 1  # Uncollapsed placeholder is "valid"
                    continue

                # Check if this tile can have this neighbor
                if tile in self.validator.neighbors:
                    valid_neighbors = self.validator.neighbors[tile].get(direction, set())
                    if neighbor_tile in valid_neighbors:
                        score += 2
                        valid_directions += 1
                    else:
                        # Partial credit if neighbor could theoretically work
                        score += 0
                else:
                    valid_directions += 1

            # Prefer tiles that work with more neighbors
            total_score = score * 10 + valid_directions
            if total_score > best_score:
                best_score = total_score
                best_tile = tile

        return best_tile

    def _log_stuck_cells(
            self,
            cells_to_collapse: Set[Tuple[int, int]],
            superposition: Dict[Tuple[int, int], Set[int]],
            collapsed: Dict[Tuple[int, int], int],
            terrain: List[List[int]]
    ):
        """Log diagnostic information about stuck cells."""
        stuck_cells = [
            c for c in cells_to_collapse
            if c not in collapsed and len(superposition.get(c, set())) == 0
        ]

        if not stuck_cells:
            return

        print(f"  Stuck cells ({len(stuck_cells)}):")
        for cell in stuck_cells[:10]:  # Limit output
            neighbors = self._get_neighbor_info(cell, terrain, collapsed)
            print(f"    {cell}: neighbors={neighbors}")

    def _get_neighbor_info(
            self,
            cell: Tuple[int, int],
            terrain: List[List[int]],
            collapsed: Dict[Tuple[int, int], int]
    ) -> Dict[str, str]:
        """Get info about a cell's neighbors for debugging."""
        row, col = cell
        info = {}

        for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                    ("left", (0, -1)), ("right", (0, 1))]:
            nr, nc = row + dr, col + dc

            if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                info[direction] = "edge"
                continue

            if (nr, nc) in collapsed:
                info[direction] = f"${collapsed[(nr, nc)]:02X}"
            elif terrain[nr][nc] != PLACEHOLDER_TILE:
                info[direction] = f"${terrain[nr][nc]:02X}"
            else:
                info[direction] = "placeholder"

        return info

    def _compute_pattern_phase(
            self,
            row: int,
            col: int,
            collapsed: Dict[Tuple[int, int], int]
    ) -> int:
        """Compute pattern phase based on existing fill tiles in this row.

        This is stateless - survives backtracking correctly by recomputing
        from the current state of collapsed tiles.
        """
        # Find leftmost fill tile in this row
        leftmost_fill_col = None
        leftmost_fill_tile = None

        for (r, c), tile in collapsed.items():
            if r == row and tile in FOREST_FILL:
                if leftmost_fill_col is None or c < leftmost_fill_col:
                    leftmost_fill_col = c
                    leftmost_fill_tile = tile

        if leftmost_fill_col is None:
            # No fill tiles yet in this row - this cell becomes the anchor
            # Use row parity to maintain vertical tiling pattern
            # Pattern is: [[$A2, $A3, $A0, $A1], [$A0, $A1, $A2, $A3]]
            # Even rows start with $A2 (phase 2), odd rows start with $A0 (phase 0)
            base_phase = 2 if (row % 2 == 0) else 0
            return (base_phase + col) % 4

        # Compute phase relative to leftmost fill tile
        # The leftmost fill tile's phase is determined by its value
        leftmost_phase = leftmost_fill_tile - 0xA0
        return (leftmost_phase + (col - leftmost_fill_col)) % 4

    def _score_possibilities_with_lookahead(
            self,
            possibilities: List[int],
            cell: Tuple[int, int],
            terrain: List[List[int]],
            region: ForestFillRegion,
            superposition: Dict[Tuple[int, int], Set[int]],
            collapsed: Dict[Tuple[int, int], int],
            distance: int,
            pattern_phase: int,
            use_border: bool
    ) -> List[Tuple[float, int]]:
        """Score all possibilities with lookahead to detect contradictions."""
        tile_scores = []

        for tile in possibilities:
            # Base score from pattern/category matching
            base_score = self._score_tile_with_context(
                tile, cell, terrain, collapsed, distance, pattern_phase, use_border
            )

            # Lookahead: test if this tile would create contradictions
            test_superposition = {c: p.copy() for c, p in superposition.items()}
            test_collapsed = collapsed.copy()

            test_collapsed[cell] = tile
            test_superposition[cell] = {tile}

            self._propagate_constraints(cell, terrain, region, test_superposition, test_collapsed)

            # Count contradictions
            contradictions = sum(
                1 for c in region.cells
                if c not in test_collapsed and len(test_superposition.get(c, set())) == 0
            )

            # Count total remaining entropy (lower is more constrained, could be risky)
            total_entropy = sum(
                len(test_superposition.get(c, set()))
                for c in region.cells
                if c not in test_collapsed
            )

            # Combined score: heavily penalize contradictions
            combined_score = (
                -contradictions * 10000 +  # Massive penalty for contradictions
                base_score +               # Positive for good pattern match
                total_entropy * 0.1        # Slight preference for less constrained states
            )

            tile_scores.append((combined_score, tile))

        tile_scores.sort(reverse=True)
        return tile_scores

    def _propagate_constraints(
            self,
            cell: Tuple[int, int],
            terrain: List[List[int]],
            region: ForestFillRegion,
            superposition: Dict[Tuple[int, int], Set[int]],
            collapsed: Dict[Tuple[int, int], int]
    ):
        """Propagate constraints from a cell to its neighbors."""
        queue = deque([cell])
        processed = set()

        while queue:
            current = queue.popleft()

            if current in processed:
                continue
            processed.add(current)

            row, col = current

            for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                        ("left", (0, -1)), ("right", (0, 1))]:
                nr, nc = row + dr, col + dc
                neighbor_cell = (nr, nc)

                if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                    continue

                if neighbor_cell not in region.cells:
                    continue

                if neighbor_cell in collapsed:
                    continue

                old_possibilities = superposition.get(neighbor_cell, set()).copy()
                new_possibilities = self._get_constrained_possibilities(
                    neighbor_cell, terrain, region, superposition, collapsed
                )

                superposition[neighbor_cell] = new_possibilities

                if new_possibilities != old_possibilities and neighbor_cell not in processed:
                    queue.append(neighbor_cell)

    def _get_constrained_possibilities(
            self,
            cell: Tuple[int, int],
            terrain: List[List[int]],
            region: ForestFillRegion,
            superposition: Dict[Tuple[int, int], Set[int]],
            collapsed: Dict[Tuple[int, int], int]
    ) -> Set[int]:
        """Get valid tile possibilities for a cell based on current constraints."""
        row, col = cell
        current_possibilities = superposition.get(cell, set(ALL_FOREST_TILES)).copy()

        for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                    ("left", (0, -1)), ("right", (0, 1))]:
            nr, nc = row + dr, col + dc

            if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                continue

            neighbor_cell = (nr, nc)
            if neighbor_cell in collapsed:
                neighbor_tile = collapsed[neighbor_cell]
            elif terrain[nr][nc] != PLACEHOLDER_TILE:
                neighbor_tile = terrain[nr][nc]
            else:
                continue

            valid_for_this_neighbor = set()
            for candidate in current_possibilities:
                if candidate not in self.validator.neighbors:
                    continue

                valid_neighbors = self.validator.neighbors[candidate].get(direction, set())
                if neighbor_tile in valid_neighbors:
                    valid_for_this_neighbor.add(candidate)

            current_possibilities &= valid_for_this_neighbor

        return current_possibilities

    def _select_best_tile(
            self,
            valid_tiles: Set[int],
            distance: int,
            pattern_phase: int,
            use_border: bool
    ) -> Optional[int]:
        """Select best tile from valid candidates based on scoring."""
        if not valid_tiles:
            return None

        scored = []
        for tile in valid_tiles:
            score = self._score_tile(tile, distance, pattern_phase, use_border)
            scored.append((score, tile))

        scored.sort(reverse=True)
        return scored[0][1]

    def _score_tile(self, tile: int, distance: int, pattern_phase: int, use_border: bool) -> int:
        """Score a candidate tile based on category and pattern match."""
        score = 0

        is_border = tile in FOREST_BORDER
        is_fill = tile in FOREST_FILL

        if use_border and is_border:
            score += 100
        elif not use_border and is_fill:
            score += 100

        if is_fill:
            expected_tile = 0xA0 + pattern_phase
            if tile == expected_tile:
                score += 50

        return score

    def _score_tile_with_context(
            self,
            tile: int,
            cell: Tuple[int, int],
            terrain: List[List[int]],
            collapsed: Dict[Tuple[int, int], int],
            distance: int,
            pattern_phase: int,
            use_border: bool
    ) -> float:
        """Score a tile considering both intrinsic properties and neighbor context."""
        base_score = self._score_tile(tile, distance, pattern_phase, use_border)

        frequency_score = 0.0
        row, col = cell
        neighbor_count = 0

        for direction, (dr, dc) in [("up", (-1, 0)), ("down", (1, 0)),
                                    ("left", (0, -1)), ("right", (0, 1))]:
            nr, nc = row + dr, col + dc

            if nr < 0 or nr >= len(terrain) or nc < 0 or nc >= len(terrain[0]):
                continue

            neighbor_tile = None
            if (nr, nc) in collapsed:
                neighbor_tile = collapsed[(nr, nc)]
            elif terrain[nr][nc] != self.placeholder_tile:
                neighbor_tile = terrain[nr][nc]

            if neighbor_tile is not None:
                freq = self.validator.get_neighbor_frequency(tile, neighbor_tile, direction)
                if freq > 0:
                    frequency_score += 50 * math.log2(1 + freq)
                    neighbor_count += 1

                    is_tile_fill = tile in FOREST_FILL
                    is_neighbor_fill = neighbor_tile in FOREST_FILL
                    if is_tile_fill and is_neighbor_fill:
                        frequency_score += 30

        if neighbor_count > 0:
            frequency_score = frequency_score / neighbor_count

        return base_score + frequency_score

    @staticmethod
    def is_placeholder(tile_value: int) -> bool:
        """Check if tile is the placeholder that should be replaced."""
        return tile_value == PLACEHOLDER_TILE