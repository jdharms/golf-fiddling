"""
Bank classes for organizing tiles in tile picker panels.

This module provides reusable tile organization components that handle
layout, rendering, and hit detection for groups of tiles.
"""


import pygame
from pygame import Rect, Surface

from editor.core.constants import (
    COLOR_GRID,
    COLOR_SELECTION,
    COLOR_TEXT,
    TILE_SIZE,
)
from editor.core.pygame_rendering import Tileset


def _render_placeholder_tile(size: int) -> Surface:
    """Render the placeholder tile (0x100) with a distinctive pattern."""
    surf = Surface((size, size))
    # Gray checkerboard pattern to indicate meta/placeholder tile
    gray1 = (100, 100, 100)
    gray2 = (140, 140, 140)
    checker_size = size // 4

    for row in range(4):
        for col in range(4):
            color = gray1 if (row + col) % 2 == 0 else gray2
            rect = (col * checker_size, row * checker_size, checker_size, checker_size)
            pygame.draw.rect(surf, color, rect)

    return surf


def range_to_list(min: int, max: int) -> list[int]:
    return list(range(min, max))


class TileSubBank:
    """A labeled subgroup of tiles within a bank."""

    def __init__(self, label: str, tile_indices: list[int]):
        """
        Args:
            label: Display name for this subbank (e.g., "Borders With Depth")
            tile_indices: List of tile index values for this subbank
        """
        self.label = label
        self.tile_indices = tile_indices

        # Layout constants
        self.label_height = 14  # Smaller than bank labels
        self.spacing_before = 4  # Vertical spacing before this subbank

    def get_height(self, tiles_per_row: int, tile_scale: int, tile_spacing: int) -> int:
        """
        Calculate total rendered height of this subbank.

        Args:
            tiles_per_row: Number of tiles per row (from parent bank)
            tile_scale: Tile rendering scale (from parent bank)
            tile_spacing: Spacing between tiles in pixels

        Returns:
            Total height in pixels including label and tiles
        """
        # Calculate grid dimensions
        num_tiles = len(self.tile_indices)
        num_rows = (num_tiles + tiles_per_row - 1) // tiles_per_row

        tile_size = TILE_SIZE * tile_scale + tile_spacing
        tiles_height = num_rows * tile_size

        # Total: spacing before + label + tiles
        return self.spacing_before + self.label_height + tiles_height

    def render(
        self,
        screen: Surface,
        x: int,
        y: int,
        width: int,
        tileset: Tileset,
        palette_idx: int,
        selected_tile: int | None,
        tiles_per_row: int,
        tile_scale: int,
        tile_spacing: int,
        clip_rect: Rect,
    ) -> int:
        """
        Render this subbank at the specified position.

        Args:
            screen: Pygame surface to draw on
            x: Left edge x coordinate
            y: Top edge y coordinate (includes spacing before)
            width: Total width available
            tileset: Tileset for rendering tiles
            palette_idx: Palette index for terrain rendering
            selected_tile: Currently selected tile value (for highlight)
            tiles_per_row: Number of tiles per row
            tile_scale: Tile rendering scale
            tile_spacing: Spacing between tiles
            clip_rect: Clipping rectangle for scrolling

        Returns:
            Height consumed by this subbank
        """
        current_y = y + self.spacing_before

        # 1. Render label text (left-aligned, smaller font)
        font = pygame.font.SysFont("monospace", 10)
        text_surf = font.render(self.label, True, COLOR_GRID)  # Subtle gray color
        screen.blit(text_surf, (x, current_y))

        current_y += self.label_height

        # 2. Render tiles in grid
        tile_size = TILE_SIZE * tile_scale + tile_spacing

        for i, tile_idx in enumerate(self.tile_indices):
            col = i % tiles_per_row
            row = i // tiles_per_row

            tile_x = x + col * tile_size
            tile_y = current_y + row * tile_size

            # Skip if outside clip rect
            if tile_y + tile_size < clip_rect.y or tile_y > clip_rect.bottom:
                continue

            # Render tile (special handling for 0x100 placeholder)
            if tile_idx == 0x100:
                tile_surf = _render_placeholder_tile(TILE_SIZE * tile_scale)
            else:
                tile_surf = tileset.render_tile(tile_idx, palette_idx, tile_scale)
            screen.blit(tile_surf, (tile_x, tile_y))

            # Selection highlight
            if tile_idx == selected_tile:
                pygame.draw.rect(
                    screen,
                    COLOR_SELECTION,
                    (
                        tile_x - 1,
                        tile_y - 1,
                        TILE_SIZE * tile_scale + 2,
                        TILE_SIZE * tile_scale + 2,
                    ),
                    2,
                )

        return self.get_height(tiles_per_row, tile_scale, tile_spacing)


