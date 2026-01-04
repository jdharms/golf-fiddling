"""
Transform tool for applying compression table transformations via shift+drag.
"""


import pygame
from pygame import Rect

from editor.controllers.view_state import ViewState
from editor.core.constants import (
    CANVAS_OFFSET_X,
    CANVAS_OFFSET_Y,
    GREENS_HEIGHT,
    GREENS_WIDTH,
    STATUS_HEIGHT,
    TERRAIN_WIDTH,
    TILE_SIZE,
)

from .base_tool import ToolResult


class TransformToolState:
    """State for an active transform drag operation."""

    def __init__(self):
        self.is_active = False
        self.drag_start_pos: tuple[int, int] | None = None
        self.origin_tile: tuple[int, int] | None = None
        self.preview_changes: dict[tuple[int, int], int] = {}
        self.direction: str | None = None
        self.blocked = False

    def start(self, mouse_pos: tuple[int, int], tile_pos: tuple[int, int]):
        self.is_active = True
        self.drag_start_pos = mouse_pos
        self.origin_tile = tile_pos
        self.preview_changes = {}
        self.direction = None
        self.blocked = False

    def reset(self):
        self.__init__()


class TransformTool:
    """Transform tool - shift+drag to apply compression transformations."""

    def __init__(self):
        self.state = TransformToolState()

    def handle_mouse_down(self, pos, button, modifiers, context):
        if button != 1:
            return ToolResult.not_handled()

        # Only in terrain or greens mode
        if context.state.mode not in ("terrain", "greens"):
            return ToolResult.not_handled()

        # Create view state
        canvas_rect = Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            context.screen_width - CANVAS_OFFSET_X,
            context.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT,
        )
        view_state = ViewState(
            canvas_rect,
            context.state.canvas_offset_x,
            context.state.canvas_offset_y,
            context.state.canvas_scale,
        )

        tile = view_state.screen_to_tile(pos)
        if tile:
            self.state.start(pos, tile)
            return ToolResult.handled()

        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        if button == 1 and self.state.is_active:
            # Commit transform
            if not self.state.blocked and self.state.preview_changes:
                context.state.undo_manager.push_state(context.hole_data)
                self._commit_transform(context)
                self.state.reset()
                return ToolResult.modified(terrain=(context.state.mode == "terrain"))
            else:
                self.state.reset()
                return ToolResult.handled()

        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        if self.state.is_active:
            self._update_transform_preview(pos, context)
            return ToolResult.handled()
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        # Cancel on Shift release
        if key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
            if self.state.is_active:
                self.state.reset()
                return ToolResult.handled()
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        self.reset()

    def reset(self):
        self.state.reset()

    def get_hotkey(self) -> int | None:
        """Return 'T' key for Transform tool."""
        return pygame.K_t

    def _update_transform_preview(self, pos, context):
        """Update transform preview based on drag movement."""
        dx = pos[0] - self.state.drag_start_pos[0]
        dy = pos[1] - self.state.drag_start_pos[1]

        # Determine direction
        if self.state.direction is None and (abs(dx) > 5 or abs(dy) > 5):
            if dx < -2 or dy < -2:
                self.state.blocked = True
                return
            self.state.direction = "horizontal" if abs(dx) > abs(dy) else "vertical"

        if self.state.direction is None:
            return

        # Get source tile
        origin_row, origin_col = self.state.origin_tile
        if context.state.mode == "terrain":
            source_value = context.hole_data.terrain[origin_row][origin_col]
            max_col = TERRAIN_WIDTH
            max_row = len(context.hole_data.terrain)
        else:
            source_value = context.hole_data.greens[origin_row][origin_col]
            max_col = GREENS_WIDTH
            max_row = GREENS_HEIGHT

        tile_size = TILE_SIZE * context.state.canvas_scale

        if self.state.direction == "horizontal":
            if dx < 0:
                self.state.preview_changes.clear()
                return

            steps = max(0, (dx + tile_size - 1) // tile_size)
            if steps == 0:
                self.state.preview_changes.clear()
                return

            self.state.preview_changes.clear()
            current_value = source_value
            for step in range(1, steps + 1):
                current_value = context.transform_logic.apply_horizontal(
                    current_value, context.state.mode
                )
                tile_col = origin_col + step
                if 0 <= tile_col < max_col:
                    self.state.preview_changes[(origin_row, tile_col)] = current_value

        else:  # vertical
            if dy < 0:
                self.state.preview_changes.clear()
                return

            steps = max(0, (dy + tile_size - 1) // tile_size)
            if steps == 0:
                self.state.preview_changes.clear()
                return

            self.state.preview_changes.clear()
            current_value = source_value
            for step in range(1, steps + 1):
                current_value = context.transform_logic.apply_vertical(
                    current_value, context.state.mode
                )
                tile_row = origin_row + step
                if 0 <= tile_row < max_row:
                    self.state.preview_changes[(tile_row, origin_col)] = current_value

    def _commit_transform(self, context):
        """Apply preview changes to hole data."""
        for (row, col), tile_value in self.state.preview_changes.items():
            if context.state.mode == "terrain":
                context.hole_data.set_terrain_tile(row, col, tile_value)
            else:
                context.hole_data.set_greens_tile(row, col, tile_value)
