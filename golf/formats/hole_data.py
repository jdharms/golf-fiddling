"""
NES Open Tournament Golf - Hole Data Model

Manages hole data including terrain, attributes, greens, and metadata.
Handles loading from and saving to JSON files.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from . import compact_json as json
from . import hex_utils
from ..core.palettes import TERRAIN_WIDTH, GREENS_WIDTH


class HoleData:
    """Manages hole data including terrain, attributes, and greens."""

    def __init__(self):
        self.terrain: List[List[int]] = []
        self.attributes: List[List[int]] = []
        self.greens: List[List[int]] = []
        self.green_x: int = 0
        self.green_y: int = 0
        self.metadata: Dict[str, Any] = {}
        self.filepath: Optional[str] = None
        self.modified: bool = False

    def load(self, path: str):
        """Load hole data from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)

        # Parse terrain using shared hex utility
        self.terrain = []
        for row_str in data["terrain"]["rows"]:
            row = hex_utils.parse_hex_row(row_str)
            self.terrain.append(row)

        # Parse attributes
        self.attributes = data["attributes"]["rows"]

        # Parse greens using shared hex utility
        self.greens = []
        for row_str in data["greens"]["rows"]:
            row = hex_utils.parse_hex_row(row_str)
            self.greens.append(row)

        # Green position
        self.green_x = data["green"]["x"]
        self.green_y = data["green"]["y"]

        # Store other metadata
        self.metadata = {
            "hole": data.get("hole", 1),
            "par": data.get("par", 4),
            "distance": data.get("distance", 400),
            "handicap": data.get("handicap", 1),
            "scroll_limit": data.get("scroll_limit", 32),
            "tee": data.get("tee", {"x": 0, "y": 0}),
            "flag_positions": data.get("flag_positions", []),
            "_debug": data.get("_debug", {}),
        }

        self.filepath = path
        self.modified = False

    def save(self, path: Optional[str] = None):
        """Save hole data to JSON file."""
        if path is None:
            path = self.filepath
        if path is None:
            raise ValueError("No save path specified")

        # Convert terrain to hex strings using shared utility
        terrain_rows = []
        for row in self.terrain:
            row_str = hex_utils.format_hex_row(row)
            terrain_rows.append(row_str)

        # Convert greens to hex strings using shared utility
        greens_rows = []
        for row in self.greens:
            row_str = hex_utils.format_hex_row(row)
            greens_rows.append(row_str)

        data = {
            "hole": self.metadata.get("hole", 1),
            "par": self.metadata.get("par", 4),
            "distance": self.metadata.get("distance", 400),
            "handicap": self.metadata.get("handicap", 1),
            "scroll_limit": self.metadata.get("scroll_limit", 32),
            "green": {"x": self.green_x, "y": self.green_y},
            "tee": self.metadata.get("tee", {"x": 0, "y": 0}),
            "flag_positions": self.metadata.get("flag_positions", []),
            "terrain": {
                "width": TERRAIN_WIDTH,
                "height": len(self.terrain),
                "rows": terrain_rows,
            },
            "attributes": {
                "width": len(self.attributes[0]) if self.attributes else 11,
                "height": len(self.attributes),
                "rows": self.attributes,
            },
            "greens": {
                "width": GREENS_WIDTH,
                "height": len(self.greens),
                "rows": greens_rows,
            },
            "_debug": self.metadata.get("_debug", {}),
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

        self.filepath = path
        self.modified = False

    def get_terrain_height(self) -> int:
        return len(self.terrain)

    def get_attribute(self, tile_row: int, tile_col: int) -> int:
        """Get palette index for a terrain tile position."""
        attr_row = tile_row // 2
        attr_col = tile_col // 2
        if 0 <= attr_row < len(self.attributes) and 0 <= attr_col < len(self.attributes[attr_row]):
            return self.attributes[attr_row][attr_col]
        return 1

    def set_attribute(self, super_row: int, super_col: int, palette: int):
        """Set palette index for a supertile position."""
        if 0 <= super_row < len(self.attributes) and 0 <= super_col < len(self.attributes[super_row]):
            self.attributes[super_row][super_col] = palette
            self.modified = True

    def set_terrain_tile(self, row: int, col: int, tile_idx: int):
        """Set a terrain tile."""
        if 0 <= row < len(self.terrain) and 0 <= col < len(self.terrain[row]):
            self.terrain[row][col] = tile_idx
            self.modified = True

    def set_greens_tile(self, row: int, col: int, tile_idx: int):
        """Set a greens tile."""
        if 0 <= row < len(self.greens) and 0 <= col < len(self.greens[row]):
            self.greens[row][col] = tile_idx
            self.modified = True

    def add_terrain_row(self, at_top: bool = False):
        """Add a row of default terrain."""
        new_row = [0xDF] * TERRAIN_WIDTH  # Default to deep rough
        if at_top:
            self.terrain.insert(0, new_row)
        else:
            self.terrain.append(new_row)

        # Add attribute row if needed
        if len(self.terrain) // 2 > len(self.attributes):
            new_attr_row = [1] * 11  # Default to fairway palette
            if at_top:
                self.attributes.insert(0, new_attr_row)
            else:
                self.attributes.append(new_attr_row)

        self.modified = True

    def remove_terrain_row(self, from_top: bool = False):
        """Remove a row of terrain."""
        if len(self.terrain) <= 1:
            return

        if from_top:
            self.terrain.pop(0)
        else:
            self.terrain.pop()

        # Remove attribute row if needed
        expected_attr_rows = (len(self.terrain) + 1) // 2
        while len(self.attributes) > expected_attr_rows:
            if from_top:
                self.attributes.pop(0)
            else:
                self.attributes.pop()

        self.modified = True
