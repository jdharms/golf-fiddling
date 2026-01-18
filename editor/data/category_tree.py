"""Category tree structure for hierarchical stamp organization."""

from dataclasses import dataclass, field


@dataclass
class CategoryNode:
    """Node in category tree."""

    name: str  # Display name (e.g., "water")
    path: str  # Full path (e.g., "terrain/water")
    children: dict[str, "CategoryNode"] = field(default_factory=dict)
    stamp_ids: list[str] = field(default_factory=list)  # Stamps directly in this category
    is_expanded: bool = False  # UI state: is folder expanded?

    def get_all_stamp_ids(self) -> list[str]:
        """Get all stamp IDs in this category and all subcategories (recursive)."""
        all_ids = self.stamp_ids.copy()
        for child in self.children.values():
            all_ids.extend(child.get_all_stamp_ids())
        return all_ids

    def get_depth(self) -> int:
        """Get depth of this node (0 = root)."""
        return self.path.count("/")


class CategoryTree:
    """Hierarchical category tree for stamps."""

    def __init__(self):
        self.root: dict[str, CategoryNode] = {}  # Top-level categories

    def clear(self):
        """Clear all categories."""
        self.root.clear()

    def add_stamp(self, category_path: str, stamp_id: str):
        """
        Add stamp to category tree.

        Args:
            category_path: Category path (e.g., "terrain/water/shallow")
            stamp_id: Stamp ID to add
        """
        if not category_path:
            return

        parts = category_path.split("/")
        current_dict = self.root
        current_path_parts = []

        for part in parts:
            current_path_parts.append(part)
            current_path = "/".join(current_path_parts)

            if part not in current_dict:
                # Create new node
                current_dict[part] = CategoryNode(name=part, path=current_path)

            node = current_dict[part]
            current_dict = node.children

        # Add stamp to leaf node
        node.stamp_ids.append(stamp_id)

    def get_node(self, category_path: str) -> CategoryNode | None:
        """Get category node by path."""
        if not category_path:
            return None

        parts = category_path.split("/")
        current_dict = self.root

        for part in parts:
            if part not in current_dict:
                return None
            node = current_dict[part]
            current_dict = node.children

        return node

    def get_flattened_list(self) -> list[tuple[CategoryNode, int]]:
        """
        Get flattened list of visible categories (respecting collapse state).

        Returns:
            List of (node, indent_level) tuples
        """
        result = []

        def traverse(node_dict: dict[str, CategoryNode], depth: int):
            for name in sorted(node_dict.keys()):
                node = node_dict[name]
                result.append((node, depth))

                # Only traverse children if expanded
                if node.is_expanded and node.children:
                    traverse(node.children, depth + 1)

        traverse(self.root, 0)
        return result
