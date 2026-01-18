"""
NES Open Tournament Golf - Editor State

Manages application state including editing mode, view settings, and canvas position.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from editor.data import ClipboardData

from .undo_manager import UndoManager


class GridMode(Enum):
    """Grid display mode."""

    OFF = auto()  # No grid displayed
    TILE = auto()  # Standard 1x1 tile grid
    SUPERTILE = auto()  # 2x2 supertile grid


@dataclass
class CanvasState:
    """Per-mode canvas viewport state."""

    offset_x: int = 0
    offset_y: int = 0
    scale: int = 4


class EditorState:
    """Manages editor application state."""

    def __init__(self):
        # Editing mode
        self.mode: str = "terrain"  # "terrain" or "greens"

        # View settings
        self.grid_mode: GridMode = GridMode.TILE
        self.show_invalid_tiles: bool = False

        # Canvas position and zoom (per-mode)
        self._canvas_states: dict[str, CanvasState] = {
            "terrain": CanvasState(),
            "greens": CanvasState(),
        }

        # Tool settings
        self.selected_palette: int = 1  # For palette mode
        self.selected_flag_index: int = 0  # Which of 4 flag positions (0-3)
        self.tool_message: str | None = None  # Current tool status message

        # Clipboard and paste preview
        self.clipboard: ClipboardData | None = None
        self.paste_preview_active: bool = False

        # Undo/redo support
        self.undo_manager: UndoManager = UndoManager(max_undo_levels=50)

    # Property accessors for per-mode canvas state
    @property
    def canvas_offset_x(self) -> int:
        return self._canvas_states[self.mode].offset_x

    @canvas_offset_x.setter
    def canvas_offset_x(self, value: int) -> None:
        self._canvas_states[self.mode].offset_x = value

    @property
    def canvas_offset_y(self) -> int:
        return self._canvas_states[self.mode].offset_y

    @canvas_offset_y.setter
    def canvas_offset_y(self, value: int) -> None:
        self._canvas_states[self.mode].offset_y = value

    @property
    def canvas_scale(self) -> int:
        return self._canvas_states[self.mode].scale

    @canvas_scale.setter
    def canvas_scale(self, value: int) -> None:
        self._canvas_states[self.mode].scale = value

    def set_mode(self, mode: str):
        """Set the editing mode."""
        if mode in ("terrain", "greens"):
            self.mode = mode

    def cycle_grid_mode(self):
        """Cycle through grid modes: OFF -> TILE -> SUPERTILE -> OFF."""
        if self.grid_mode == GridMode.OFF:
            self.grid_mode = GridMode.TILE
        elif self.grid_mode == GridMode.TILE:
            self.grid_mode = GridMode.SUPERTILE
        else:
            self.grid_mode = GridMode.OFF

    @property
    def show_grid(self) -> bool:
        """Backward compatibility: returns True if grid is visible."""
        return self.grid_mode != GridMode.OFF

    def toggle_invalid_tiles(self):
        """Toggle invalid tile highlighting."""
        self.show_invalid_tiles = not self.show_invalid_tiles

    def select_flag(self, index: int):
        """Select which flag position to display (0-3)."""
        if 0 <= index <= 3:
            self.selected_flag_index = index

    def reset_canvas_position(self):
        """Reset canvas to origin for both modes."""
        for canvas_state in self._canvas_states.values():
            canvas_state.offset_x = 0
            canvas_state.offset_y = 0
