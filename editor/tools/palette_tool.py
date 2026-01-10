"""
Palette tool for painting attribute (palette) values on terrain.
"""


import pygame
from pygame import Rect

from editor.controllers.view_state import ViewState
from editor.core.constants import (
    CANVAS_OFFSET_X,
    CANVAS_OFFSET_Y,
    STATUS_HEIGHT,
)

from .base_tool import ToolContext, ToolResult


class PaletteTool:
    """Palette tool - paint attribute (palette) values on terrain."""

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
        """Return 'A' key for Palette tool (A for Attributes)."""
        return pygame.K_a

    def _paint_at(self, pos: tuple[int, int], context: ToolContext) -> ToolResult:
        """Paint palette at screen position."""
        # Only works in terrain mode (greens have fixed palette)
        if context.state.mode != "terrain":
            return ToolResult(
                handled=True,
                message="Palette: Not available in greens mode"
            )

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

        supertile = view_state.screen_to_supertile(pos)
        if supertile and supertile != self.last_paint_pos:
            row, col = supertile

            # Validate bounds before accessing attributes array
            if not (0 <= row < len(context.hole_data.attributes) and
                    0 <= col < len(context.hole_data.attributes[row])):
                return ToolResult.handled()  # Outside valid area

            current_palette = context.hole_data.attributes[row][col]

            # Only paint if the value is actually changing
            if current_palette != context.state.selected_palette:
                # Push undo state only on first actual modification of this paint stroke
                if not self.undo_pushed:
                    context.state.undo_manager.push_state(context.hole_data)
                    self.undo_pushed = True

                context.hole_data.set_attribute(
                    row, col, context.state.selected_palette
                )
                self.last_paint_pos = supertile
                return ToolResult.modified(terrain=False)

            # Clicked on same value - update position but don't modify
            self.last_paint_pos = supertile
        return ToolResult.handled()
