"""
NES Open Tournament Golf - Event Handler

Handles user input events including mouse, keyboard, and window events.
"""

from typing import Tuple, Optional, List, Callable

import pygame
from pygame import Rect

from .editor_state import EditorState
from golf.formats.hole_data import HoleData
from editor.ui.pickers import TilePicker, GreensTilePicker
from editor.ui.widgets import Button
from editor.core.constants import (
    CANVAS_OFFSET_X,
    CANVAS_OFFSET_Y,
    STATUS_HEIGHT,
    TILE_SIZE,
    TERRAIN_WIDTH,
    GREENS_WIDTH,
    GREENS_HEIGHT,
)


class EventHandler:
    """Handles all user input events."""

    def __init__(
        self,
        state: EditorState,
        hole_data: HoleData,
        terrain_picker: TilePicker,
        greens_picker: GreensTilePicker,
        buttons: List[Button],
        screen_width: int,
        screen_height: int,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        on_mode_change: Callable[[], None],
        on_flag_change: Callable[[], None],
        on_resize: Callable[[int, int], None],
    ):
        """
        Initialize event handler.

        Args:
            state: Editor state
            hole_data: Hole data
            terrain_picker: Terrain tile picker
            greens_picker: Greens tile picker
            buttons: List of UI buttons
            screen_width: Screen width
            screen_height: Screen height
            on_load: Callback for load action
            on_save: Callback for save action
            on_mode_change: Callback when mode changes
            on_flag_change: Callback when flag selection changes
            on_resize: Callback for window resize (width, height)
        """
        self.state = state
        self.hole_data = hole_data
        self.terrain_picker = terrain_picker
        self.greens_picker = greens_picker
        self.buttons = buttons
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.on_load = on_load
        self.on_save = on_save
        self.on_mode_change = on_mode_change
        self.on_flag_change = on_flag_change
        self.on_resize = on_resize

    def update_screen_size(self, width: int, height: int):
        """Update screen dimensions."""
        self.screen_width = width
        self.screen_height = height

    def handle_events(self, events: List[pygame.event.Event]) -> bool:
        """
        Handle all pygame events.

        Args:
            events: List of pygame events to process

        Returns:
            True if application should continue running, False if quit requested
        """
        for event in events:
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                self._handle_key(event)

            # Handle button events
            for button in self.buttons:
                button.handle_event(event)

            # Handle picker events
            if self.state.mode == "greens":
                self.greens_picker.handle_event(event)
            else:
                self.terrain_picker.handle_event(event)

            # Handle canvas events
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self.state.mouse_down = True
                    self._paint_at(event.pos)
                elif event.button == 3:  # Right click - eyedropper
                    self._eyedropper(event.pos)
                elif event.button == 4:  # Scroll up
                    self.state.canvas_offset_y = max(0, self.state.canvas_offset_y - 20)
                elif event.button == 5:  # Scroll down
                    self.state.canvas_offset_y += 20

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.state.mouse_down = False
                    self.state.last_paint_pos = None

            elif event.type == pygame.MOUSEMOTION:
                if self.state.mouse_down:
                    self._paint_at(event.pos)

            elif event.type == pygame.VIDEORESIZE:
                self.on_resize(event.w, event.h)

        return True

    def _handle_key(self, event):
        """Handle keyboard input."""
        if event.key == pygame.K_g:
            self.state.toggle_grid()

        elif event.key == pygame.K_1:
            self.state.selected_palette = 1
        elif event.key == pygame.K_2:
            self.state.selected_palette = 2
        elif event.key == pygame.K_3:
            self.state.selected_palette = 3

        elif event.key == pygame.K_TAB:
            # Cycle modes
            modes = ["terrain", "palette", "greens"]
            idx = modes.index(self.state.mode)
            self.state.set_mode(modes[(idx + 1) % len(modes)])
            self.on_mode_change()

        elif event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.on_save()
        elif event.key == pygame.K_o and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.on_load()

        elif event.key == pygame.K_LEFT:
            self.state.canvas_offset_x = max(0, self.state.canvas_offset_x - 20)
        elif event.key == pygame.K_RIGHT:
            self.state.canvas_offset_x += 20
        elif event.key == pygame.K_UP:
            self.state.canvas_offset_y = max(0, self.state.canvas_offset_y - 20)
        elif event.key == pygame.K_DOWN:
            self.state.canvas_offset_y += 20

        elif event.key == pygame.K_LEFTBRACKET:  # [
            # Previous flag position
            if self.hole_data.metadata.get("flag_positions"):
                num_flags = len(self.hole_data.metadata["flag_positions"])
                self.state.selected_flag_index = (self.state.selected_flag_index - 1) % num_flags
                self.on_flag_change()

        elif event.key == pygame.K_RIGHTBRACKET:  # ]
            # Next flag position
            if self.hole_data.metadata.get("flag_positions"):
                num_flags = len(self.hole_data.metadata["flag_positions"])
                self.state.selected_flag_index = (self.state.selected_flag_index + 1) % num_flags
                self.on_flag_change()

        elif event.key == pygame.K_v:  # Toggle sprites (V for "view")
            self.state.toggle_sprites()

    def _get_canvas_rect(self) -> Rect:
        """Get the canvas drawing area."""
        return Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            self.screen_width - CANVAS_OFFSET_X,
            self.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT
        )

    def _screen_to_tile(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Convert screen position to tile coordinates."""
        canvas_rect = self._get_canvas_rect()
        if not canvas_rect.collidepoint(screen_pos):
            return None

        local_x = screen_pos[0] - canvas_rect.x + self.state.canvas_offset_x
        local_y = screen_pos[1] - canvas_rect.y + self.state.canvas_offset_y

        tile_size = TILE_SIZE * self.state.canvas_scale
        tile_col = local_x // tile_size
        tile_row = local_y // tile_size

        return (tile_row, tile_col)

    def _screen_to_supertile(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Convert screen position to supertile (2x2) coordinates."""
        tile = self._screen_to_tile(screen_pos)
        if tile is None:
            return None
        return (tile[0] // 2, tile[1] // 2)

    def _paint_at(self, pos: Tuple[int, int]):
        """Paint at screen position based on current mode."""
        if self.state.mode == "terrain":
            tile = self._screen_to_tile(pos)
            if tile and tile != self.state.last_paint_pos:
                row, col = tile
                if 0 <= row < len(self.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                    self.hole_data.set_terrain_tile(row, col, self.terrain_picker.selected_tile)
                    self.state.last_paint_pos = tile

        elif self.state.mode == "palette":
            supertile = self._screen_to_supertile(pos)
            if supertile and supertile != self.state.last_paint_pos:
                row, col = supertile
                self.hole_data.set_attribute(row, col, self.state.selected_palette)
                self.state.last_paint_pos = supertile

        elif self.state.mode == "greens":
            tile = self._screen_to_tile(pos)
            if tile and tile != self.state.last_paint_pos:
                row, col = tile
                if 0 <= row < GREENS_HEIGHT and 0 <= col < GREENS_WIDTH:
                    self.hole_data.set_greens_tile(row, col, self.greens_picker.selected_tile)
                    self.state.last_paint_pos = tile

    def _eyedropper(self, pos: Tuple[int, int]):
        """Pick tile/palette from canvas."""
        if self.state.mode == "terrain":
            tile = self._screen_to_tile(pos)
            if tile:
                row, col = tile
                if 0 <= row < len(self.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                    self.terrain_picker.selected_tile = self.hole_data.terrain[row][col]

        elif self.state.mode == "palette":
            supertile = self._screen_to_supertile(pos)
            if supertile:
                row, col = supertile
                if 0 <= row < len(self.hole_data.attributes) and 0 <= col < len(self.hole_data.attributes[row]):
                    self.state.selected_palette = self.hole_data.attributes[row][col]

        elif self.state.mode == "greens":
            tile = self._screen_to_tile(pos)
            if tile:
                row, col = tile
                if 0 <= row < len(self.hole_data.greens) and 0 <= col < GREENS_WIDTH:
                    self.greens_picker.selected_tile = self.hole_data.greens[row][col]
