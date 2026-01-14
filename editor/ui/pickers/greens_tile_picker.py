"""
Greens-specific tile picker panel.
"""

from pygame import Rect

from .tile_banks import (
    SimpleTileBankGreens,
    GroupedTileBankGreens,
    TileSubBankGreens,
    range_to_list,
)
from .tile_picker import TilePicker


class GreensTilePicker(TilePicker):
    """Tile picker for greens editing."""

    def __init__(self, tileset, rect: Rect, on_hover_change=None, on_tile_selected=None):
        super().__init__(tileset, rect, on_hover_change, on_tile_selected)

        # Override banks with greens-specific tiles organized by type
        # Fringe groups organized by path direction
        fringe_groups = [
            ("Down-Left 1", [0x4B, 0x51, 0x5D, 0x7D, 0x83]),
            ("Down-Left 2", [0x5A, 0x6A, 0x6D, 0x75, 0x79]),
            ("Down-Right 1", [0x48, 0x50, 0x5C, 0x7C, 0x82]),
            ("Down-Right 2", [0x5B, 0x6B, 0x6C, 0x74, 0x78]),
            ("Down-Up 1", [0x53, 0x55, 0x61, 0x67]),
            ("Down-Up 2", [0x52, 0x54, 0x60, 0x66]),
            ("Left-Right 1", [0x49, 0x4A, 0x62, 0x64]),
            ("Left-Right 2", [0x4D, 0x4E, 0x63, 0x65]),
            ("Left-Up 1", [0x58, 0x68, 0x6F, 0x77, 0x7B]),
            ("Left-Up 2", [0x4F, 0x57, 0x5F, 0x7F, 0x81]),
            ("Right-Up 1", [0x59, 0x69, 0x6E, 0x76, 0x7A]),
            ("Right-Up 2", [0x4C, 0x56, 0x5E, 0x7E, 0x80]),
        ]

        self.banks = [
            SimpleTileBankGreens(
                "Placeholder",
                [0x100],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            GroupedTileBankGreens(
                "Rough",
                [
                    TileSubBankGreens("Family $29", [0x29, 0x70, 0x71, 0x72, 0x73]),
                    TileSubBankGreens("Family $2C", [0x2C, 0x84, 0x85, 0x86, 0x87])
                ],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            GroupedTileBankGreens(
                "Fringe",
                [TileSubBankGreens(label, tiles) for label, tiles in fringe_groups],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            GroupedTileBankGreens(
                "Slopes",
                [
                    TileSubBankGreens("Gentle Dark", range_to_list(0x30, 0x38)),
                    TileSubBankGreens("Moderate Dark", range_to_list(0x38, 0x40)),
                    TileSubBankGreens("Steep Dark", range_to_list(0x40, 0x48)),
                    TileSubBankGreens("Gentle Light", range_to_list(0x90, 0x98)),
                    TileSubBankGreens("Moderate Light", range_to_list(0x98, 0xA0)),
                    TileSubBankGreens("Steep Light", range_to_list(0x88, 0x90)),
                ],
                self.tiles_per_row,
                self.tile_scale,
                self.tile_spacing,
            ),
            SimpleTileBankGreens(
                "Flat", [0xB0], self.tiles_per_row, self.tile_scale, self.tile_spacing
            ),
        ]
        self._calculate_bank_positions()

        self.selected_tile = 0x30

    def find_tile_position(self, tile_value: int) -> tuple[int, int] | tuple[int, int, int] | None:  # type: ignore[override]
        """Find position of tile in bank hierarchy.

        Returns:
            - (bank_idx, subbank_idx, position) for GroupedTileBankGreens
            - (bank_idx, position) for SimpleTileBankGreens
            - None if not found
        """
        for bank_idx, bank in enumerate(self.banks):
            if isinstance(bank, GroupedTileBankGreens):
                # Search subbanks, return (bank_idx, subbank_idx, position)
                for subbank_idx, subbank in enumerate(bank.subbanks):
                    if tile_value in subbank.tile_indices:
                        position = subbank.tile_indices.index(tile_value)
                        return (bank_idx, subbank_idx, position)
            else:  # SimpleTileBankGreens
                if tile_value in bank.tile_indices:
                    position = bank.tile_indices.index(tile_value)
                    return (bank_idx, position)
        return None

    def get_next_tile_in_subbank(self, tile_value: int) -> int | None:
        """Get next tile in same bank/subbank with circular wrapping.

        For SimpleTileBankGreens: cycles within the bank
        For GroupedTileBankGreens: cycles within the subbank

        Returns:
            Next tile value or None if tile not found in any bank
        """
        position = self.find_tile_position(tile_value)
        if not position:
            return None

        bank = self.banks[position[0]]

        if isinstance(bank, GroupedTileBankGreens):
            # 3-tuple: (bank_idx, subbank_idx, position)
            _, subbank_idx, pos = position  # type: ignore[misc]
            subbank = bank.subbanks[subbank_idx]
            next_pos = (pos + 1) % len(subbank.tile_indices)
            return subbank.tile_indices[next_pos]
        else:  # SimpleTileBankGreens
            # 2-tuple: (bank_idx, position)
            _, pos = position  # type: ignore[misc]
            next_pos = (pos + 1) % len(bank.tile_indices)
            return bank.tile_indices[next_pos]

    def get_previous_tile_in_subbank(self, tile_value: int) -> int | None:
        """Get previous tile in same bank/subbank with circular wrapping.

        For SimpleTileBankGreens: cycles within the bank
        For GroupedTileBankGreens: cycles within the subbank

        Returns:
            Previous tile value or None if tile not found in any bank
        """
        position = self.find_tile_position(tile_value)
        if not position:
            return None

        bank = self.banks[position[0]]

        if isinstance(bank, GroupedTileBankGreens):
            # 3-tuple: (bank_idx, subbank_idx, position)
            _, subbank_idx, pos = position  # type: ignore[misc]
            subbank = bank.subbanks[subbank_idx]
            prev_pos = (pos - 1) % len(subbank.tile_indices)
            return subbank.tile_indices[prev_pos]
        else:  # SimpleTileBankGreens
            # 2-tuple: (bank_idx, position)
            _, pos = position  # type: ignore[misc]
            prev_pos = (pos - 1) % len(bank.tile_indices)
            return bank.tile_indices[prev_pos]
