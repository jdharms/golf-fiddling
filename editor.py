#!/usr/bin/env python3
"""
NES Open Tournament Golf - Course Editor

A Pygame-based editor for modifying course terrain, attributes, and greens.
"""

import compact_json as json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import pygame
from pygame import Surface, Rect

# Constants
TILE_SIZE = 8
BYTES_PER_TILE = 16
TERRAIN_WIDTH = 22
GREENS_WIDTH = 24
GREENS_HEIGHT = 24

# UI Layout
PICKER_WIDTH = 200
TOOLBAR_HEIGHT = 40
STATUS_HEIGHT = 30
CANVAS_OFFSET_X = PICKER_WIDTH
CANVAS_OFFSET_Y = TOOLBAR_HEIGHT

# Colors
COLOR_BG = (48, 48, 48)
COLOR_TOOLBAR = (32, 32, 32)
COLOR_STATUS = (32, 32, 32)
COLOR_PICKER_BG = (40, 40, 40)
COLOR_GRID = (80, 80, 80)
COLOR_GRID_SUPER = (120, 120, 120)
COLOR_SELECTION = (255, 255, 0)
COLOR_TEXT = (255, 255, 255)
COLOR_BUTTON = (64, 64, 64)
COLOR_BUTTON_HOVER = (80, 80, 80)
COLOR_BUTTON_ACTIVE = (100, 100, 200)

# Palettes (RGB tuples)
PALETTES = [
    [(0, 0, 0), (12, 147, 0), (255, 255, 255), (100, 176, 255)],  # 0: HUD (unused)
    [(0, 0, 0), (12, 147, 0), (0, 82, 0), (92, 228, 48)],         # 1: Fairway/Rough
    [(0, 0, 0), (12, 147, 0), (0, 82, 0), (188, 190, 0)],         # 2: Bunker
    [(0, 0, 0), (12, 147, 0), (0, 82, 0), (100, 176, 255)],       # 3: Water
]

# Greens palette (single palette for greens view)
GREENS_PALETTE = [(0, 0, 0), (12, 147, 0), (0, 82, 0), (92, 228, 48)]
GREENS_PALETTE_NUM = 4  # arbitrary

# Putting green overlay color
GREEN_OVERLAY_COLOR = (0, 82, 0)

# NES sprite coordinate offsets
SPRITE_OFFSET_Y = +1  # Scanline delay


class Tileset:
    """Loads and renders NES CHR tile data."""

    def __init__(self, chr_path: str):
        with open(chr_path, 'rb') as f:
            self.data = f.read()

        self.num_tiles = len(self.data) // BYTES_PER_TILE
        self._cache: Dict[Tuple[int, int, int], Surface] = {}

    def decode_tile(self, tile_idx: int) -> List[List[int]]:
        """Decode a single 8x8 tile into 2-bit pixel values."""
        if tile_idx >= self.num_tiles:
            return [[0] * 8 for _ in range(8)]

        offset = tile_idx * BYTES_PER_TILE
        plane0 = self.data[offset:offset + 8]
        plane1 = self.data[offset + 8:offset + 16]

        pixels = []
        for row in range(8):
            row_pixels = []
            for col in range(8):
                bit_mask = 0x80 >> col
                low_bit = 1 if (plane0[row] & bit_mask) else 0
                high_bit = 1 if (plane1[row] & bit_mask) else 0
                pixel = low_bit | (high_bit << 1)
                row_pixels.append(pixel)
            pixels.append(row_pixels)

        return pixels

    def render_tile(self, tile_idx: int, palette_idx: int, scale: int = 1) -> Surface:
        """Render a tile to a Pygame surface with given palette."""
        cache_key = (tile_idx, palette_idx, scale)
        if cache_key in self._cache:
            return self._cache[cache_key]

        palette = PALETTES[palette_idx] if palette_idx < len(PALETTES) else PALETTES[1]
        pixels = self.decode_tile(tile_idx)

        surf = Surface((TILE_SIZE * scale, TILE_SIZE * scale))
        for y in range(8):
            for x in range(8):
                color = palette[pixels[y][x]]
                if scale == 1:
                    surf.set_at((x, y), color)
                else:
                    pygame.draw.rect(surf, color, (x * scale, y * scale, scale, scale))

        self._cache[cache_key] = surf
        return surf

    def render_tile_greens(self, tile_idx: int, scale: int = 1) -> Surface:
        """Render a tile using the greens palette."""
        cache_key = (tile_idx, GREENS_PALETTE_NUM, scale)
        if cache_key in self._cache:
            return self._cache[cache_key]

        pixels = self.decode_tile(tile_idx)

        surf = Surface((TILE_SIZE * scale, TILE_SIZE * scale))
        for y in range(8):
            for x in range(8):
                color = GREENS_PALETTE[pixels[y][x]]
                if scale == 1:
                    surf.set_at((x, y), color)
                else:
                    pygame.draw.rect(surf, color, (x * scale, y * scale, scale, scale))

        self._cache[cache_key] = surf
        return surf


