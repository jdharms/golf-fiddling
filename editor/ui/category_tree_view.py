"""Category tree view widget for hierarchical stamp categories."""

import pygame
from pygame import Rect, Surface

from editor.resources import get_resource_path
from editor.core.constants import (
    COLOR_BUTTON,
    COLOR_BUTTON_ACTIVE,
    COLOR_BUTTON_HOVER,
    COLOR_GRID,
    COLOR_PICKER_BG,
    COLOR_SELECTION,
    COLOR_TEXT,
)
from editor.data.category_tree import CategoryNode, CategoryTree


class CategoryTreeView:
    """Collapsible tree view for stamp categories."""

    # Visual constants
    ITEM_HEIGHT = 24
    INDENT_SIZE = 16
    FOLDER_ICON_EXPANDED = "▼"
    FOLDER_ICON_COLLAPSED = "▶"

    def __init__(
        self,
        rect: Rect,
        category_tree: CategoryTree,
        font: pygame.font.Font,
        on_category_selected=None,
    ):
        """
        Initialize category tree view.

        Args:
            rect: View rectangle
            category_tree: CategoryTree instance
            font: Pygame font
            on_category_selected: Callback when category selected (receives category_path)
        """
        self.rect = rect
        self.category_tree = category_tree
        self.font = font
        self.icon_font = pygame.font.Font(str(get_resource_path('data/fonts/NotoEmoji.ttf')), 16)
        self.on_category_selected = on_category_selected

        # State
        self.selected_path: str | None = None
        self.hovered_path: str | None = None
        self.scroll_y = 0

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if handled."""
        if event.type == pygame.MOUSEMOTION:
            if self.rect.collidepoint(event.pos):
                self.hovered_path = self._category_at_position(event.pos)
            else:
                self.hovered_path = None

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if event.button == 1:  # Left click
                    category_path, click_zone = self._category_at_position_detailed(event.pos)
                    if category_path:
                        node = self.category_tree.get_node(category_path)
                        if node:
                            if click_zone == "icon" and node.children:
                                # Toggle expand/collapse
                                node.is_expanded = not node.is_expanded
                                return True
                            elif click_zone == "label":
                                # Select category
                                self.selected_path = category_path
                                if self.on_category_selected:
                                    self.on_category_selected(category_path)
                                return True

                elif event.button == 4:  # Scroll up
                    self.scroll_y = max(0, self.scroll_y - 20)
                    return True
                elif event.button == 5:  # Scroll down
                    self.scroll_y += 20
                    return True

        return False

    def _category_at_position(self, pos: tuple[int, int]) -> str | None:
        """Get category path at screen position."""
        category_path, _ = self._category_at_position_detailed(pos)
        return category_path

    def _category_at_position_detailed(self, pos: tuple[int, int]) -> tuple[str | None, str]:
        """
        Get category path and click zone at screen position.

        Returns:
            (category_path, click_zone) where click_zone is "icon" or "label"
        """
        local_y = pos[1] - self.rect.y + self.scroll_y
        local_x = pos[0] - self.rect.x

        item_index = local_y // self.ITEM_HEIGHT
        flattened = self.category_tree.get_flattened_list()

        if 0 <= item_index < len(flattened):
            node, depth = flattened[item_index]
            icon_x_start = depth * self.INDENT_SIZE + 5
            icon_x_end = icon_x_start + 12

            if icon_x_start <= local_x < icon_x_end:
                return (node.path, "icon")
            else:
                return (node.path, "label")

        return (None, "")

    def render(self, screen: Surface):
        """Render category tree."""
        # Background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        # Get flattened visible categories
        flattened = self.category_tree.get_flattened_list()

        # Render each category
        for i, (node, depth) in enumerate(flattened):
            item_y = self.rect.y + i * self.ITEM_HEIGHT - self.scroll_y

            # Skip if outside visible area
            if item_y + self.ITEM_HEIGHT < self.rect.y or item_y > self.rect.bottom:
                continue

            item_rect = Rect(self.rect.x, item_y, self.rect.width, self.ITEM_HEIGHT)

            # Background
            is_selected = node.path == self.selected_path
            is_hovered = node.path == self.hovered_path

            if is_selected:
                color = COLOR_BUTTON_ACTIVE
            elif is_hovered:
                color = COLOR_BUTTON_HOVER
            else:
                color = COLOR_BUTTON

            pygame.draw.rect(screen, color, item_rect)

            # Border
            border_color = COLOR_SELECTION if is_selected else COLOR_GRID
            border_width = 2 if is_selected else 1
            pygame.draw.rect(screen, border_color, item_rect, border_width)

            # Indent
            indent_x = self.rect.x + depth * self.INDENT_SIZE + 5

            # Folder icon (if has children)
            if node.children:
                icon = self.FOLDER_ICON_EXPANDED if node.is_expanded else self.FOLDER_ICON_COLLAPSED
                icon_surf = self.icon_font.render(icon, True, COLOR_TEXT)
                screen.blit(icon_surf, (indent_x, item_y + 4))
                label_x = indent_x + 16
            else:
                label_x = indent_x + 8

            # Category name
            label_surf = self.font.render(node.name, True, COLOR_TEXT)
            screen.blit(label_surf, (label_x, item_y + 4))

            # Stamp count (optional - show in gray)
            count_text = f"({len(node.stamp_ids)})"
            count_surf = self.font.render(count_text, True, COLOR_GRID)
            count_x = self.rect.right - count_surf.get_width() - 10
            screen.blit(count_surf, (count_x, item_y + 4))

    def resize(self, rect: Rect):
        """Update view rectangle (e.g., on window resize)."""
        self.rect = rect
