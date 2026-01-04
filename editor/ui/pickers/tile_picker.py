"""
Main tile picker panel for terrain tile selection.
"""


import pygame
from pygame import Rect, Surface

from editor.core.constants import (
    COLOR_PICKER_BG,
    TILE_SIZE,
)
from editor.core.pygame_rendering import Tileset

from .tile_banks import GroupedTileBank, TileSubBank, _range_to_list


class TilePicker:
    """Tile selection panel."""

    def __init__(self, tileset: Tileset, rect: Rect, on_hover_change=None, on_tile_selected=None):
        self.tileset = tileset
        self.rect = rect
        self.scroll_y = 0
        self.selected_tile = 0x25  # Default to rough
        self.tile_scale = 4
        self.tiles_per_row = (rect.width - 20) // (TILE_SIZE * self.tile_scale + 2)

        self.tile_spacing = 2

        # Callback for hover changes
        self.on_hover_change = on_hover_change

        # Callback for tile selection (e.g., to auto-switch to paint tool)
        self.on_tile_selected = on_tile_selected

        # If Shift is pressed or released we want to know
        self.shift_held = False

        # Create banks with subbanks
        self.banks = [
            GroupedTileBank(
                "Meta",
                [TileSubBank("Placeholder", [0x100])],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            GroupedTileBank(
                "Fill",
                [
                    TileSubBank("Feature", [0x27]),
                    TileSubBank("Shallow Rough", [0x25]),
                    TileSubBank("Deep Rough", [0xDF]),
                ],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            GroupedTileBank(
                "Teebox",
                [
                    TileSubBank("Top", [0x36, 0x3C, 0x37, 0x39, 0x38]),
                    TileSubBank("Bottom", [0x3B, 0x35, 0x3A]),
                ],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            GroupedTileBank(
                "Rough",
                [
                    TileSubBank("Small Tree", [0x3E]),
                    TileSubBank("TreeTops", [0x9C, 0x9E]),
                    TileSubBank("TreeBases", [0x9D, 0x9F]),
                ],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            GroupedTileBank(
                "Features",
                [
                    TileSubBank("Borders With Depth", _range_to_list(0x40, 0x55)),
                    TileSubBank("Borders, Flat", _range_to_list(0x55, 0x80)),
                    TileSubBank("w/ Treetop", [0xBC, 0xBE]),
                    TileSubBank("w/ Treebase", [0xBD, 0xBF]),
                ],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            GroupedTileBank(
                "Out of bounds",
                [
                    TileSubBank("Border", _range_to_list(0x80, 0x9C)),
                    TileSubBank("Inner Border", [0x3F]),
                    TileSubBank("Forest fill", _range_to_list(0xA0, 0xA4)),
                    TileSubBank("Forest border", _range_to_list(0xA4, 0xBC)),
                ],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
        ]

        # Spacing between banks (vertical gap)
        self.bank_spacing = 8

        # Cached bank positions (y-offset for each bank)
        self._bank_positions = []
        self._calculate_bank_positions()

        # Track tile currently under mouse
        self.hovered_tile = None

    def _calculate_bank_positions(self):
        """Calculate y-offset for each bank (for layout and hit testing)."""
        self._bank_positions = []
        current_y = 10  # Top margin

        for bank in self.banks:
            self._bank_positions.append(current_y)
            current_y += bank.get_height() + self.bank_spacing

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if handled."""
        if event.type == pygame.MOUSEMOTION:
            # Update hovered tile (doesn't consume event)
            if self.rect.collidepoint(event.pos):
                new_hover = self._tile_at_position(event.pos)
            else:
                new_hover = None

            # Only notify if hover changed
            if new_hover != self.hovered_tile:
                self.hovered_tile = new_hover
                if self.on_hover_change and self.shift_held:
                    self.on_hover_change(new_hover)
            # Don't return True - let event propagate to buttons

        if event.type == pygame.KEYDOWN or event.type == pygame.KEYUP:
            shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT
            if not shift_held:
                # if we were holding shift previously
                if self.shift_held and self.on_hover_change:
                    self.shift_held = False
                    self.on_hover_change(None)
            else:
                # if we were not holding shift previously
                if not self.shift_held and self.on_hover_change:
                    self.shift_held = True
                    self.on_hover_change(self.hovered_tile)


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

    def _select_at(self, pos: tuple[int, int]):
        """Select tile at screen position."""
        tile = self._tile_at_position(pos)
        if tile is not None:
            self.selected_tile = tile
            # Notify callback (e.g., to auto-switch to paint tool)
            if self.on_tile_selected:
                self.on_tile_selected(tile)

    def _tile_at_position(self, pos: tuple[int, int]) -> int | None:
        """Get tile index at screen position, or None if invalid."""
        local_x = pos[0] - self.rect.x - 10
        local_y = pos[1] - self.rect.y + self.scroll_y

        # Find which bank we're in
        for bank_idx, bank in enumerate(self.banks):
            bank_y_start = self._bank_positions[bank_idx]
            bank_height = bank.get_height()
            bank_y_end = bank_y_start + bank_height

            if bank_y_start <= local_y < bank_y_end:
                # We're inside this bank
                # Check if we're in the bank label area
                if local_y < bank_y_start + bank.label_height:
                    return None  # Clicked on bank label

                # Position relative to bank's content area (after label + padding)
                bank_content_y = local_y - (
                    bank_y_start + bank.label_height + bank.padding
                )

                # Delegate to bank's hit detection method
                tile = bank.get_tile_at_position(
                    local_x - bank.padding,
                    bank_content_y,
                    self.tiles_per_row,
                    self.tile_scale,
                    self.tile_spacing,
                )
                if tile is not None:
                    return tile

        return None  # Outside all banks

    def get_hovered_tile(self) -> int | None:
        """Get the tile value currently under mouse, or None."""
        return self.hovered_tile

    def find_tile_position(self, tile_value: int) -> tuple[int, int, int] | None:
        """Find position of tile in bank hierarchy.

        Returns:
            (bank_idx, subbank_idx, position_in_subbank) or None if not found
        """
        for bank_idx, bank in enumerate(self.banks):
            for subbank_idx, subbank in enumerate(bank.subbanks):
                if tile_value in subbank.tile_indices:
                    position = subbank.tile_indices.index(tile_value)
                    return (bank_idx, subbank_idx, position)
        return None

    def get_next_tile_in_subbank(self, tile_value: int) -> int | None:
        """Get next tile in same sub-bank with circular wrapping.

        Returns:
            Next tile value or None if tile not found in any bank
        """
        position = self.find_tile_position(tile_value)
        if not position:
            return None

        bank_idx, subbank_idx, pos = position
        subbank = self.banks[bank_idx].subbanks[subbank_idx]

        # Circular wrapping
        next_pos = (pos + 1) % len(subbank.tile_indices)
        return subbank.tile_indices[next_pos]

    def get_previous_tile_in_subbank(self, tile_value: int) -> int | None:
        """Get previous tile in same sub-bank with circular wrapping.

        Returns:
            Previous tile value or None if tile not found in any bank
        """
        position = self.find_tile_position(tile_value)
        if not position:
            return None

        bank_idx, subbank_idx, pos = position
        subbank = self.banks[bank_idx].subbanks[subbank_idx]

        # Circular wrapping (negative index works in Python)
        prev_pos = (pos - 1) % len(subbank.tile_indices)
        return subbank.tile_indices[prev_pos]

    def render(self, screen: Surface, palette_idx: int = 1):
        """Render the tile picker with all banks."""
        # Background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.rect)

        # Create clipping rect for scrolling
        clip_rect = self.rect.copy()
        clip_rect.y += 5
        clip_rect.height -= 10

        # Render each bank
        picker_width = self.rect.width - 20  # 10px margin on each side

        for i, bank in enumerate(self.banks):
            bank_y = self.rect.y + self._bank_positions[i] - self.scroll_y
            bank_x = self.rect.x + 10

            # Skip banks completely outside visible area (optimization)
            bank_height = bank.get_height()
            if bank_y + bank_height < clip_rect.y or bank_y > clip_rect.bottom:
                continue

            bank.render(
                screen,
                bank_x,
                bank_y,
                picker_width,
                self.tileset,
                palette_idx,
                self.selected_tile,
                self.hovered_tile,
                clip_rect,
            )