class Sprite:
    """Loads and renders a sprite from JSON file with embedded CHR data."""

    def __init__(self, json_path: str):
        with open(json_path, 'r') as f:
            data = json.load(f)

        self.name = data.get("name", "unknown")

        # Parse hex tile data
        self.tiles = []
        for tile_str in data.get("tiles", []):
            tile_bytes = bytes.fromhex(tile_str.replace(" ", ""))
            self.tiles.append(tile_bytes)

        # Parse palette (convert hex colors to RGB tuples)
        palette_hex = data.get("palette", ["#000000"] * 4)
        self.palette = []
        for hex_color in palette_hex:
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            self.palette.append((r, g, b))

        # Parse sprite entries (OAM-style: tile index + offsets)
        self.sprites = data.get("sprites", [{"tile": 0, "x": 0, "y": 0}])

        self._cache: Dict[Tuple[int, int], Surface] = {}

    def decode_tile(self, tile_idx: int) -> List[List[int]]:
        """Decode a single 8x8 tile into 2-bit pixel values."""
        if tile_idx >= len(self.tiles):
            return [[0] * 8 for _ in range(8)]

        tile_data = self.tiles[tile_idx]
        plane0 = tile_data[0:8]
        plane1 = tile_data[8:16]

        pixels = []
        for row in range(8):
            row_pixels = []
            for col in range(8):
                bit_mask = 0x80 >> col
                low_bit = 1 if (plane0[row] & bit_mask) else 0
                high_bit = 1 if (plane1[row] & bit_mask) else 0
                pixel = low_bit | (high_bit << 1)
                row_pixels.append(pixel)
            pixels.append(row_pixels)

        return pixels

    def render_tile(self, tile_idx: int, scale: int = 1) -> Surface:
        """Render a sprite tile to a Pygame surface."""
        cache_key = (tile_idx, scale)
        if cache_key in self._cache:
            return self._cache[cache_key]

        pixels = self.decode_tile(tile_idx)

        surf = Surface((TILE_SIZE * scale, TILE_SIZE * scale))
        surf.set_colorkey((0, 0, 0))  # Make color 0 (black) transparent

        for y in range(8):
            for x in range(8):
                color_idx = pixels[y][x]
                if color_idx > 0:  # Skip transparent pixels
                    color = self.palette[color_idx]
                    if scale == 1:
                        surf.set_at((x, y), color)
                    else:
                        pygame.draw.rect(surf, color, (x * scale, y * scale, scale, scale))

        self._cache[cache_key] = surf
        return surf

    def render(self, screen: Surface, x: int, y: int, scale: int = 1):
        """Render all sprite entries at given positions."""
        for sprite_entry in self.sprites:
            tile_idx = sprite_entry.get("tile", 0)
            offset_x = sprite_entry.get("x", 0)
            offset_y = sprite_entry.get("y", 0)

            offset_y += SPRITE_OFFSET_Y

            sx = x + offset_x * scale
            sy = y + offset_y * scale

            tile_surf = self.render_tile(tile_idx, scale)
            screen.blit(tile_surf, (sx, sy))


