"""
Paint tool for terrain and greens editing.
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
)

from .base_tool import ToolContext, ToolResult


class PaintTool:
    """Paint tool - primary editing tool for all modes."""

    def __init__(self):
        self.is_painting = False
        self.last_paint_pos: tuple[int, int] | None = None
        self.undo_pushed = False

    def handle_mouse_down(self, pos, button, modifiers, context):
        # Right-click: delegate to eyedropper
        if button == 3:
            eyedropper = context.get_eyedropper_tool()
            if eyedropper:
                return eyedropper.handle_mouse_down(pos, button, modifiers, context)
            return ToolResult.not_handled()

        if button != 1:  # Only left click
            return ToolResult.not_handled()

        # Start paint stroke (but don't push undo yet - wait for first actual modification)
        if not self.is_painting:
            self.is_painting = True

        return self._paint_at(pos, context)

    def handle_mouse_up(self, pos, button, context):
        if button == 1:
            self.is_painting = False
            self.last_paint_pos = None
            self.undo_pushed = False
        return ToolResult.handled()

    def handle_mouse_motion(self, pos, context):
        if self.is_painting:
            return self._paint_at(pos, context)
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        self.reset()

    def reset(self):
        self.is_painting = False
        self.last_paint_pos = None
        self.undo_pushed = False

    def get_hotkey(self) -> int | None:
        """Return 'P' key for Paint tool."""
        return pygame.K_p

    def _paint_at(self, pos: tuple[int, int], context: ToolContext) -> ToolResult:
        """Paint at screen position based on current mode."""
        # Create view state for coordinate conversion
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

        mode = context.state.mode

        if mode == "terrain":
            return self._paint_terrain(view_state, pos, context)
        elif mode == "greens":
            return self._paint_greens(view_state, pos, context)

        return ToolResult.not_handled()

    def _paint_terrain(self, view_state, pos, context) -> ToolResult:
        tile = view_state.screen_to_tile(pos)
        if tile and tile != self.last_paint_pos:
            row, col = tile
            if 0 <= row < len(context.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                selected_tile = context.terrain_picker.selected_tile
                current_tile = context.hole_data.terrain[row][col]

                # Only paint if the value is actually changing
                if current_tile != selected_tile:
                    # Push undo state only on first actual modification of this paint stroke
                    if not self.undo_pushed:
                        context.state.undo_manager.push_state(context.hole_data)
                        self.undo_pushed = True

                    context.hole_data.set_terrain_tile(row, col, selected_tile)
                    self.last_paint_pos = tile
                    return ToolResult.modified(terrain=True)

                # Clicked on same value - update position but don't modify
                self.last_paint_pos = tile
        return ToolResult.handled()

    def _paint_greens(self, view_state, pos, context) -> ToolResult:
        tile = view_state.screen_to_tile(pos)
        if tile and tile != self.last_paint_pos:
            row, col = tile
            if 0 <= row < GREENS_HEIGHT and 0 <= col < GREENS_WIDTH:
                selected_tile = context.greens_picker.selected_tile
                current_tile = context.hole_data.greens[row][col]

                # Only paint if the value is actually changing
                if current_tile != selected_tile:
                    # Push undo state only on first actual modification of this paint stroke
                    if not self.undo_pushed:
                        context.state.undo_manager.push_state(context.hole_data)
                        self.undo_pushed = True

                    context.hole_data.set_greens_tile(row, col, selected_tile)
                    self.last_paint_pos = tile
                    return ToolResult.modified(terrain=False)

                # Clicked on same value - update position but don't modify
                self.last_paint_pos = tile
        return ToolResult.handled()
