"""
Greens-specific tile picker panel.
"""

import pygame
from pygame import Rect, Surface

from editor.core.constants import (
    COLOR_GRID,
    COLOR_PICKER_BG,
    COLOR_SELECTION,
    COLOR_TEXT,
    TILE_SIZE,
)

from .tile_banks import SimpleTileBank, _range_to_list
from .tile_picker import TilePicker


class GreensTilePicker(TilePicker):
    """Tile picker for greens editing."""

    def __init__(self, tileset, rect: Rect, on_hover_change=None):
        super().__init__(tileset, rect, on_hover_change)

        # Override banks with greens-specific tiles organized by type
        self.banks = [
            SimpleTileBank(
                "Rough",
                [0x29, 0x2C],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            SimpleTileBank(
                "Fringe",
                _range_to_list(0x48, 0x88),
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            SimpleTileBank(
                "Slopes",
                _range_to_list(0x30, 0x48) + _range_to_list(0x88, 0xA0),
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            SimpleTileBank(
                "Flat", [0xB0], self.tiles_per_row, self.tile_scale, self.tile_spacing
            ),
        ]
        self._calculate_bank_positions()

        self.selected_tile = 0x30

    def render(self, screen: Surface, palette_idx: int = 1):
        """Render the tile picker with greens palette."""
        # Background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        # Create clipping rect for scrolling
        clip_rect = self.rect.copy()
        clip_rect.y += 5
        clip_rect.height -= 10

        # Render each bank (greens-specific rendering)
        picker_width = self.rect.width - 20  # 10px margin on each side

        for i, bank in enumerate(self.banks):
            bank_y = self.rect.y + self._bank_positions[i] - self.scroll_y
            bank_x = self.rect.x + 10

            # Skip banks completely outside visible area
            bank_height = bank.get_height()
            if bank_y + bank_height < clip_rect.y or bank_y > clip_rect.bottom:
                continue

            # Draw label background
            label_rect = Rect(bank_x, bank_y, picker_width, bank.label_height)
            pygame.draw.rect(screen, COLOR_GRID, label_rect)

            # Render label text (centered)
            font = pygame.font.SysFont("monospace", 12)
            text_surf = font.render(bank.label, True, COLOR_TEXT)
            text_x = bank_x + (picker_width - text_surf.get_width()) // 2
            text_y = bank_y + (bank.label_height - text_surf.get_height()) // 2
            screen.blit(text_surf, (text_x, text_y))

            # Draw bank border
            border_rect = Rect(bank_x, bank_y, picker_width, bank_height)
            pygame.draw.rect(screen, COLOR_GRID, border_rect, bank.border_width)

            # Render tiles directly from SimpleTileBank
            tile_y_start = bank_y + bank.label_height + bank.padding
            tile_x_start = bank_x + bank.padding
            tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing

            for tile_i, tile_idx in enumerate(bank.tile_indices):
                col = tile_i % self.tiles_per_row
                row = tile_i // self.tiles_per_row

                tile_x = tile_x_start + col * tile_size
                tile_y = tile_y_start + row * tile_size

                # Skip if outside clip rect
                if tile_y + tile_size < clip_rect.y or tile_y > clip_rect.bottom:
                    continue

                # Render tile using greens palette
                tile_surf = self.tileset.render_tile_greens(tile_idx, self.tile_scale)
                screen.blit(tile_surf, (tile_x, tile_y))

                # Selection highlight
                if tile_idx == self.selected_tile:
                    pygame.draw.rect(
                        screen,
                        COLOR_SELECTION,
                        (
                            tile_x - 1,
                            tile_y - 1,
                            TILE_SIZE * self.tile_scale + 2,
                            TILE_SIZE * self.tile_scale + 2,
                        ),
                        2,
                    )
