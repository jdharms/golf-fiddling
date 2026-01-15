"""
Tool picker - UI component for selecting active editor tool.
"""

from typing import Callable

import pygame
from pygame import Rect, Surface

from editor.core.constants import (
    COLOR_BUTTON,
    COLOR_BUTTON_ACTIVE,
    COLOR_BUTTON_HOVER,
    COLOR_PICKER_BG,
    COLOR_TEXT,
)


class ToolButton:
    """Individual tool button in the picker."""

    def __init__(self, tool_name: str, label: str, icon_char: str, is_action: bool = False):
        self.tool_name = tool_name  # "paint", "transform", "forest_fill"
        self.label = label  # "Paint", "Transform", "Forest Fill"
        self.icon_char = icon_char  # Unicode icon/emoji
        self.is_action = is_action  # True for action tools that execute immediately
        self.rect: Rect | None = None  # Set during layout
        self.hovered = False


class ToolPicker:
    """Tool selection picker - right sidebar."""

    BUTTON_HEIGHT = 60
    BUTTON_SPACING = 5
    TOP_PADDING = 10

    def __init__(self, rect: Rect, on_tool_change: Callable[[str], None]):
        self.rect = rect
        self.on_tool_change = on_tool_change
        self.selected_tool = "paint"  # Default
        self.icon_font = pygame.font.Font('data/fonts/NotoEmoji.ttf', 36)
        self.buttons: list[ToolButton] = []

    def register_tool(self, tool_name: str, label: str, icon: str, is_action: bool = False):
        """Add a tool to the picker."""
        button = ToolButton(tool_name, label, icon, is_action)
        self.buttons.append(button)
        self._calculate_button_positions()

    def _calculate_button_positions(self):
        """Calculate and update button rect positions."""
        y_offset = self.rect.top + self.TOP_PADDING
        for button in self.buttons:
            button.rect = Rect(
                self.rect.left + 5,
                y_offset,
                self.rect.width - 10,
                self.BUTTON_HEIGHT,
            )
            y_offset += self.BUTTON_HEIGHT + self.BUTTON_SPACING

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle mouse clicks and hover. Returns True if handled."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check if click is on any button
            for button in self.buttons:
                if button.rect and button.rect.collidepoint(event.pos):
                    if button.is_action:
                        # Action tools: always execute, don't change selection
                        self.on_tool_change(button.tool_name)
                    else:
                        # Modal tools: only change if different
                        if button.tool_name != self.selected_tool:
                            self.selected_tool = button.tool_name
                            self.on_tool_change(button.tool_name)
                    return True

        elif event.type == pygame.MOUSEMOTION:
            # Update hover states
            mouse_pos = event.pos
            for button in self.buttons:
                if button.rect:
                    button.hovered = button.rect.collidepoint(mouse_pos)

        return False

    def render(self, screen: Surface, font: pygame.font.Font):
        """Render tool buttons with selection highlight."""
        # Background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        # Render each button
        for button in self.buttons:
            if not button.rect:
                continue

            # Determine button color
            if button.tool_name == self.selected_tool:
                color = COLOR_BUTTON_ACTIVE
            elif button.hovered:
                color = COLOR_BUTTON_HOVER
            else:
                color = COLOR_BUTTON

            # Draw button background
            pygame.draw.rect(screen, color, button.rect)
            pygame.draw.rect(screen, COLOR_TEXT, button.rect, 1)  # Border

            # Render icon (centered, larger font)
            icon_font = self.icon_font
            icon_surface = icon_font.render(button.icon_char, True, COLOR_TEXT)
            icon_rect = icon_surface.get_rect(
                centerx=button.rect.centerx, centery=button.rect.centery - 10
            )
            screen.blit(icon_surface, icon_rect)

            # Render label (centered, below icon)
            label_surface = font.render(button.label, True, COLOR_TEXT)
            label_rect = label_surface.get_rect(
                centerx=button.rect.centerx, centery=button.rect.centery + 15
            )
            screen.blit(label_surface, label_rect)
