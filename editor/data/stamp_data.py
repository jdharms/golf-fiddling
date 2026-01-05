"""
NES Open Tournament Golf - Stamp Data

Manages stamp data with JSON serialization for persistent pattern library.
"""

from datetime import datetime
from pathlib import Path

from golf.formats import compact_json as json
from golf.formats import hex_utils

from .clipboard_data import ClipboardData


class StampMetadata:
    """Metadata for a stamp."""

    def __init__(
        self,
        stamp_id: str | None = None,
        name: str = "",
        description: str = "",
        category: str = "user",
        tags: list[str] | None = None,
    ):
        # Auto-generate ID if not provided
        if stamp_id is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stamp_id = f"stamp_{timestamp}"

        self.id = stamp_id
        self.name = name
        self.description = description
        self.created = datetime.now().isoformat()
        self.category = category
        self.tags = tags if tags is not None else []

    def to_dict(self) -> dict:
        """Convert metadata to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created": self.created,
            "category": self.category,
            "tags": self.tags,
        }

    @staticmethod
    def from_dict(data: dict) -> "StampMetadata":
        """Create metadata from dictionary."""
        metadata = StampMetadata(
            stamp_id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", "user"),
            tags=data.get("tags", []),
        )
        metadata.created = data.get("created", metadata.created)
        return metadata


class StampData:
    """A reusable tile pattern with transparency support."""

    def __init__(self):
        self.tiles: list[list[int | None]] = []  # None = transparent
        self.attributes: list[list[int]] | None = None
        self.width: int = 0
        self.height: int = 0
        self.mode: str = "terrain"  # "terrain" or "greens"
        self.metadata: StampMetadata = StampMetadata()

    @staticmethod
    def from_clipboard(
        clipboard: ClipboardData, metadata: StampMetadata | None = None
    ) -> "StampData":
        """Create stamp from clipboard data."""
        stamp = StampData()
        stamp.tiles = [row.copy() for row in clipboard.tiles]  # Deep copy
        stamp.attributes = (
            [row.copy() for row in clipboard.attributes]
            if clipboard.attributes
            else None
        )
        stamp.width = clipboard.width
        stamp.height = clipboard.height
        stamp.mode = clipboard.mode
        stamp.metadata = metadata if metadata is not None else StampMetadata()
        return stamp

    def save(self, path: str | Path):
        """
        Save stamp to JSON file using hex_utils format.

        Args:
            path: File path to save to (can be string or Path)
        """
        path = Path(path)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert tiles to hex strings using shared utility
        tile_rows = []
        for row in self.tiles:
            # Convert None values to "--" marker for transparency
            hex_values = []
            for tile_value in row:
                if tile_value is None:
                    hex_values.append("--")
                else:
                    hex_values.append(f"{tile_value:02X}")
            tile_rows.append(" ".join(hex_values))

        # Build data dictionary
        data = {
            **self.metadata.to_dict(),  # Spread metadata fields
            "mode": self.mode,
            "width": self.width,
            "height": self.height,
            "tiles": {"rows": tile_rows},
        }

        # Include attributes if present (terrain mode)
        if self.attributes:
            data["attributes"] = {"rows": self.attributes}

        # Save to JSON
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load(path: str | Path) -> "StampData":
        """
        Load stamp from JSON file.

        Args:
            path: File path to load from (can be string or Path)

        Returns:
            Loaded StampData instance
        """
        path = Path(path)

        with open(path) as f:
            data = json.load(f)

        stamp = StampData()

        # Load metadata
        stamp.metadata = StampMetadata.from_dict(data)

        # Load dimensions and mode
        stamp.mode = data.get("mode", "terrain")
        stamp.width = data.get("width", 0)
        stamp.height = data.get("height", 0)

        # Parse tiles using shared hex utility (with transparency support)
        stamp.tiles = []
        for row_str in data["tiles"]["rows"]:
            # Split by whitespace and convert hex values
            hex_values = row_str.split()
            row_data = []
            for hex_val in hex_values:
                if hex_val == "--":
                    # Transparent tile marker
                    row_data.append(None)
                else:
                    # Regular tile value
                    try:
                        row_data.append(int(hex_val, 16))
                    except ValueError:
                        # Invalid hex value, treat as transparent
                        row_data.append(None)
            stamp.tiles.append(row_data)

        # Parse attributes if present
        if "attributes" in data and data["attributes"]:
            stamp.attributes = data["attributes"]["rows"]
        else:
            stamp.attributes = None

        return stamp

    def get_tile(self, row: int, col: int) -> int | None:
        """Get tile value at stamp position (0-indexed)."""
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.tiles[row][col]
        return None

    def is_transparent(self, row: int, col: int) -> bool:
        """Check if tile at position is transparent."""
        tile_value = self.get_tile(row, col)
        return tile_value is None

    def get_display_name(self) -> str:
        """Get display name for UI (name if present, else ID)."""
        if self.metadata.name:
            return self.metadata.name
        return self.metadata.id
