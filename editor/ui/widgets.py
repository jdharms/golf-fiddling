"""
NES Open Tournament Golf - UI Widgets

Basic UI widget components for the editor.
"""

import pygame
from pygame import Rect, Surface

from editor.core.constants import (
    COLOR_BUTTON,
    COLOR_BUTTON_ACTIVE,
    COLOR_BUTTON_HOVER,
    COLOR_GRID,
    COLOR_SELECTION,
    COLOR_TEXT,
)


class Button:
    """Simple button widget."""

    def __init__(self, rect: Rect, text: str, callback, background_color=None):
        self.rect = rect
        self.text = text
        self.callback = callback
        self.background_color = background_color
        self.hovered = False
        self.active = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()
                return True
        return False

    def render(self, screen: Surface, font: pygame.font.Font):
        # Use background_color if provided, otherwise use standard button colors
        if self.background_color:
            pygame.draw.rect(screen, self.background_color, self.rect)
        else:
            color = (
                COLOR_BUTTON_ACTIVE
                if self.active
                else (COLOR_BUTTON_HOVER if self.hovered else COLOR_BUTTON)
            )
            pygame.draw.rect(screen, color, self.rect)

        # Draw selection border (thicker if active)
        border_color = COLOR_SELECTION if self.active else COLOR_GRID
        border_width = 2 if self.active else 1
        pygame.draw.rect(screen, border_color, self.rect, border_width)

        text_surf = font.render(self.text, True, COLOR_TEXT)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)
