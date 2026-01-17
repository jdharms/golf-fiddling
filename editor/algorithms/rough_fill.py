"""
NES Open Tournament Golf - Rough Fill Algorithm

Fills tiles outside the greens fringe with appropriate rough tiles
based on parity and adjacency rules.
"""

from collections import deque


class RoughFill:
    """
    Fills rough tiles in a 24x24 greens grid.

    Algorithm:
        1. Find active set via BFS from (0,0) - all placeholder tiles
           connected to the exterior
        2. Calculate parity for each tile: (col + row) % 2
        3. Apply adjacency rules for tiles adjacent to fringe edges
        4. Fill remaining active tiles with base rough (checkerboard)
    """

    # Placeholder value for tiles to be filled
    PLACEHOLDER = 0x100

    # Fringe edge tiles - these indicate which direction the rough goes
    FRINGE_LEFT = 0x66    # rough goes to LEFT of this tile
    FRINGE_UP = 0x64      # rough goes ABOVE this tile
    FRINGE_RIGHT = 0x67   # rough goes to RIGHT of this tile
    FRINGE_DOWN = 0x65    # rough goes BELOW this tile

    # Edge rough tiles (even parity, odd parity)
    EDGE_LEFT = (0x70, 0x84)    # used LEFT of FRINGE_LEFT
    EDGE_UP = (0x71, 0x85)      # used ABOVE FRINGE_UP
    EDGE_RIGHT = (0x73, 0x87)   # used RIGHT of FRINGE_RIGHT
    EDGE_DOWN = (0x72, 0x86)    # used BELOW FRINGE_DOWN

    # Base rough tiles (even parity, odd parity)
    BASE_ROUGH = (0x29, 0x2C)   # checkerboard pattern

    # All rough tiles (for detection/replacement)
    ROUGH_TILES = frozenset([
        0x29, 0x2C,           # base rough
        0x70, 0x71, 0x72, 0x73,  # edge rough (even)
        0x84, 0x85, 0x86, 0x87,  # edge rough (odd)
    ])

    def fill(self, greens: list[list[int]]) -> list[list[int]]:
        """
        Fill rough tiles in a 24x24 greens grid.

        Args:
            greens: 24x24 grid of tile values. Tiles with value PLACEHOLDER
                    (0x100) will be filled with appropriate rough tiles.

        Returns:
            Modified copy of greens with placeholders replaced by rough tiles.
        """
        # Make a deep copy to avoid modifying the input
        result = [row[:] for row in greens]
        height = len(result)
        width = len(result[0]) if height > 0 else 0

        # Step 1: Find active set via BFS from (0,0)
        active_set = self._find_active_set(result, width, height)

        # Step 2 & 3: Apply adjacency rules, then fill remaining
        for row, col in active_set:
            parity = self._get_parity(row, col)
            tile = self._determine_tile(result, row, col, parity, width, height)
            result[row][col] = tile

        return result

    def _find_active_set(
        self,
        greens: list[list[int]],
        width: int,
        height: int
    ) -> set[tuple[int, int]]:
        """
        Find all placeholder tiles connected to (0,0) via BFS.

        This identifies the "exterior" placeholder tiles that should be
        filled with rough. Interior placeholders (e.g., inside a sand trap
        or water hazard boundary) are not included.

        Args:
            greens: The greens grid
            width: Grid width
            height: Grid height

        Returns:
            Set of (row, col) positions that are placeholders connected
            to the exterior.
        """
        if width == 0 or height == 0:
            return set()

        # Start position must be a placeholder
        if greens[0][0] != self.PLACEHOLDER:
            return set()

        active = set()
        visited = set()
        queue = deque([(0, 0)])
        visited.add((0, 0))

        while queue:
            row, col = queue.popleft()

            # Only add placeholders to active set
            if greens[row][col] == self.PLACEHOLDER:
                active.add((row, col))

                # Explore neighbors (only through placeholders)
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = row + dr, col + dc
                    if 0 <= nr < height and 0 <= nc < width:
                        if (nr, nc) not in visited:
                            visited.add((nr, nc))
                            # Only queue if it's a placeholder (continue BFS through placeholders only)
                            if greens[nr][nc] == self.PLACEHOLDER:
                                queue.append((nr, nc))

        return active

    def _get_parity(self, row: int, col: int) -> int:
        """
        Calculate parity for a tile position.

        Args:
            row: Row index
            col: Column index

        Returns:
            0 for even parity, 1 for odd parity
        """
        return (col + row) % 2

    def _determine_tile(
        self,
        greens: list[list[int]],
        row: int,
        col: int,
        parity: int,
        width: int,
        height: int
    ) -> int:
        """
        Determine the appropriate rough tile for a position.

        Checks adjacency rules in priority order:
        1. LEFT of FRINGE_LEFT (0x66) -> EDGE_LEFT
        2. ABOVE FRINGE_UP (0x64) -> EDGE_UP
        3. RIGHT of FRINGE_RIGHT (0x67) -> EDGE_RIGHT
        4. BELOW FRINGE_DOWN (0x65) -> EDGE_DOWN
        5. Otherwise -> BASE_ROUGH

        Args:
            greens: The greens grid
            row: Current row
            col: Current column
            parity: Parity value (0 or 1)
            width: Grid width
            height: Grid height

        Returns:
            The tile value to use at this position.
        """
        # Check RIGHT neighbor - if it's FRINGE_LEFT, we're LEFT of it
        if col + 1 < width and greens[row][col + 1] == self.FRINGE_LEFT:
            return self.EDGE_LEFT[parity]

        # Check BELOW neighbor - if it's FRINGE_UP, we're ABOVE it
        if row + 1 < height and greens[row + 1][col] == self.FRINGE_UP:
            return self.EDGE_UP[parity]

        # Check LEFT neighbor - if it's FRINGE_RIGHT, we're RIGHT of it
        if col - 1 >= 0 and greens[row][col - 1] == self.FRINGE_RIGHT:
            return self.EDGE_RIGHT[parity]

        # Check ABOVE neighbor - if it's FRINGE_DOWN, we're BELOW it
        if row - 1 >= 0 and greens[row - 1][col] == self.FRINGE_DOWN:
            return self.EDGE_DOWN[parity]

        # Default: base rough with checkerboard pattern
        return self.BASE_ROUGH[parity]
