"""
NES Open Tournament Golf - Editor Application

Main application class that orchestrates all editor components.
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame
from pygame import Rect

from .core.constants import *
from .core.pygame_rendering import Tileset, Sprite
from golf.formats.hole_data import HoleData
from .ui.widgets import Button
from .ui.pickers import TilePicker, GreensTilePicker
from .ui.dialogs import open_file_dialog, save_file_dialog
from .controllers.editor_state import EditorState
from .controllers.event_handler import EventHandler
from .rendering.terrain_renderer import TerrainRenderer
from .rendering.greens_renderer import GreensRenderer


class EditorApplication:
    """Main editor application."""

    def __init__(self, terrain_chr: str, greens_chr: str):
        pygame.init()

        self.screen_width = 1200
        self.screen_height = 800
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height),
            pygame.RESIZABLE
        )
        pygame.display.set_caption("NES Open Golf Course Editor")

        self.font = pygame.font.SysFont("monospace", 14)
        self.font_small = pygame.font.SysFont("monospace", 12)

        # Load tilesets
        self.terrain_tileset = Tileset(terrain_chr)
        self.greens_tileset = Tileset(greens_chr)

        # Load sprites
        self.sprites: Dict[str, Optional[Sprite]] = {}
        sprite_files = {
            "flag": "data/sprites/flag.json",
            "tee": "data/sprites/tee-block.json",
            "ball": "data/sprites/ball.json",
            "green-cup": "data/sprites/green-cup.json",
            "green-flag": "data/sprites/green-flag.json",
        }

        for sprite_name, sprite_path in sprite_files.items():
            try:
                self.sprites[sprite_name] = Sprite(sprite_path)
            except FileNotFoundError:
                print(f"Warning: Sprite file not found: {sprite_path}")
                self.sprites[sprite_name] = None
            except Exception as e:
                print(f"Warning: Failed to load sprite {sprite_name}: {e}")
                self.sprites[sprite_name] = None

        # Create application state
        self.state = EditorState()
        self.hole_data = HoleData()

        # Create UI elements
        self.buttons: List[Button] = []
        self.btn_terrain: Optional[Button] = None
        self.btn_palette: Optional[Button] = None
        self.btn_greens: Optional[Button] = None
        self.btn_sprites: Optional[Button] = None
        self.flag_buttons: List[Button] = []
        self.terrain_picker: Optional[TilePicker] = None
        self.greens_picker: Optional[GreensTilePicker] = None
        self._create_ui()

        # Create event handler
        self.event_handler = EventHandler(
            self.state,
            self.hole_data,
            self.terrain_picker,
            self.greens_picker,
            self.buttons,
            self.screen_width,
            self.screen_height,
            on_load=self._on_load,
            on_save=self._on_save,
            on_mode_change=self._update_mode_buttons,
            on_flag_change=self._update_flag_buttons,
            on_resize=self._on_resize,
        )

        self.running = True
        self.clock = pygame.time.Clock()

    def _create_ui(self):
        """Create UI elements."""
        picker_rect = Rect(0, TOOLBAR_HEIGHT, PICKER_WIDTH, self.screen_height - TOOLBAR_HEIGHT - STATUS_HEIGHT)
        self.terrain_picker = TilePicker(self.terrain_tileset, picker_rect)
        self.greens_picker = GreensTilePicker(self.greens_tileset, picker_rect)

        # Toolbar buttons
        self.buttons = []
        x = 10

        btn_load = Button(Rect(x, 5, 60, 30), "Load", self._on_load)
        self.buttons.append(btn_load)
        x += 70

        btn_save = Button(Rect(x, 5, 60, 30), "Save", self._on_save)
        self.buttons.append(btn_save)
        x += 80

        self.btn_terrain = Button(Rect(x, 5, 70, 30), "Terrain", lambda: self._set_mode("terrain"))
        self.buttons.append(self.btn_terrain)
        x += 80

        self.btn_palette = Button(Rect(x, 5, 70, 30), "Palette", lambda: self._set_mode("palette"))
        self.buttons.append(self.btn_palette)
        x += 80

        self.btn_greens = Button(Rect(x, 5, 70, 30), "Greens", lambda: self._set_mode("greens"))
        self.buttons.append(self.btn_greens)
        x += 90

        btn_grid = Button(Rect(x, 5, 50, 30), "Grid", self.state.toggle_grid)
        self.buttons.append(btn_grid)
        x += 60

        btn_add_row = Button(Rect(x, 5, 70, 30), "+Row", lambda: self.hole_data.add_terrain_row(False))
        self.buttons.append(btn_add_row)
        x += 80

        btn_del_row = Button(Rect(x, 5, 70, 30), "-Row", lambda: self.hole_data.remove_terrain_row(False))
        self.buttons.append(btn_del_row)
        x += 100

        # Flag position buttons
        self.flag_buttons = []
        for i in range(4):
            btn = Button(
                Rect(x + (i * 35), 5, 30, 30),
                f"F{i+1}",
                lambda idx=i: self._select_flag(idx)
            )
            self.buttons.append(btn)
            self.flag_buttons.append(btn)

        x += 150

        # Sprite toggle
        self.btn_sprites = Button(Rect(x, 5, 70, 30), "Sprites", self.state.toggle_sprites)
        self.buttons.append(self.btn_sprites)

        self._update_mode_buttons()

    def _set_mode(self, mode: str):
        """Set editing mode."""
        self.state.set_mode(mode)
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        """Update mode button active states."""
        self.btn_terrain.active = (self.state.mode == "terrain")
        self.btn_palette.active = (self.state.mode == "palette")
        self.btn_greens.active = (self.state.mode == "greens")
        self._update_flag_buttons()

    def _select_flag(self, index: int):
        """Select which flag position to display."""
        self.state.select_flag(index)
        self._update_flag_buttons()

    def _update_flag_buttons(self):
        """Update flag button active states."""
        for i, btn in enumerate(self.flag_buttons):
            btn.active = (i == self.state.selected_flag_index)

    def _on_load(self):
        """Load a hole file."""
        path = open_file_dialog(
            "Load Hole",
            [("JSON files", "*.json"), ("All files", "*.*")]
        )
        if path:
            self.hole_data.load(path)
            self.state.reset_canvas_position()

    def _on_save(self):
        """Save the current hole."""
        if self.hole_data.filepath:
            self.hole_data.save()
        else:
            path = save_file_dialog(
                "Save Hole",
                ".json",
                [("JSON files", "*.json"), ("All files", "*.*")]
            )
            if path:
                self.hole_data.save(path)

    def _on_resize(self, width: int, height: int):
        """Handle window resize."""
        self.screen_width = width
        self.screen_height = height
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height), pygame.RESIZABLE)
        self._create_ui()
        self.event_handler.update_screen_size(width, height)

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

    def run(self):
        """Main loop."""
        while self.running:
            events = pygame.event.get()
            self.running = self.event_handler.handle_events(events)
            self._render()
            self.clock.tick(60)

        pygame.quit()

    def _render(self):
        """Render the editor."""
        self.screen.fill(COLOR_BG)

        # Toolbar
        self._render_toolbar()

        # Tile picker
        if self.state.mode == "greens":
            self.greens_picker.render(self.screen)
        else:
            palette_for_picker = self.state.selected_palette if self.state.mode == "palette" else 1
            self.terrain_picker.render(self.screen, palette_for_picker)

        # Canvas
        self._render_canvas()

        # Status bar
        self._render_status()

        pygame.display.flip()

    def _render_toolbar(self):
        """Render toolbar with buttons and palette selector."""
        pygame.draw.rect(self.screen, COLOR_TOOLBAR, (0, 0, self.screen_width, TOOLBAR_HEIGHT))
        for button in self.buttons:
            button.render(self.screen, self.font)

        # Palette selector in toolbar (for palette mode)
        if self.state.mode == "palette":
            x = 900
            text = self.font.render("Palette:", True, COLOR_TEXT)
            self.screen.blit(text, (x, 12))
            x += 70
            for i in range(1, 4):
                rect = Rect(x, 8, 24, 24)
                pygame.draw.rect(self.screen, PALETTES[i][3], rect)
                pygame.draw.rect(self.screen, COLOR_SELECTION if self.state.selected_palette == i else COLOR_GRID, rect, 2)
                num = self.font_small.render(str(i), True, COLOR_TEXT)
                self.screen.blit(num, (x + 8, 12))
                x += 30

    def _render_canvas(self):
        """Render the main editing canvas."""
        canvas_rect = self._get_canvas_rect()
        pygame.draw.rect(self.screen, (0, 0, 0), canvas_rect)

        if not self.hole_data.terrain:
            text = self.font.render("No hole loaded. Press Ctrl+O to open.", True, COLOR_TEXT)
            self.screen.blit(text, (canvas_rect.centerx - text.get_width() // 2, canvas_rect.centery))
            return

        if self.state.mode == "greens":
            GreensRenderer.render(
                self.screen,
                canvas_rect,
                self.hole_data,
                self.greens_tileset,
                self.sprites,
                self.state.canvas_offset_x,
                self.state.canvas_offset_y,
                self.state.canvas_scale,
                self.state.show_grid,
                self.state.show_sprites,
                self.state.selected_flag_index,
            )
        else:
            TerrainRenderer.render(
                self.screen,
                canvas_rect,
                self.hole_data,
                self.terrain_tileset,
                self.sprites,
                self.state.canvas_offset_x,
                self.state.canvas_offset_y,
                self.state.canvas_scale,
                self.state.show_grid,
                self.state.show_sprites,
                self.state.selected_flag_index,
            )

    def _render_status(self):
        """Render status bar."""
        status_rect = Rect(0, self.screen_height - STATUS_HEIGHT, self.screen_width, STATUS_HEIGHT)
        pygame.draw.rect(self.screen, COLOR_STATUS, status_rect)

        # Mouse position
        mouse_pos = pygame.mouse.get_pos()
        tile = self._screen_to_tile(mouse_pos)

        status_parts = [f"Mode: {self.state.mode.title()}"]

        if self.state.mode == "terrain":
            status_parts.append(f"Sprites: {'ON' if self.state.show_sprites else 'OFF'}")
            if self.state.show_sprites and self.hole_data.metadata:
                status_parts.append(f"Flag: {self.state.selected_flag_index + 1}/4")

        if tile:
            row, col = tile
            status_parts.append(f"Tile: ({col}, {row})")

            if self.state.mode == "terrain" and 0 <= row < len(self.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                tile_val = self.hole_data.terrain[row][col]
                attr_val = self.hole_data.get_attribute(row, col)
                status_parts.append(f"Value: ${tile_val:02X}")
                status_parts.append(f"Palette: {attr_val}")

            elif self.state.mode == "greens" and 0 <= row < len(self.hole_data.greens) and 0 <= col < GREENS_WIDTH:
                tile_val = self.hole_data.greens[row][col]
                status_parts.append(f"Value: ${tile_val:02X}")

        if self.hole_data.filepath:
            name = Path(self.hole_data.filepath).name
            modified = "*" if self.hole_data.modified else ""
            status_parts.append(f"File: {name}{modified}")

        status_text = "  |  ".join(status_parts)
        text_surf = self.font.render(status_text, True, COLOR_TEXT)
        self.screen.blit(text_surf, (10, self.screen_height - STATUS_HEIGHT + 8))

    def load_hole(self, path: str):
        """Load a hole from file path."""
        self.hole_data.load(path)
        self.state.reset_canvas_position()
