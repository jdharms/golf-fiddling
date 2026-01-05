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


class StampBrowser:
    """Stamp browser widget for selecting stamps from library."""

    # Category tabs
    CATEGORIES = ["terrain", "water", "bunker", "green", "user"]
    CATEGORY_LABELS = {
        "terrain": "Terrain",
        "water": "Water",
        "bunker": "Bunker",
        "green": "Green",
        "user": "User",
    }

    def __init__(
        self,
        rect: Rect,
        stamp_library: StampLibrary,
        font: pygame.font.Font,
        on_stamp_selected=None,
    ):
        """
        Initialize stamp browser.

        Args:
            rect: Browser panel rectangle
            stamp_library: StampLibrary instance
            font: Pygame font for rendering text
            on_stamp_selected: Callback when stamp is selected (receives StampData)
        """
        self.rect = rect
        self.stamp_library = stamp_library
        self.font = font
        self.on_stamp_selected = on_stamp_selected

        # Current category
        self.current_category = "terrain"

        # Scroll position
        self.scroll_y = 0

        # Selected stamp
        self.selected_stamp_id: str | None = None

        # Hovered stamp
        self.hovered_stamp_id: str | None = None

        # Layout constants
        self.tab_height = 30
        self.item_height = 60
        self.item_padding = 5
        self.margin = 10

        # Calculate tab rects
        self._calculate_tab_rects()

    def _calculate_tab_rects(self):
        """Calculate rectangles for category tabs."""
        tab_width = (self.rect.width - 20) // len(self.CATEGORIES)
        self.tab_rects = {}

        for i, category in enumerate(self.CATEGORIES):
            x = self.rect.x + 10 + i * tab_width
            y = self.rect.y + 10
            self.tab_rects[category] = Rect(x, y, tab_width, self.tab_height)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if handled."""
        if event.type == pygame.MOUSEMOTION:
            # Update hovered stamp/tab (doesn't consume event)
            if self.rect.collidepoint(event.pos):
                # Check if hovering over tabs
                for category, tab_rect in self.tab_rects.items():
                    if tab_rect.collidepoint(event.pos):
                        return False  # Let event propagate

                # Check if hovering over stamp list
                new_hover = self._stamp_at_position(event.pos)
                if new_hover != self.hovered_stamp_id:
                    self.hovered_stamp_id = new_hover
            else:
                self.hovered_stamp_id = None

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if event.button == 1:  # Left click
                    # Check tab clicks
                    for category, tab_rect in self.tab_rects.items():
                        if tab_rect.collidepoint(event.pos):
                            self.current_category = category
                            self.scroll_y = 0
                            return True

                    # Check stamp list clicks
                    stamp_id = self._stamp_at_position(event.pos)
                    if stamp_id:
                        self.selected_stamp_id = stamp_id
                        stamp = self.stamp_library.get_stamp(stamp_id)
                        if stamp and self.on_stamp_selected:
                            self.on_stamp_selected(stamp)
                        return True

                elif event.button == 4:  # Scroll up
                    self.scroll_y = max(0, self.scroll_y - 20)
                    return True
                elif event.button == 5:  # Scroll down
                    self.scroll_y += 20
                    return True

        return False

    def _stamp_at_position(self, pos: tuple[int, int]) -> str | None:
        """Get stamp ID at screen position, or None if invalid."""
        # Check if position is in stamp list area (below tabs)
        list_y_start = self.rect.y + 10 + self.tab_height + 10
        if pos[1] < list_y_start:
            return None

        local_y = pos[1] - list_y_start + self.scroll_y

        stamps = self.stamp_library.get_stamps_by_category(self.current_category)

        for i, stamp in enumerate(stamps):
            item_y_start = i * (self.item_height + self.item_padding)
            item_y_end = item_y_start + self.item_height

            if item_y_start <= local_y < item_y_end:
                return stamp.metadata.id

        return None

    def render(self, screen: Surface):
        """Render the stamp browser."""
        # Background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        # Render tabs
        for category in self.CATEGORIES:
            tab_rect = self.tab_rects[category]
            is_active = category == self.current_category

            # Tab background
            color = COLOR_BUTTON_ACTIVE if is_active else COLOR_BUTTON
            pygame.draw.rect(screen, color, tab_rect)

            # Tab border
            border_color = COLOR_SELECTION if is_active else COLOR_GRID
            border_width = 2 if is_active else 1
            pygame.draw.rect(screen, border_color, tab_rect, border_width)

            # Tab label
            label = self.CATEGORY_LABELS[category]
            text_surf = self.font.render(label, True, COLOR_TEXT)
            text_rect = text_surf.get_rect(center=tab_rect.center)
            screen.blit(text_surf, text_rect)

        # Create clipping rect for stamp list
        list_y_start = self.rect.y + 10 + self.tab_height + 10
        list_rect = Rect(
            self.rect.x + 10,
            list_y_start,
            self.rect.width - 20,
            self.rect.height - (10 + self.tab_height + 20),
        )

        # Render stamp list
        stamps = self.stamp_library.get_stamps_by_category(self.current_category)

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

                # Stamp name/ID
                display_name = stamp.get_display_name()
                name_surf = self.font.render(display_name, True, COLOR_TEXT)
                name_rect = name_surf.get_rect(
                    left=item_rect.left + 10,
                    centery=item_rect.centery - 10,
                )
                screen.blit(name_surf, name_rect)

                # Stamp dimensions
                size_text = f"{stamp.width}×{stamp.height}"
                size_surf = self.font.render(size_text, True, COLOR_TEXT)
                size_rect = size_surf.get_rect(
                    left=item_rect.left + 10,
                    centery=item_rect.centery + 10,
                )
                screen.blit(size_surf, size_rect)

    def resize(self, rect: Rect):
        """Update browser rectangle (e.g., on window resize)."""
        self.rect = rect
        self._calculate_tab_rects()
