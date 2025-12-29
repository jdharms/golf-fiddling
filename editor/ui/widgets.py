"""
NES Open Tournament Golf - UI Widgets

Basic UI widget components for the editor.
"""

import pygame
from pygame import Surface, Rect

from editor.core.constants import (
    COLOR_BUTTON,
    COLOR_BUTTON_HOVER,
    COLOR_BUTTON_ACTIVE,
    COLOR_GRID,
    COLOR_TEXT,
)


class Button:
    """Simple button widget."""

    def __init__(self, rect: Rect, text: str, callback):
        self.rect = rect
        self.text = text
        self.callback = callback
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
        color = COLOR_BUTTON_ACTIVE if self.active else (COLOR_BUTTON_HOVER if self.hovered else COLOR_BUTTON)
        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, COLOR_GRID, self.rect, 1)

        text_surf = font.render(self.text, True, COLOR_TEXT)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)