class SimpleTileBank:
    """A labeled group of tiles without subbank subdivision."""

    def __init__(
        self,
        label: str,
        tile_indices: list[int],
        tiles_per_row: int,
        tile_scale: int,
        tile_spacing: int = 2,
    ):
        """
        Args:
            label: Display name for this bank (e.g., "Rough", "Fringe")
            tile_indices: List of tile index values for this bank
            tiles_per_row: Number of tiles per row (from parent picker)
            tile_scale: Tile rendering scale (from parent picker)
            tile_spacing: Spacing between tiles in pixels
        """
        self.label = label
        self.tile_indices = tile_indices
        self.tiles_per_row = tiles_per_row
        self.tile_scale = tile_scale
        self.tile_spacing = tile_spacing

        # Layout constants (same as GroupedTileBank for consistency)
        self.label_height = 20  # Height of label header
        self.border_width = 1  # Border line thickness
        self.padding = 4  # Internal padding around tiles

    def get_height(self) -> int:
        """
        Calculate total rendered height of this bank.

        Returns:
            Total height in pixels including label, tiles, borders, padding
        """
        # Calculate grid dimensions
        num_tiles = len(self.tile_indices)
        num_rows = (num_tiles + self.tiles_per_row - 1) // self.tiles_per_row

        tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing
        tiles_height = num_rows * tile_size

        # Total: label + top padding + tiles + bottom padding + bottom border
        return (
            self.label_height
            + self.padding
            + tiles_height
            + self.padding
            + self.border_width
        )

    def get_tile_count(self) -> int:
        """Return number of tiles in this bank."""
        return len(self.tile_indices)

    def render(
        self,
        screen: Surface,
        x: int,
        y: int,
        width: int,
        tileset: Tileset,
        palette_idx: int,
        selected_tile: int | None,
        hovered_tile: int | None,
        clip_rect: Rect,
    ):
        """
        Render this bank at the specified position.

        Args:
            screen: Pygame surface to draw on
            x: Left edge x coordinate
            y: Top edge y coordinate (includes label)
            width: Total width of bank
            tileset: Tileset for rendering tiles
            palette_idx: Palette index for terrain rendering
            selected_tile: Currently selected tile value (for highlight)
            hovered_tile: Currently hovered tile value (for highlight)
            clip_rect: Clipping rectangle for scrolling
        """
        # 1. Draw label background
        label_rect = Rect(x, y, width, self.label_height)
        pygame.draw.rect(screen, COLOR_GRID, label_rect)

        # 2. Render label text (centered)
        font = pygame.font.SysFont("monospace", 12)
        text_surf = font.render(self.label, True, COLOR_TEXT)
        text_x = x + (width - text_surf.get_width()) // 2
        text_y = y + (self.label_height - text_surf.get_height()) // 2
        screen.blit(text_surf, (text_x, text_y))

        # 3. Draw bank border (around entire bank including label)
        bank_height = self.get_height()
        border_rect = Rect(x, y, width, bank_height)
        pygame.draw.rect(screen, COLOR_GRID, border_rect, self.border_width)

        # 4. Render tiles in grid
        tile_y_start = y + self.label_height + self.padding
        tile_x_start = x + self.padding
        tile_size = TILE_SIZE * self.tile_scale + self.tile_spacing

        for i, tile_idx in enumerate(self.tile_indices):
            col = i % self.tiles_per_row
            row = i // self.tiles_per_row

            tile_x = tile_x_start + col * tile_size
            tile_y = tile_y_start + row * tile_size

            # Skip if outside clip rect
            if tile_y + tile_size < clip_rect.y or tile_y > clip_rect.bottom:
                continue

            # Render tile (special handling for 0x100 placeholder)
            if tile_idx == 0x100:
                tile_surf = _render_placeholder_tile(TILE_SIZE * self.tile_scale)
            else:
                tile_surf = tileset.render_tile(tile_idx, palette_idx, self.tile_scale)
            screen.blit(tile_surf, (tile_x, tile_y))

            # Selection highlight
            if tile_idx == selected_tile:
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

    def get_tile_at_position(
        self,
        local_x: int,
        bank_content_y: int,
        tiles_per_row: int,
        tile_scale: int,
        tile_spacing: int,
    ) -> int | None:
        """
        Get tile index at position within bank content area, or None if invalid.

        Args:
            local_x: X position relative to bank content area
            bank_content_y: Y position relative to bank content area (after label + padding)
            tiles_per_row: Number of tiles per row
            tile_scale: Tile rendering scale
            tile_spacing: Spacing between tiles in pixels

        Returns:
            Tile index or None if position is invalid
        """
        tile_size = TILE_SIZE * tile_scale + tile_spacing

        col = local_x // tile_size
        row = bank_content_y // tile_size

        # Check bounds
        if col < 0 or col >= tiles_per_row:
            return None

        tile_idx = row * tiles_per_row + col
        if 0 <= tile_idx < len(self.tile_indices):
            return self.tile_indices[tile_idx]

        return None


