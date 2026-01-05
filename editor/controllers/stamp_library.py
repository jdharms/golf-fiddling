"""
NES Open Tournament Golf - Stamp Library

Manages loading and saving of stamp patterns from built-in and user directories.
"""

from pathlib import Path

from editor.data import StampData


class StampLibrary:
    """Manages stamp library with built-in and user stamps."""

    def __init__(self):
        """Initialize stamp library."""
        self.stamps: dict[str, StampData] = {}  # stamp_id -> StampData
        self.categories: dict[str, list[str]] = {}  # category -> list of stamp_ids

        # Paths
        self.built_in_path = Path("data/stamps/built-in")
        self.user_path = Path.home() / ".config" / "golf-editor" / "stamps"

        # Ensure user directory exists
        self.user_path.mkdir(parents=True, exist_ok=True)

    def load_stamps(self):
        """Load all stamps from built-in and user directories."""
        self.stamps.clear()
        self.categories.clear()

        # Load built-in stamps
        if self.built_in_path.exists():
            self._load_stamps_from_directory(self.built_in_path, is_built_in=True)

        # Load user stamps
        if self.user_path.exists():
            self._load_stamps_from_directory(self.user_path, is_built_in=False)

    def _load_stamps_from_directory(self, directory: Path, is_built_in: bool):
        """
        Recursively load stamps from a directory.

        Args:
            directory: Directory to scan
            is_built_in: Whether these are built-in stamps
        """
        # Scan for JSON files recursively
        for json_file in directory.rglob("*.json"):
            # Skip index.json files
            if json_file.name == "index.json":
                continue

            try:
                stamp = StampData.load(json_file)
                stamp_id = stamp.metadata.id

                # Store stamp
                self.stamps[stamp_id] = stamp

                # Categorize stamp
                category = stamp.metadata.category
                if category not in self.categories:
                    self.categories[category] = []
                self.categories[category].append(stamp_id)

            except Exception as e:
                print(f"Warning: Failed to load stamp {json_file}: {e}")

    def get_stamps_by_category(self, category: str) -> list[StampData]:
        """
        Get all stamps in a category.

        Args:
            category: Category name

        Returns:
            List of StampData objects in the category
        """
        stamp_ids = self.categories.get(category, [])
        return [self.stamps[stamp_id] for stamp_id in stamp_ids if stamp_id in self.stamps]

    def get_all_categories(self) -> list[str]:
        """Get list of all categories."""
        return sorted(self.categories.keys())

    def get_stamp(self, stamp_id: str) -> StampData | None:
        """
        Get stamp by ID.

        Args:
            stamp_id: Stamp ID

        Returns:
            StampData or None if not found
        """
        return self.stamps.get(stamp_id)

    def save_stamp(self, stamp: StampData, category: str | None = None) -> Path:
        """
        Save stamp to user directory.

        Args:
            stamp: StampData to save
            category: Optional category subdirectory (uses stamp.metadata.category if None)

        Returns:
            Path where stamp was saved
        """
        # Use stamp's category if not specified
        if category is None:
            category = stamp.metadata.category

        # Create category subdirectory
        category_path = self.user_path / category
        category_path.mkdir(parents=True, exist_ok=True)

        # Generate filename from name or ID
        if stamp.metadata.name:
            # Use name if available (sanitize for filesystem)
            filename = self._sanitize_filename(stamp.metadata.name) + ".json"
        else:
            # Use ID
            filename = f"{stamp.metadata.id}.json"

        save_path = category_path / filename

        # Save stamp
        stamp.save(save_path)

        # Add to library
        self.stamps[stamp.metadata.id] = stamp
        if category not in self.categories:
            self.categories[category] = []
        if stamp.metadata.id not in self.categories[category]:
            self.categories[category].append(stamp.metadata.id)

        return save_path

    def delete_stamp(self, stamp_id: str) -> bool:
        """
        Delete stamp from user directory (can't delete built-in stamps).

        Args:
            stamp_id: Stamp ID to delete

        Returns:
            True if deleted, False if not found or is built-in
        """
        stamp = self.stamps.get(stamp_id)
        if not stamp:
            return False

        # Check if stamp is in user directory
        # (We don't allow deleting built-in stamps)
        for json_file in self.user_path.rglob("*.json"):
            try:
                test_stamp = StampData.load(json_file)
                if test_stamp.metadata.id == stamp_id:
                    # Found it, delete file
                    json_file.unlink()

                    # Remove from library
                    del self.stamps[stamp_id]
                    for category_stamps in self.categories.values():
                        if stamp_id in category_stamps:
                            category_stamps.remove(stamp_id)

                    return True
            except Exception:
                continue

        return False

    def get_stamp_count(self) -> int:
        """Get total number of stamps in library."""
        return len(self.stamps)

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        Sanitize stamp name for use as filename.

        Args:
            name: Stamp name

        Returns:
            Sanitized filename (without extension)
        """
        # Replace spaces with underscores
        name = name.replace(" ", "_")

        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "")

        # Limit length
        if len(name) > 50:
            name = name[:50]

        # Lowercase
        name = name.lower()

        return name or "unnamed_stamp"
