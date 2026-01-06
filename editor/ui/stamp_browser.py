"""
Stamp browser panel for browsing and selecting stamp patterns.

Replaces tile picker when Stamp tool is active.
"""

import pygame
from pygame import Rect, Surface

from editor.controllers.stamp_library import StampLibrary
from editor.core.constants import (
    COLOR_BUTTON,
    COLOR_BUTTON_ACTIVE,
    COLOR_BUTTON_HOVER,
    COLOR_GRID,
    COLOR_PICKER_BG,
    COLOR_SELECTION,
    COLOR_TEXT,
)
from editor.data import StampData
from editor.ui.category_tree_view import CategoryTreeView


class StampBrowser:
    """Stamp browser widget for selecting stamps from library."""

    def __init__(
        self,
        rect: Rect,
        stamp_library: StampLibrary,
        font: pygame.font.Font,
        tileset,
        on_stamp_selected=None,
    ):
        """
        Initialize stamp browser.

        Args:
            rect: Browser panel rectangle
            stamp_library: StampLibrary instance
            font: Pygame font for rendering text
            tileset: Tileset for rendering stamp previews
            on_stamp_selected: Callback when stamp is selected (receives StampData)
        """
        self.rect = rect
        self.stamp_library = stamp_library
        self.font = font
        self.tileset = tileset
        self.on_stamp_selected = on_stamp_selected

        # Current category path (selected in tree)
        self.current_category: str | None = None

        # Scroll position for stamp list
        self.scroll_y = 0

        # Selected stamp
        self.selected_stamp_id: str | None = None

        # Hovered stamp
        self.hovered_stamp_id: str | None = None

        # Preview cache for performance
        self._preview_cache: dict[str, Surface] = {}

        # Layout constants
        self.tree_height = 200  # Height of category tree view
        self.item_height = 80  # Increased from 60 to accommodate previews
        self.preview_box_size = 48
        self.item_padding = 5
        self.margin = 10

        # Create category tree view
        tree_rect = Rect(
            rect.x + 10,
            rect.y + 10,
            rect.width - 20,
            self.tree_height,
        )
        self.category_tree_view = CategoryTreeView(
            tree_rect,
            stamp_library.category_tree,
            font,
            on_category_selected=self._on_category_selected,
        )

    def _on_category_selected(self, category_path: str):
        """Callback when category is selected in tree."""
        self.current_category = category_path
        self.scroll_y = 0  # Reset scroll when changing categories

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if handled."""
        # Delegate to category tree view first
        if self.category_tree_view.handle_event(event):
            return True

        # Then handle stamp list events
        if event.type == pygame.MOUSEMOTION:
            if self.rect.collidepoint(event.pos):
                new_hover = self._stamp_at_position(event.pos)
                if new_hover != self.hovered_stamp_id:
                    self.hovered_stamp_id = new_hover
            else:
                self.hovered_stamp_id = None

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if event.button == 1:  # Left click
                    stamp_id = self._stamp_at_position(event.pos)
                    if stamp_id:
                        self.selected_stamp_id = stamp_id
                        stamp = self.stamp_library.get_stamp(stamp_id)
                        if stamp and self.on_stamp_selected:
                            self.on_stamp_selected(stamp)
                        return True

                elif event.button == 4:  # Scroll up (stamp list)
                    self.scroll_y = max(0, self.scroll_y - 20)
                    return True
                elif event.button == 5:  # Scroll down (stamp list)
                    self.scroll_y += 20
                    return True

        return False

    def _stamp_at_position(self, pos: tuple[int, int]) -> str | None:
        """Get stamp ID at screen position, or None if invalid."""
        # Check if position is in stamp list area (below tree view)
        list_y_start = self.rect.y + 10 + self.tree_height + 10
        if pos[1] < list_y_start:
            return None

        local_y = pos[1] - list_y_start + self.scroll_y

        # Get stamps for current category path
        if not self.current_category:
            return None

        stamps = self.stamp_library.get_stamps_by_path(self.current_category)

        for i, stamp in enumerate(stamps):
            item_y_start = i * (self.item_height + self.item_padding)
            item_y_end = item_y_start + self.item_height

            if item_y_start <= local_y < item_y_end:
                return stamp.metadata.id

        return None

    @staticmethod
    def _draw_checkered_tile(surface: Surface, x: int, y: int, size: int):
        """
        Draw a checkered pattern to indicate transparent tile.

        Args:
            surface: Pygame surface to draw on
            x: X position
            y: Y position
            size: Tile size
        """
        # Checkered pattern colors (gray tones)
        TRANSPARENT_COLOR1 = (100, 100, 100)
        TRANSPARENT_COLOR2 = (140, 140, 140)

        checker_size = max(size // 4, 2)

        for row in range(0, size, checker_size):
            for col in range(0, size, checker_size):
                # Alternate colors in checkerboard pattern
                if (row // checker_size + col // checker_size) % 2 == 0:
                    color = TRANSPARENT_COLOR1
                else:
                    color = TRANSPARENT_COLOR2

                rect = pygame.Rect(x + col, y + row, checker_size, checker_size)
                pygame.draw.rect(surface, color, rect)

    def _render_stamp_preview(
        self, screen: Surface, stamp, preview_rect: Rect, palette_idx: int
    ) -> None:
        """
        Render stamp preview scaled to fit preview box.

        Args:
            screen: Pygame surface
            stamp: StampData to render
            preview_rect: Rectangle for preview (e.g., 48x48)
            palette_idx: Palette index to use for rendering
        """
        from editor.core.constants import TILE_SIZE

        # Create cache key with palette
        cache_key = f"{stamp.metadata.id}_p{palette_idx}"

        # Check cache first
        if cache_key in self._preview_cache:
            cached_surf = self._preview_cache[cache_key]
            # Center cached preview in preview box
            center_x = preview_rect.centerx - cached_surf.get_width() // 2
            center_y = preview_rect.centery - cached_surf.get_height() // 2
            screen.blit(cached_surf, (center_x, center_y))
            # Draw border around preview box
            pygame.draw.rect(screen, COLOR_GRID, preview_rect, 1)
            return

        # Calculate scale to fit preview box
        max_dimension = max(stamp.width, stamp.height)
        tile_scale = max(1, preview_rect.width // (max_dimension * TILE_SIZE))

        # Create temporary surface for stamp
        stamp_width = stamp.width * TILE_SIZE * tile_scale
        stamp_height = stamp.height * TILE_SIZE * tile_scale
        stamp_surf = Surface((stamp_width, stamp_height))
        stamp_surf.fill(COLOR_PICKER_BG)

        # Render each tile
        for row in range(stamp.height):
            for col in range(stamp.width):
                tile_value = stamp.get_tile(row, col)
                tile_size = TILE_SIZE * tile_scale
                tile_x = col * tile_size
                tile_y = row * tile_size

                if tile_value is None:
                    # Transparent tile: draw checkered pattern
                    self._draw_checkered_tile(stamp_surf, tile_x, tile_y, tile_size)
                else:
                    # Regular tile: render with selected palette
                    tile_surf = self.tileset.render_tile(tile_value, palette_idx, tile_scale)
                    stamp_surf.blit(tile_surf, (tile_x, tile_y))

        # Cache the preview with palette
        self._preview_cache[cache_key] = stamp_surf

        # Center stamp in preview box
        center_x = preview_rect.centerx - stamp_surf.get_width() // 2
        center_y = preview_rect.centery - stamp_surf.get_height() // 2
        screen.blit(stamp_surf, (center_x, center_y))

        # Draw border around preview box
        pygame.draw.rect(screen, COLOR_GRID, preview_rect, 1)

    def render(self, screen: Surface, palette_idx: int = 0):
        """
        Render the stamp browser.

        Args:
            screen: Pygame surface
            palette_idx: Palette index to use for stamp previews (default: 0)
        """
        # Background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        # Render category tree view
        self.category_tree_view.render(screen)

        # Create clipping rect for stamp list (below tree view)
        list_y_start = self.rect.y + 10 + self.tree_height + 10
        list_rect = Rect(
            self.rect.x + 10,
            list_y_start,
            self.rect.width - 20,
            self.rect.height - (10 + self.tree_height + 20),
        )

        # Render stamp list
        if not self.current_category:
            # Show "Select a category" message
            msg_surf = self.font.render("Select a category", True, COLOR_TEXT)
            msg_rect = msg_surf.get_rect(center=list_rect.center)
            screen.blit(msg_surf, msg_rect)
            return

        stamps = self.stamp_library.get_stamps_by_path(self.current_category)

        if not stamps:
            # Show "No stamps" message
            msg_surf = self.font.render("No stamps in this category", True, COLOR_TEXT)
            msg_rect = msg_surf.get_rect(center=list_rect.center)
            screen.blit(msg_surf, msg_rect)
        else:
            # Render each stamp item
            for i, stamp in enumerate(stamps):
                item_y = list_y_start + i * (self.item_height + self.item_padding) - self.scroll_y
                item_rect = Rect(
                    list_rect.x,
                    item_y,
                    list_rect.width,
                    self.item_height,
                )

                # Skip items outside visible area
                if item_y + self.item_height < list_rect.y or item_y > list_rect.bottom:
                    continue

                is_selected = stamp.metadata.id == self.selected_stamp_id
                is_hovered = stamp.metadata.id == self.hovered_stamp_id

                # Item background
                if is_selected:
                    color = COLOR_BUTTON_ACTIVE
                elif is_hovered:
                    color = COLOR_BUTTON_HOVER
                else:
                    color = COLOR_BUTTON

                pygame.draw.rect(screen, color, item_rect)

                # Item border
                border_color = COLOR_SELECTION if is_selected else COLOR_GRID
                border_width = 2 if is_selected else 1
                pygame.draw.rect(screen, border_color, item_rect, border_width)

                # Preview box (left side)
                preview_rect = Rect(
                    item_rect.left + 5,
                    item_rect.centery - self.preview_box_size // 2,
                    self.preview_box_size,
                    self.preview_box_size,
                )
                self._render_stamp_preview(screen, stamp, preview_rect, palette_idx)

                # Text area (right side of preview)
                text_x_start = preview_rect.right + 10

                # Stamp name/ID
                display_name = stamp.get_display_name()
                name_surf = self.font.render(display_name, True, COLOR_TEXT)
                name_rect = name_surf.get_rect(
                    left=text_x_start,
                    centery=item_rect.centery - 10,
                )
                screen.blit(name_surf, name_rect)

                # Stamp dimensions
                size_text = f"{stamp.width}×{stamp.height}"
                size_surf = self.font.render(size_text, True, COLOR_TEXT)
                size_rect = size_surf.get_rect(
                    left=text_x_start,
                    centery=item_rect.centery + 10,
                )
                screen.blit(size_surf, size_rect)

    def resize(self, rect: Rect):
        """Update browser rectangle (e.g., on window resize)."""
        self.rect = rect
        # Update category tree view rectangle
        tree_rect = Rect(
            rect.x + 10,
            rect.y + 10,
            rect.width - 20,
            self.tree_height,
        )
        self.category_tree_view.resize(tree_rect)