class GroupedTileBank:
    """A labeled group of tiles within a tile picker, organized into subbanks."""

    def __init__(
        self,
        label: str,
        subbanks: list[TileSubBank],
        tiles_per_row: int,
        tile_scale: int,
        tile_spacing: int = 2,
    ):
        """
        Args:
            label: Display name for this bank (e.g., "Teebox", "Rough")
            subbanks: List of TileSubBank objects for this bank
            tiles_per_row: Number of tiles per row (from parent picker)
            tile_scale: Tile rendering scale (from parent picker)
            tile_spacing: Spacing between tiles in pixels
        """
        self.label = label
        self.subbanks = subbanks
        self.tiles_per_row = tiles_per_row
        self.tile_scale = tile_scale
        self.tile_spacing = tile_spacing

        # Layout constants
        self.label_height = 20  # Height of label header
        self.border_width = 1  # Border line thickness
        self.padding = 4  # Internal padding around tiles

    def get_height(self) -> int:
        """
        Calculate total rendered height of this bank.

        Returns:
            Total height in pixels including label, subbanks, borders, padding
        """
        # Sum heights of all subbanks
        subbanks_height = sum(
            subbank.get_height(self.tiles_per_row, self.tile_scale, self.tile_spacing)
            for subbank in self.subbanks
        )

        # Total: label + top padding + subbanks + bottom padding + bottom border
        return (
            self.label_height
            + self.padding
            + subbanks_height
            + self.padding
            + self.border_width
        )

    def get_tile_count(self) -> int:
        """Return number of tiles in this bank."""
        return sum(len(subbank.tile_indices) for subbank in self.subbanks)

    def render(
        self,
        screen: Surface,
        x: int,
        y: int,
        width: int,
        tileset: Tileset,
        palette_idx: int,
        selected_tile: int | None,
        hovered_tile: int | None,
        clip_rect: Rect,
    ):
        """
        Render this bank at the specified position.

        Args:
            screen: Pygame surface to draw on
            x: Left edge x coordinate
            y: Top edge y coordinate (includes label)
            width: Total width of bank
            tileset: Tileset for rendering tiles
            palette_idx: Palette index for terrain rendering
            selected_tile: Currently selected tile value (for highlight)
            hovered_tile: Currently hovered tile value (for highlight)
            clip_rect: Clipping rectangle for scrolling
        """
        # 1. Draw label background
        label_rect = Rect(x, y, width, self.label_height)
        pygame.draw.rect(screen, COLOR_GRID, label_rect)

        # 2. Render label text (centered)
        font = pygame.font.SysFont("monospace", 12)
        text_surf = font.render(self.label, True, COLOR_TEXT)
        text_x = x + (width - text_surf.get_width()) // 2
        text_y = y + (self.label_height - text_surf.get_height()) // 2
        screen.blit(text_surf, (text_x, text_y))

        # 3. Draw bank border (around entire bank including label)
        bank_height = self.get_height()
        border_rect = Rect(x, y, width, bank_height)
        pygame.draw.rect(screen, COLOR_GRID, border_rect, self.border_width)

        # 4. Render subbanks
        current_y = y + self.label_height + self.padding
        subbank_x = x + self.padding

        for subbank in self.subbanks:
            height_consumed = subbank.render(
                screen,
                subbank_x,
                current_y,
                width - 2 * self.padding,
                tileset,
                palette_idx,
                selected_tile,
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
                clip_rect,
            )
            current_y += height_consumed

    def get_tile_at_position(
        self,
        local_x: int,
        bank_content_y: int,
        tiles_per_row: int,
        tile_scale: int,
        tile_spacing: int,
    ) -> int | None:
        """
        Get tile index at position within bank content area, or None if invalid.

        Args:
            local_x: X position relative to bank content area
            bank_content_y: Y position relative to bank content area (after label + padding)
            tiles_per_row: Number of tiles per row
            tile_scale: Tile rendering scale
            tile_spacing: Spacing between tiles in pixels

        Returns:
            Tile index or None if position is invalid
        """
        # Search through subbanks to find which one contains this y position
        current_subbank_y = 0
        for subbank in self.subbanks:
            subbank_height = subbank.get_height(tiles_per_row, tile_scale, tile_spacing)

            if current_subbank_y <= bank_content_y < current_subbank_y + subbank_height:
                # We're inside this subbank
                # Position relative to subbank
                subbank_local_y = bank_content_y - current_subbank_y

                # Check if we're in the subbank label area
                if subbank_local_y < subbank.spacing_before + subbank.label_height:
                    return None  # Clicked on subbank label

                # Position relative to subbank's tile grid
                tile_area_y = subbank_local_y - (
                    subbank.spacing_before + subbank.label_height
                )

                tile_size = TILE_SIZE * tile_scale + tile_spacing
                col = local_x // tile_size
                row = tile_area_y // tile_size

                # Check bounds
                if col < 0 or col >= tiles_per_row:
                    return None

                tile_idx = row * tiles_per_row + col
                if 0 <= tile_idx < len(subbank.tile_indices):
                    return subbank.tile_indices[tile_idx]
                return None

            current_subbank_y += subbank_height

        return None  # Outside all subbanks
