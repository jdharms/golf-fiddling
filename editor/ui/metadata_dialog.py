"""
Metadata editing dialog for hole par and distance.

Allows user to:
- Edit par value (3-7)
- Edit distance value (100-999 yards)
- Live validation with visual feedback
- Save or cancel changes
"""

import pygame
from pygame import Rect, Surface

from editor.core.constants import (
    COLOR_BUTTON,
    COLOR_BUTTON_HOVER,
    COLOR_GRID,
    COLOR_PICKER_BG,
    COLOR_SELECTION,
    COLOR_TEXT,
)
from golf.formats.hole_data import HoleData


class MetadataDialog:
    """Modal dialog for editing hole metadata (par and distance)."""

    # Validation error color
    COLOR_ERROR = (255, 50, 50)

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        hole_data: HoleData,
        font: pygame.font.Font,
    ):
        """
        Initialize metadata dialog.

        Args:
            screen_width: Screen width
            screen_height: Screen height
            hole_data: HoleData to edit
            font: Pygame font for rendering text
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.hole_data = hole_data
        self.font = font

        # Dialog dimensions
        self.dialog_width = 400
        self.dialog_height = 250
        self.dialog_rect = Rect(
            (screen_width - self.dialog_width) // 2,
            (screen_height - self.dialog_height) // 2,
            self.dialog_width,
            self.dialog_height,
        )

        # Initialize field values from hole_data
        par = hole_data.metadata.get("par", 4)
        distance = hole_data.metadata.get("distance", 400)

        # Text field state
        self.par_value = str(par)
        self.par_active = False
        self.par_valid = self._validate_par(self.par_value)

        self.distance_value = str(distance)
        self.distance_active = False
        self.distance_valid = self._validate_distance(self.distance_value)

        # Calculate layout
        self._calculate_layout()

        # Result tracking
        self.saved = False
        self.cancelled = False

    def _calculate_layout(self):
        """Calculate layout rectangles."""
        margin = 20
        button_height = 40
        input_height = 30
        label_width = 80

        # Title at top
        self.title_y = self.dialog_rect.y + margin

        # Par field
        par_y = self.title_y + 60
        self.par_label_rect = Rect(
            self.dialog_rect.x + margin,
            par_y,
            label_width,
            input_height,
        )
        self.par_input_rect = Rect(
            self.par_label_rect.right + 10,
            par_y,
            80,
            input_height,
        )
        self.par_hint_rect = Rect(
            self.par_input_rect.right + 10,
            par_y,
            100,
            input_height,
        )

        # Distance field
        distance_y = par_y + 50
        self.distance_label_rect = Rect(
            self.dialog_rect.x + margin,
            distance_y,
            label_width,
            input_height,
        )
        self.distance_input_rect = Rect(
            self.distance_label_rect.right + 10,
            distance_y,
            100,
            input_height,
        )
        self.distance_hint_rect = Rect(
            self.distance_input_rect.right + 10,
            distance_y,
            150,
            input_height,
        )

        # Buttons at bottom
        button_width = 100
        button_y = self.dialog_rect.bottom - margin - button_height
        self.save_button_rect = Rect(
            self.dialog_rect.centerx - button_width - 10,
            button_y,
            button_width,
            button_height,
        )
        self.cancel_button_rect = Rect(
            self.dialog_rect.centerx + 10,
            button_y,
            button_width,
            button_height,
        )

    def _validate_par(self, value_str: str) -> bool:
        """Validate par value (must be integer 3-7)."""
        try:
            par = int(value_str)
            return 3 <= par <= 7
        except ValueError:
            return False

    def _validate_distance(self, value_str: str) -> bool:
        """Validate distance value (must be integer 100-999)."""
        try:
            distance = int(value_str)
            return 100 <= distance <= 999
        except ValueError:
            return False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        Handle input events.

        Returns:
            True if dialog should close, False otherwise
        """
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check buttons
            if self.save_button_rect.collidepoint(event.pos):
                return self._save()
            elif self.cancel_button_rect.collidepoint(event.pos):
                self.cancelled = True
                return True

            # Check field clicks
            if self.par_input_rect.collidepoint(event.pos):
                self.par_active = True
                self.distance_active = False
            elif self.distance_input_rect.collidepoint(event.pos):
                self.distance_active = True
                self.par_active = False
            else:
                self.par_active = False
                self.distance_active = False

        elif event.type == pygame.KEYDOWN:
            # Handle par input
            if self.par_active:
                if event.key == pygame.K_BACKSPACE:
                    self.par_value = self.par_value[:-1]
                    self.par_valid = self._validate_par(self.par_value)
                elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                    self.par_active = False
                    if event.key == pygame.K_TAB:
                        self.distance_active = True
                elif event.unicode and event.unicode.isprintable():
                    # Only allow digits
                    if event.unicode.isdigit() and len(self.par_value) < 2:
                        self.par_value += event.unicode
                        self.par_valid = self._validate_par(self.par_value)

            # Handle distance input
            elif self.distance_active:
                if event.key == pygame.K_BACKSPACE:
                    self.distance_value = self.distance_value[:-1]
                    self.distance_valid = self._validate_distance(self.distance_value)
                elif event.key == pygame.K_RETURN:
                    self.distance_active = False
                elif event.unicode and event.unicode.isprintable():
                    # Only allow digits
                    if event.unicode.isdigit() and len(self.distance_value) < 3:
                        self.distance_value += event.unicode
                        self.distance_valid = self._validate_distance(self.distance_value)

            # Global keys (no field active)
            else:
                if event.key == pygame.K_ESCAPE:
                    self.cancelled = True
                    return True
                elif event.key == pygame.K_RETURN:
                    return self._save()

        return False

    def _save(self) -> bool:
        """
        Save changes to hole_data.

        Returns:
            True if saved successfully (dialog should close), False otherwise
        """
        # Validate all fields
        if not self.par_valid or not self.distance_valid:
            return False  # Don't close dialog

        # Apply changes
        try:
            self.hole_data.metadata["par"] = int(self.par_value)
            self.hole_data.metadata["distance"] = int(self.distance_value)
            self.hole_data.modified = True
            self.saved = True
            return True  # Close dialog
        except ValueError:
            return False  # Don't close if conversion fails

    def render(self, screen: Surface):
        """Render the dialog."""
        # Semi-transparent overlay
        overlay = Surface((self.screen_width, self.screen_height))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        # Dialog background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.dialog_rect)
        pygame.draw.rect(screen, COLOR_GRID, self.dialog_rect, 2)

        # Title
        title_surf = self.font.render("Edit Hole Metadata", True, COLOR_TEXT)
        title_rect = title_surf.get_rect(
            centerx=self.dialog_rect.centerx,
            y=self.title_y,
        )
        screen.blit(title_surf, title_rect)

        # Par label and input
        self._render_field(
            screen,
            "Par:",
            self.par_label_rect,
            self.par_input_rect,
            self.par_hint_rect,
            self.par_value,
            self.par_active,
            self.par_valid,
            "(3-7)",
        )

        # Distance label and input
        self._render_field(
            screen,
            "Distance:",
            self.distance_label_rect,
            self.distance_input_rect,
            self.distance_hint_rect,
            self.distance_value,
            self.distance_active,
            self.distance_valid,
            "(100-999 yards)",
        )

        # Buttons
        self._render_button(screen, self.save_button_rect, "Save")
        self._render_button(screen, self.cancel_button_rect, "Cancel")

    def _render_field(
        self,
        screen: Surface,
        label: str,
        label_rect: Rect,
        input_rect: Rect,
        hint_rect: Rect,
        value: str,
        is_active: bool,
        is_valid: bool,
        hint_text: str,
    ):
        """Render a text input field with label and hint."""
        # Label
        label_surf = self.font.render(label, True, COLOR_TEXT)
        label_pos = label_surf.get_rect(
            left=label_rect.left,
            centery=label_rect.centery,
        )
        screen.blit(label_surf, label_pos)

        # Input box background
        pygame.draw.rect(screen, COLOR_BUTTON, input_rect)

        # Input box border (color based on state)
        if not is_valid:
            border_color = self.COLOR_ERROR  # Red for invalid
        elif is_active:
            border_color = COLOR_SELECTION  # Yellow for active
        else:
            border_color = COLOR_GRID  # Gray for inactive

        pygame.draw.rect(screen, border_color, input_rect, 2)

        # Value text (or placeholder if empty)
        if value:
            value_surf = self.font.render(value, True, COLOR_TEXT)
        else:
            value_surf = self.font.render("", True, COLOR_GRID)

        value_pos = value_surf.get_rect(
            left=input_rect.left + 5,
            centery=input_rect.centery,
        )
        screen.blit(value_surf, value_pos)

        # Hint text
        hint_surf = self.font.render(hint_text, True, COLOR_GRID)
        hint_pos = hint_surf.get_rect(
            left=hint_rect.left,
            centery=hint_rect.centery,
        )
        screen.blit(hint_surf, hint_pos)

    def _render_button(self, screen: Surface, rect: Rect, text: str):
        """Render a button."""
        is_hovered = rect.collidepoint(pygame.mouse.get_pos())
        color = COLOR_BUTTON_HOVER if is_hovered else COLOR_BUTTON

        pygame.draw.rect(screen, color, rect)
        pygame.draw.rect(screen, COLOR_GRID, rect, 1)

        text_surf = self.font.render(text, True, COLOR_TEXT)
        text_rect = text_surf.get_rect(center=rect.center)
        screen.blit(text_surf, text_rect)
