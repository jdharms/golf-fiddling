"""
Terrain Tile Neighbor Validator

Validates terrain tile neighbor relationships based on patterns observed
in the original course data.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, List


class TerrainNeighborValidator:
    """
    Validates terrain tile neighbor relationships against a learned set of valid neighbors.

    This allows the editor to highlight tiles that have invalid neighbor combinations,
    helping catch common mistakes where multi-tile sprites aren't properly aligned.
    """

    def __init__(self, neighbors_path: Optional[str] = None):
        """
        Load neighbor data from JSON file.

        Args:
            neighbors_path: Path to terrain_neighbors.json. If None, uses default location.

        Raises:
            FileNotFoundError: If neighbors file cannot be found.
            json.JSONDecodeError: If neighbors file is invalid JSON.
        """
        if neighbors_path is None:
            # Default location: data/tables/terrain_neighbors.json
            neighbors_path = (
                Path(__file__).parent.parent.parent / "data" / "tables" / "terrain_neighbors.json"
            )
        else:
            neighbors_path = Path(neighbors_path)

        if not neighbors_path.exists():
            raise FileNotFoundError(f"Neighbor data file not found: {neighbors_path}")

        with open(neighbors_path, "r") as f:
            data = json.load(f)

        # Convert hex string keys to integers for fast lookup
        self.neighbors: Dict[int, Dict[str, Set[int]]] = {}
        self.neighbor_frequencies: Dict[int, Dict[str, Dict[int, int]]] = {}
        for tile_hex, directions in data["neighbors"].items():
            tile_idx = int(tile_hex, 16)

            # Auto-detect format (old: arrays, new: objects with counts)
            if isinstance(directions.get("up", []), list):
                # Old format: arrays
                self.neighbors[tile_idx] = {
                    "up": set(int(n, 16) for n in directions.get("up", [])),
                    "down": set(int(n, 16) for n in directions.get("down", [])),
                    "left": set(int(n, 16) for n in directions.get("left", [])),
                    "right": set(int(n, 16) for n in directions.get("right", [])),
                }
                self.neighbor_frequencies[tile_idx] = {
                    "up": {}, "down": {}, "left": {}, "right": {}
                }
            else:
                # New format: objects with counts
                self.neighbors[tile_idx] = {
                    "up": set(int(n, 16) for n in directions.get("up", {}).keys()),
                    "down": set(int(n, 16) for n in directions.get("down", {}).keys()),
                    "left": set(int(n, 16) for n in directions.get("left", {}).keys()),
                    "right": set(int(n, 16) for n in directions.get("right", {}).keys()),
                }
                self.neighbor_frequencies[tile_idx] = {
                    "up": {int(n, 16): count for n, count in directions.get("up", {}).items()},
                    "down": {int(n, 16): count for n, count in directions.get("down", {}).items()},
                    "left": {int(n, 16): count for n, count in directions.get("left", {}).items()},
                    "right": {int(n, 16): count for n, count in directions.get("right", {}).items()},
                }

    def is_valid_neighbor(self, tile: int, neighbor: int, direction: str) -> bool:
        """
        Check if a neighbor tile is valid for a given tile in a given direction.

        Args:
            tile: The tile index to check
            neighbor: The neighbor tile index
            direction: One of "up", "down", "left", "right"

        Returns:
            True if the neighbor relationship is valid or the tile is unknown.
            False if the relationship is explicitly invalid.
        """
        # If tile not in our data, treat as valid (permissive for experimentation)
        if tile not in self.neighbors:
            return True

        # Check if neighbor exists in valid set for this direction
        return neighbor in self.neighbors[tile][direction]

    def get_neighbor_frequency(self, tile: int, neighbor: int, direction: str) -> int:
        """
        Get occurrence frequency of a neighbor relationship.

        Args:
            tile: The tile index
            neighbor: The neighbor tile index
            direction: One of "up", "down", "left", "right"

        Returns:
            Occurrence count, or 0 if relationship not observed
        """
        if tile not in self.neighbor_frequencies:
            return 0
        return self.neighbor_frequencies[tile][direction].get(neighbor, 0)

    def get_invalid_tiles(self, terrain: List[List[int]]) -> Set[Tuple[int, int]]:
        """
        Find all tiles with invalid neighbors in the given terrain.

        Args:
            terrain: 2D list of terrain tile indices (rows of columns)

        Returns:
            Set of (row, col) tuples for tiles with invalid neighbors
        """
        invalid = set()

        if not terrain:
            return invalid

        height = len(terrain)
        width = len(terrain[0]) if terrain else 0

        for row in range(height):
            for col in range(width):
                tile = terrain[row][col]

                # Check up neighbor
                if row > 0:
                    neighbor = terrain[row - 1][col]
                    if not self.is_valid_neighbor(tile, neighbor, "up"):
                        invalid.add((row, col))
                        continue

                # Check down neighbor
                if row < height - 1:
                    neighbor = terrain[row + 1][col]
                    if not self.is_valid_neighbor(tile, neighbor, "down"):
                        invalid.add((row, col))
                        continue

                # Check left neighbor
                if col > 0:
                    neighbor = terrain[row][col - 1]
                    if not self.is_valid_neighbor(tile, neighbor, "left"):
                        invalid.add((row, col))
                        continue

                # Check right neighbor
                if col < width - 1:
                    neighbor = terrain[row][col + 1]
                    if not self.is_valid_neighbor(tile, neighbor, "right"):
                        invalid.add((row, col))
                        continue

        return invalid