class HoleData:
    """Manages hole data including terrain, attributes, and greens."""

    def __init__(self):
        self.terrain: List[List[int]] = []
        self.attributes: List[List[int]] = []
        self.greens: List[List[int]] = []
        self.green_x: int = 0
        self.green_y: int = 0
        self.metadata: Dict[str, Any] = {}
        self.filepath: Optional[str] = None
        self.modified: bool = False

    def load(self, path: str):
        """Load hole data from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)

        # Parse terrain
        self.terrain = []
        for row_str in data["terrain"]["rows"]:
            row = [int(x, 16) for x in row_str.split()]
            self.terrain.append(row)

        # Parse attributes
        self.attributes = data["attributes"]["rows"]

        # Parse greens
        self.greens = []
        for row_str in data["greens"]["rows"]:
            row = [int(x, 16) for x in row_str.split()]
            self.greens.append(row)

        # Green position
        self.green_x = data["green"]["x"]
        self.green_y = data["green"]["y"]

        # Store other metadata
        self.metadata = {
            "hole": data.get("hole", 1),
            "par": data.get("par", 4),
            "distance": data.get("distance", 400),
            "handicap": data.get("handicap", 1),
            "scroll_limit": data.get("scroll_limit", 32),
            "tee": data.get("tee", {"x": 0, "y": 0}),
            "flag_positions": data.get("flag_positions", []),
            "_debug": data.get("_debug", {}),
        }

        self.filepath = path
        self.modified = False

    def save(self, path: Optional[str] = None):
        """Save hole data to JSON file."""
        if path is None:
            path = self.filepath
        if path is None:
            raise ValueError("No save path specified")

        # Convert terrain to hex strings
        terrain_rows = []
        for row in self.terrain:
            row_str = ' '.join(f'{b:02X}' for b in row)
            terrain_rows.append(row_str)

        # Convert greens to hex strings
        greens_rows = []
        for row in self.greens:
            row_str = ' '.join(f'{b:02X}' for b in row)
            greens_rows.append(row_str)

        data = {
            "hole": self.metadata.get("hole", 1),
            "par": self.metadata.get("par", 4),
            "distance": self.metadata.get("distance", 400),
            "handicap": self.metadata.get("handicap", 1),
            "scroll_limit": self.metadata.get("scroll_limit", 32),
            "green": {"x": self.green_x, "y": self.green_y},
            "tee": self.metadata.get("tee", {"x": 0, "y": 0}),
            "flag_positions": self.metadata.get("flag_positions", []),
            "terrain": {
                "width": TERRAIN_WIDTH,
                "height": len(self.terrain),
                "rows": terrain_rows,
            },
            "attributes": {
                "width": len(self.attributes[0]) if self.attributes else 11,
                "height": len(self.attributes),
                "rows": self.attributes,
            },
            "greens": {
                "width": GREENS_WIDTH,
                "height": len(self.greens),
                "rows": greens_rows,
            },
            "_debug": self.metadata.get("_debug", {}),
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

        self.filepath = path
        self.modified = False

    def get_terrain_height(self) -> int:
        return len(self.terrain)

    def get_attribute(self, tile_row: int, tile_col: int) -> int:
        """Get palette index for a terrain tile position."""
        attr_row = tile_row // 2
        attr_col = tile_col // 2
        if 0 <= attr_row < len(self.attributes) and 0 <= attr_col < len(self.attributes[attr_row]):
            return self.attributes[attr_row][attr_col]
        return 1

    def set_attribute(self, super_row: int, super_col: int, palette: int):
        """Set palette index for a supertile position."""
        if 0 <= super_row < len(self.attributes) and 0 <= super_col < len(self.attributes[super_row]):
            self.attributes[super_row][super_col] = palette
            self.modified = True

    def set_terrain_tile(self, row: int, col: int, tile_idx: int):
        """Set a terrain tile."""
        if 0 <= row < len(self.terrain) and 0 <= col < len(self.terrain[row]):
            self.terrain[row][col] = tile_idx
            self.modified = True

    def set_greens_tile(self, row: int, col: int, tile_idx: int):
        """Set a greens tile."""
        if 0 <= row < len(self.greens) and 0 <= col < len(self.greens[row]):
            self.greens[row][col] = tile_idx
            self.modified = True

    def add_terrain_row(self, at_top: bool = False):
        """Add a row of default terrain."""
        new_row = [0xDF] * TERRAIN_WIDTH  # Default to deep rough
        if at_top:
            self.terrain.insert(0, new_row)
        else:
            self.terrain.append(new_row)

        # Add attribute row if needed
        if len(self.terrain) // 2 > len(self.attributes):
            new_attr_row = [1] * 11  # Default to fairway palette
            if at_top:
                self.attributes.insert(0, new_attr_row)
            else:
                self.attributes.append(new_attr_row)

        self.modified = True

    def remove_terrain_row(self, from_top: bool = False):
        """Remove a row of terrain."""
        if len(self.terrain) <= 1:
            return

        if from_top:
            self.terrain.pop(0)
        else:
            self.terrain.pop()

        # Remove attribute row if needed
        expected_attr_rows = (len(self.terrain) + 1) // 2
        while len(self.attributes) > expected_attr_rows:
            if from_top:
                self.attributes.pop(0)
            else:
                self.attributes.pop()

        self.modified = True


class TilePicker:
    """Tile selection panel."""

    def __init__(self, tileset: Tileset, rect: Rect):
        self.tileset = tileset
        self.rect = rect
        self.scroll_y = 0
        self.selected_tile = 0x25  # Default to rough
        self.tiles_per_row = (rect.width - 20) // (TILE_SIZE * 2 + 2)
        self.tile_scale = 2
        self.tile_spacing = 2

        # Build list of tile indices to show (skip empty tiles at start)
        self.tile_indices = list(range(0x25, 0xE0))

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if handled."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if event.button == 1:  # Left click
                    self._select_at(event.pos)
                    return True
                elif event.button == 4:  # Scroll up
                    self.scroll_y = max(0, self.scroll_y - 20)
                    return True
                elif event.button == 5:  # Scroll down
                    self.scroll_y += 20
                    return True
        return False

    def _select_at(self, pos: Tuple[int, int]):
        """Select tile at screen position."""
        local_x = pos[0] - self.rect.x - 10
        local_y = pos[1] - self.rect.y - 10 + self.scroll_y

        tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing
        col = local_x // tile_size
        row = local_y // tile_size

        idx = row * self.tiles_per_row + col
        if 0 <= idx < len(self.tile_indices):
            self.selected_tile = self.tile_indices[idx]

    def render(self, screen: Surface, palette_idx: int = 1):
        """Render the tile picker."""
        # Background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        # Create clipping rect
        clip_rect = self.rect.copy()
        clip_rect.y += 5
        clip_rect.height -= 10

        tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing

        for i, tile_idx in enumerate(self.tile_indices):
            col = i % self.tiles_per_row
            row = i // self.tiles_per_row

            x = self.rect.x + 10 + col * tile_size
            y = self.rect.y + 10 + row * tile_size - self.scroll_y

            # Skip if outside visible area
            if y + tile_size < clip_rect.y or y > clip_rect.bottom:
                continue

            # Render tile
            tile_surf = self.tileset.render_tile(tile_idx, palette_idx, self.tile_scale)
            screen.blit(tile_surf, (x, y))

            # Selection highlight
            if tile_idx == self.selected_tile:
                pygame.draw.rect(screen, COLOR_SELECTION,
                               (x - 1, y - 1, TILE_SIZE * self.tile_scale + 2, TILE_SIZE * self.tile_scale + 2), 2)


class GreensTilePicker(TilePicker):
    """Tile picker for greens editing."""

    def __init__(self, tileset: Tileset, rect: Rect):
        super().__init__(tileset, rect)
        # Greens use different tile range
        self.tile_indices = list(range(0x00, 0x9f))
        self.selected_tile = 0x30

    def render(self, screen: Surface, palette_idx: int = 1):
        """Render the tile picker with greens palette."""
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing

        for i, tile_idx in enumerate(self.tile_indices):
            col = i % self.tiles_per_row
            row = i // self.tiles_per_row

            x = self.rect.x + 10 + col * tile_size
            y = self.rect.y + 10 + row * tile_size - self.scroll_y

            if y + tile_size < self.rect.y or y > self.rect.bottom:
                continue

            tile_surf = self.tileset.render_tile_greens(tile_idx, self.tile_scale)
            screen.blit(tile_surf, (x, y))

            if tile_idx == self.selected_tile:
                pygame.draw.rect(screen, COLOR_SELECTION,
                               (x - 1, y - 1, TILE_SIZE * self.tile_scale + 2, TILE_SIZE * self.tile_scale + 2), 2)


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


class Editor:
    """Main editor application."""

    def __init__(self, terrain_chr: str, greens_chr: str):
        pygame.init()

        self.screen_width = 1200
        self.screen_height = 800
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height), pygame.RESIZABLE)
        pygame.display.set_caption("NES Open Golf Course Editor")

        self.font = pygame.font.SysFont("monospace", 14)
        self.font_small = pygame.font.SysFont("monospace", 12)

        # Load tilesets
        self.terrain_tileset = Tileset(terrain_chr)
        self.greens_tileset = Tileset(greens_chr)

        # Load sprites
        self.sprites = {}
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

        # Editor state
        self.hole_data = HoleData()
        self.mode = "terrain"  # "terrain", "palette", or "greens"
        self.show_grid = True
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
        self.canvas_scale = 2

        # Selected palette for palette mode
        self.selected_palette = 1

        # Sprite rendering state
        self.show_sprites = True
        self.selected_flag_index = 0  # Which of 4 flag positions (0-3)

        # Mouse state
        self.mouse_down = False
        self.last_paint_pos = None

        # Create UI elements
        self._create_ui()

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

        btn_grid = Button(Rect(x, 5, 50, 30), "Grid", self._toggle_grid)
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
        self.btn_sprites = Button(Rect(x, 5, 70, 30), "Sprites", self._toggle_sprites)
        self.buttons.append(self.btn_sprites)

        self._update_mode_buttons()

    def _set_mode(self, mode: str):
        self.mode = mode
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        self.btn_terrain.active = (self.mode == "terrain")
        self.btn_palette.active = (self.mode == "palette")
        self.btn_greens.active = (self.mode == "greens")
        self._update_flag_buttons()

    def _toggle_grid(self):
        self.show_grid = not self.show_grid

    def _select_flag(self, index: int):
        """Select which flag position to display."""
        self.selected_flag_index = index
        self._update_flag_buttons()

    def _toggle_sprites(self):
        """Toggle sprite rendering."""
        self.show_sprites = not self.show_sprites
        self.btn_sprites.active = self.show_sprites

    def _update_flag_buttons(self):
        """Update flag button active states."""
        for i, btn in enumerate(self.flag_buttons):
            btn.active = (i == self.selected_flag_index)

    def _on_load(self):
        """Load a hole file."""
        # Simple file dialog using tkinter
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            path = filedialog.askopenfilename(
                title="Load Hole",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            root.destroy()
            if path:
                self.hole_data.load(path)
                self.canvas_offset_x = 0
                self.canvas_offset_y = 0
        except ImportError:
            print("tkinter not available for file dialog")

    def _on_save(self):
        """Save the current hole."""
        if self.hole_data.filepath:
            self.hole_data.save()
        else:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                path = filedialog.asksaveasfilename(
                    title="Save Hole",
                    defaultextension=".json",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
                )
                root.destroy()
                if path:
                    self.hole_data.save(path)
            except ImportError:
                print("tkinter not available for file dialog")

    def _get_canvas_rect(self) -> Rect:
        """Get the canvas drawing area."""
        return Rect(CANVAS_OFFSET_X, CANVAS_OFFSET_Y,
                   self.screen_width - CANVAS_OFFSET_X,
                   self.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT)

    def _screen_to_tile(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Convert screen position to tile coordinates."""
        canvas_rect = self._get_canvas_rect()
        if not canvas_rect.collidepoint(screen_pos):
            return None

        local_x = screen_pos[0] - canvas_rect.x + self.canvas_offset_x
        local_y = screen_pos[1] - canvas_rect.y + self.canvas_offset_y

        tile_size = TILE_SIZE * self.canvas_scale
        tile_col = local_x // tile_size
        tile_row = local_y // tile_size

        return (tile_row, tile_col)

    def _screen_to_supertile(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Convert screen position to supertile (2x2) coordinates."""
        tile = self._screen_to_tile(screen_pos)
        if tile is None:
            return None
        return (tile[0] // 2, tile[1] // 2)

    def handle_events(self):
        """Handle pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            if event.type == pygame.KEYDOWN:
                self._handle_key(event)

            # Handle button events
            for button in self.buttons:
                button.handle_event(event)

            # Handle picker events
            if self.mode == "greens":
                self.greens_picker.handle_event(event)
            else:
                self.terrain_picker.handle_event(event)

            # Handle canvas events
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.mouse_down = True
                    self._paint_at(event.pos)
                elif event.button == 3:  # Right click - eyedropper
                    self._eyedropper(event.pos)
                elif event.button == 4:  # Scroll up
                    self.canvas_offset_y = max(0, self.canvas_offset_y - 20)
                elif event.button == 5:  # Scroll down
                    self.canvas_offset_y += 20

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.mouse_down = False
                    self.last_paint_pos = None

            elif event.type == pygame.MOUSEMOTION:
                if self.mouse_down:
                    self._paint_at(event.pos)

            elif event.type == pygame.VIDEORESIZE:
                self.screen_width = event.w
                self.screen_height = event.h
                self.screen = pygame.display.set_mode((self.screen_width, self.screen_height), pygame.RESIZABLE)
                self._create_ui()

    def _handle_key(self, event):
        """Handle keyboard input."""
        if event.key == pygame.K_g:
            self._toggle_grid()
        elif event.key == pygame.K_1:
            self.selected_palette = 1
        elif event.key == pygame.K_2:
            self.selected_palette = 2
        elif event.key == pygame.K_3:
            self.selected_palette = 3
        elif event.key == pygame.K_TAB:
            # Cycle modes
            modes = ["terrain", "palette", "greens"]
            idx = modes.index(self.mode)
            self._set_mode(modes[(idx + 1) % len(modes)])
        elif event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self._on_save()
        elif event.key == pygame.K_o and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self._on_load()
        elif event.key == pygame.K_LEFT:
            self.canvas_offset_x = max(0, self.canvas_offset_x - 20)
        elif event.key == pygame.K_RIGHT:
            self.canvas_offset_x += 20
        elif event.key == pygame.K_UP:
            self.canvas_offset_y = max(0, self.canvas_offset_y - 20)
        elif event.key == pygame.K_DOWN:
            self.canvas_offset_y += 20
        elif event.key == pygame.K_LEFTBRACKET:  # [
            # Previous flag position
            if self.hole_data.metadata.get("flag_positions"):
                num_flags = len(self.hole_data.metadata["flag_positions"])
                self.selected_flag_index = (self.selected_flag_index - 1) % num_flags
                self._update_flag_buttons()
        elif event.key == pygame.K_RIGHTBRACKET:  # ]
            # Next flag position
            if self.hole_data.metadata.get("flag_positions"):
                num_flags = len(self.hole_data.metadata["flag_positions"])
                self.selected_flag_index = (self.selected_flag_index + 1) % num_flags
                self._update_flag_buttons()
        elif event.key == pygame.K_v:  # Toggle sprites (V for "view")
            self._toggle_sprites()

    def _paint_at(self, pos: Tuple[int, int]):
        """Paint at screen position based on current mode."""
        if self.mode == "terrain":
            tile = self._screen_to_tile(pos)
            if tile and tile != self.last_paint_pos:
                row, col = tile
                if 0 <= row < len(self.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                    self.hole_data.set_terrain_tile(row, col, self.terrain_picker.selected_tile)
                    self.last_paint_pos = tile

        elif self.mode == "palette":
            supertile = self._screen_to_supertile(pos)
            if supertile and supertile != self.last_paint_pos:
                row, col = supertile
                self.hole_data.set_attribute(row, col, self.selected_palette)
                self.last_paint_pos = supertile

        elif self.mode == "greens":
            tile = self._screen_to_tile(pos)
            if tile and tile != self.last_paint_pos:
                row, col = tile
                if 0 <= row < GREENS_HEIGHT and 0 <= col < GREENS_WIDTH:
                    self.hole_data.set_greens_tile(row, col, self.greens_picker.selected_tile)
                    self.last_paint_pos = tile

    def _eyedropper(self, pos: Tuple[int, int]):
        """Pick tile/palette from canvas."""
        if self.mode == "terrain":
            tile = self._screen_to_tile(pos)
            if tile:
                row, col = tile
                if 0 <= row < len(self.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                    self.terrain_picker.selected_tile = self.hole_data.terrain[row][col]

        elif self.mode == "palette":
            supertile = self._screen_to_supertile(pos)
            if supertile:
                row, col = supertile
                if 0 <= row < len(self.hole_data.attributes) and 0 <= col < len(self.hole_data.attributes[row]):
                    self.selected_palette = self.hole_data.attributes[row][col]

        elif self.mode == "greens":
            tile = self._screen_to_tile(pos)
            if tile:
                row, col = tile
                if 0 <= row < len(self.hole_data.greens) and 0 <= col < GREENS_WIDTH:
                    self.greens_picker.selected_tile = self.hole_data.greens[row][col]

    def render(self):
        """Render the editor."""
        self.screen.fill(COLOR_BG)

        # Toolbar
        pygame.draw.rect(self.screen, COLOR_TOOLBAR, (0, 0, self.screen_width, TOOLBAR_HEIGHT))
        for button in self.buttons:
            button.render(self.screen, self.font)

        # Palette selector in toolbar (for palette mode)
        if self.mode == "palette":
            x = 700
            text = self.font.render("Palette:", True, COLOR_TEXT)
            self.screen.blit(text, (x, 12))
            x += 70
            for i in range(1, 4):
                color = COLOR_BUTTON_ACTIVE if self.selected_palette == i else COLOR_BUTTON
                rect = Rect(x, 8, 24, 24)
                pygame.draw.rect(self.screen, PALETTES[i][3], rect)
                pygame.draw.rect(self.screen, COLOR_SELECTION if self.selected_palette == i else COLOR_GRID, rect, 2)
                num = self.font_small.render(str(i), True, COLOR_TEXT)
                self.screen.blit(num, (x + 8, 12))
                x += 30

        # Tile picker
        if self.mode == "greens":
            self.greens_picker.render(self.screen)
        else:
            palette_for_picker = self.selected_palette if self.mode == "palette" else 1
            self.terrain_picker.render(self.screen, palette_for_picker)

        # Canvas
        self._render_canvas()

        # Status bar
        self._render_status()

        pygame.display.flip()

    def _render_canvas(self):
        """Render the main editing canvas."""
        canvas_rect = self._get_canvas_rect()
        pygame.draw.rect(self.screen, (0, 0, 0), canvas_rect)

        if not self.hole_data.terrain:
            text = self.font.render("No hole loaded. Press Ctrl+O to open.", True, COLOR_TEXT)
            self.screen.blit(text, (canvas_rect.centerx - text.get_width() // 2, canvas_rect.centery))
            return

        tile_size = TILE_SIZE * self.canvas_scale

        if self.mode == "greens":
            self._render_greens_canvas(canvas_rect, tile_size)
        else:
            self._render_terrain_canvas(canvas_rect, tile_size)

    def _render_terrain_canvas(self, canvas_rect: Rect, tile_size: int):
        """Render terrain view."""
        # Render terrain tiles
        for row_idx, row in enumerate(self.hole_data.terrain):
            for col_idx, tile_idx in enumerate(row):
                x = canvas_rect.x + col_idx * tile_size - self.canvas_offset_x
                y = canvas_rect.y + row_idx * tile_size - self.canvas_offset_y

                if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                    continue
                if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                    continue

                palette_idx = self.hole_data.get_attribute(row_idx, col_idx)
                tile_surf = self.terrain_tileset.render_tile(tile_idx, palette_idx, self.canvas_scale)
                self.screen.blit(tile_surf, (x, y))

        # Render green overlay
        self._render_green_overlay(canvas_rect, tile_size)

        # Render sprites
        self._render_terrain_sprites(canvas_rect)

        # Render grid
        if self.show_grid:
            self._render_grid(canvas_rect, tile_size)

    def _render_green_overlay(self, canvas_rect: Rect, tile_size: int):
        """Render the putting green overlay on terrain view."""
        if not self.hole_data.greens:
            return

        green_x = self.hole_data.green_x
        green_y = self.hole_data.green_y

        for gy, grow in enumerate(self.hole_data.greens):
            for gx, gval in enumerate(grow):
                if gval >= 0x30:
                    # Calculate pixel position
                    px = green_x + gx
                    py = green_y + gy

                    # Convert to screen coords
                    screen_x = canvas_rect.x + px * self.canvas_scale - self.canvas_offset_x
                    screen_y = canvas_rect.y + py * self.canvas_scale - self.canvas_offset_y

                    if canvas_rect.collidepoint(screen_x, screen_y):
                        pygame.draw.rect(self.screen, GREEN_OVERLAY_COLOR,
                                       (screen_x, screen_y, self.canvas_scale, self.canvas_scale))

    def _render_greens_sprites(self, canvas_rect: Rect):
        """Render flag and cup on greens detail view"""
        if not self.show_sprites or self.mode != "greens":
            return

        if not self.sprites.get("green-cup") or not self.sprites.get("green-flag"):
            return

        flag_positions = self.hole_data.metadata.get("flag_positions", [])
        if not flag_positions or not (0 <= self.selected_flag_index <= len(flag_positions)):
            return

        flag_pos = flag_positions[self.selected_flag_index]

        flag_x = flag_pos.get("x_offset", 0)
        flag_y = flag_pos.get("y_offset", 0)

        screen_x = canvas_rect.x + flag_x * self.canvas_scale - self.canvas_offset_x
        screen_y = canvas_rect.y + flag_y * self.canvas_scale - self.canvas_offset_y

        self.sprites["green-flag"].render(self.screen, screen_x, screen_y, self.canvas_scale)
        self.sprites["green-cup"].render(self.screen, screen_x, screen_y, self.canvas_scale)

    def _render_terrain_sprites(self, canvas_rect: Rect):
        """Render flag, tee, and ball sprites on terrain view."""
        if not self.show_sprites:
            return

        if self.mode != "terrain":
            return

        if not self.hole_data.metadata:
            return

        def to_screen(px: int, py: int) -> Tuple[int, int]:
            """Convert game pixel coords to screen coords."""
            sx = canvas_rect.x + px * self.canvas_scale - self.canvas_offset_x
            sy = canvas_rect.y + py * self.canvas_scale - self.canvas_offset_y
            return sx, sy

        # Tee blocks
        if self.sprites.get("tee"):
            tee = self.hole_data.metadata.get("tee", {})
            tee_x = tee.get("x", 0)
            tee_y = tee.get("y", 0)
            sx, sy = to_screen(tee_x, tee_y)
            self.sprites["tee"].render(self.screen, sx, sy, self.canvas_scale)

        # Ball at tee
        if self.sprites.get("ball"):
            tee = self.hole_data.metadata.get("tee", {})
            tee_x = tee.get("x", 0)
            tee_y = tee.get("y", 0)

            sx, sy = to_screen(tee_x, tee_y)
            self.sprites["ball"].render(self.screen, sx, sy, self.canvas_scale)

        # Flag
        if self.sprites.get("flag"):
            flag_positions = self.hole_data.metadata.get("flag_positions", [])
            if flag_positions and 0 <= self.selected_flag_index < len(flag_positions):
                flag_pos = flag_positions[self.selected_flag_index]
                green_flag_x = flag_pos.get("x_offset", 0)
                green_flag_y = flag_pos.get("y_offset", 0)

                flag_x = self.hole_data.green_x + (green_flag_x // 8)
                flag_y = self.hole_data.green_y + (green_flag_y // 8)
                sx, sy = to_screen(flag_x, flag_y)
                self.sprites["flag"].render(self.screen, sx, sy, self.canvas_scale)

    def _render_greens_canvas(self, canvas_rect: Rect, tile_size: int):
        """Render greens editing view."""
        if not self.hole_data.greens:
            return

        for row_idx, row in enumerate(self.hole_data.greens):
            for col_idx, tile_idx in enumerate(row):
                x = canvas_rect.x + col_idx * tile_size - self.canvas_offset_x
                y = canvas_rect.y + row_idx * tile_size - self.canvas_offset_y

                if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                    continue
                if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                    continue

                tile_surf = self.greens_tileset.render_tile_greens(tile_idx, self.canvas_scale)
                self.screen.blit(tile_surf, (x, y))

        # Render flag-cup sprite
        self._render_greens_sprites(canvas_rect)

        if self.show_grid:
            self._render_grid(canvas_rect, tile_size, GREENS_WIDTH, GREENS_HEIGHT)

    def _render_grid(self, canvas_rect: Rect, tile_size: int,
                    width: int = TERRAIN_WIDTH, height: Optional[int] = None):
        """Render grid overlay."""
        if height is None:
            height = self.hole_data.get_terrain_height()

        # Tile grid
        for col in range(width + 1):
            x = canvas_rect.x + col * tile_size - self.canvas_offset_x
            if canvas_rect.x <= x <= canvas_rect.right:
                color = COLOR_GRID_SUPER if col % 2 == 0 else COLOR_GRID
                pygame.draw.line(self.screen, color, (x, canvas_rect.y), (x, canvas_rect.bottom))

        for row in range(height + 1):
            y = canvas_rect.y + row * tile_size - self.canvas_offset_y
            if canvas_rect.y <= y <= canvas_rect.bottom:
                color = COLOR_GRID_SUPER if row % 2 == 0 else COLOR_GRID
                pygame.draw.line(self.screen, color, (canvas_rect.x, y), (canvas_rect.right, y))

    def _render_status(self):
        """Render status bar."""
        status_rect = Rect(0, self.screen_height - STATUS_HEIGHT, self.screen_width, STATUS_HEIGHT)
        pygame.draw.rect(self.screen, COLOR_STATUS, status_rect)

        # Mouse position
        mouse_pos = pygame.mouse.get_pos()
        tile = self._screen_to_tile(mouse_pos)

        status_parts = [f"Mode: {self.mode.title()}"]

        if self.mode == "terrain":
            status_parts.append(f"Sprites: {'ON' if self.show_sprites else 'OFF'}")
            if self.show_sprites and self.hole_data.metadata:
                status_parts.append(f"Flag: {self.selected_flag_index + 1}/4")

        if tile:
            row, col = tile
            status_parts.append(f"Tile: ({col}, {row})")

            if self.mode == "terrain" and 0 <= row < len(self.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                tile_val = self.hole_data.terrain[row][col]
                attr_val = self.hole_data.get_attribute(row, col)
                status_parts.append(f"Value: ${tile_val:02X}")
                status_parts.append(f"Palette: {attr_val}")

            elif self.mode == "greens" and 0 <= row < len(self.hole_data.greens) and 0 <= col < GREENS_WIDTH:
                tile_val = self.hole_data.greens[row][col]
                status_parts.append(f"Value: ${tile_val:02X}")

        if self.hole_data.filepath:
            name = Path(self.hole_data.filepath).name
            modified = "*" if self.hole_data.modified else ""
            status_parts.append(f"File: {name}{modified}")

        status_text = "  |  ".join(status_parts)
        text_surf = self.font.render(status_text, True, COLOR_TEXT)
        self.screen.blit(text_surf, (10, self.screen_height - STATUS_HEIGHT + 8))

    def run(self):
        """Main loop."""
        while self.running:
            self.handle_events()
            self.render()
            self.clock.tick(60)

        pygame.quit()


def main():
    if len(sys.argv) < 3:
        print("Usage: python editor.py <terrain_chr.bin> <greens_chr.bin> [hole.json]")
        print("")
        print("Example:")
        print("  python editor.py chr-ram.bin greens-chr.bin")
        print("  python editor.py chr-ram.bin greens-chr.bin courses/japan/hole_01.json")
        sys.exit(1)

    terrain_chr = sys.argv[1]
    greens_chr = sys.argv[2]

    editor = Editor(terrain_chr, greens_chr)

    # Load initial hole if specified
    if len(sys.argv) > 3:
        editor.hole_data.load(sys.argv[3])

    editor.run()


if __name__ == "__main__":
    main()