"""
Toolbar for editor buttons.
"""

import pygame
from pygame import Rect

from editor.core.constants import COLOR_TOOLBAR, PALETTES, TOOLBAR_HEIGHT

from .widgets import Button


class ToolbarCallbacks:
    """Container for toolbar callbacks."""

    def __init__(self, **callbacks):
        for name, callback in callbacks.items():
            setattr(self, name, callback)


class Toolbar:
    """Manages toolbar buttons and layout."""

    def __init__(self, screen_width: int, callbacks: ToolbarCallbacks):
        self.screen_width = screen_width
        self.callbacks = callbacks

        # Button groups
        self.file_buttons: list[Button] = []
        self.mode_buttons: list[Button] = []
        self.tool_buttons: list[Button] = []
        self.flag_buttons: list[Button] = []
        self.palette_buttons: list[Button] = []

        self._create_buttons()

        # All buttons
        self.buttons = (
            self.file_buttons
            + self.mode_buttons
            + self.tool_buttons
            + self.flag_buttons
            + self.palette_buttons
        )

    def _create_buttons(self):
        """Create all toolbar buttons with automatic layout."""
        x = 10

        # File buttons
        btn_load = Button(Rect(x, 5, 60, 30), "Load", self.callbacks.on_load)
        self.file_buttons.append(btn_load)
        x += 70

        btn_save = Button(Rect(x, 5, 60, 30), "Save", self.callbacks.on_save)
        self.file_buttons.append(btn_save)
        x += 80

        # Mode buttons
        btn_terrain = Button(
            Rect(x, 5, 70, 30), "Terrain", lambda: self.callbacks.on_set_mode("terrain")
        )
        self.mode_buttons.append(btn_terrain)
        x += 80

        btn_greens = Button(
            Rect(x, 5, 70, 30), "Greens", lambda: self.callbacks.on_set_mode("greens")
        )
        self.mode_buttons.append(btn_greens)
        x += 90

        # Utility buttons
        btn_grid = Button(Rect(x, 5, 50, 30), "Grid", self.callbacks.on_toggle_grid)
        self.tool_buttons.append(btn_grid)
        x += 60

        # Flag position buttons
        for i in range(4):
            btn = Button(
                Rect(x + (i * 35), 5, 30, 30),
                f"F{i + 1}",
                lambda idx=i: self.callbacks.on_select_flag(idx),
            )
            self.flag_buttons.append(btn)
        x += 150

        # Palette selector buttons
        for i in range(1, 4):
            btn = Button(
                Rect(x + ((i - 1) * 30), 8, 24, 24),
                str(i),
                lambda idx=i: self.callbacks.on_set_palette(idx),
                background_color=PALETTES[i][3],
            )
            self.palette_buttons.append(btn)
        x += 100

    def handle_events(self, events):
        """Delegate events to all buttons."""
        for button in self.buttons:
            for event in events:
                button.handle_event(event)

    def render(self, screen, font, font_small):
        """Render toolbar background and all buttons."""
        pygame.draw.rect(
            screen, COLOR_TOOLBAR, (0, 0, self.screen_width, TOOLBAR_HEIGHT)
        )
        for button in self.buttons:
            button.render(
                screen, font_small if button in self.palette_buttons else font
            )

    def resize(self, screen_width: int):
        """Update button positions for new screen width without recreating."""
        self.screen_width = screen_width
        # For now, positions are absolute. In future could make dynamic.
        # Buttons maintain their positions since they're fixed layout.

    def get_mode_buttons(self):
        """Get mode buttons for updating active state."""
        return self.mode_buttons

    def get_flag_buttons(self):
        """Get flag buttons for updating active state."""
        return self.flag_buttons

    def get_palette_buttons(self):
        """Get palette buttons for updating active state."""
        return self.palette_buttons
