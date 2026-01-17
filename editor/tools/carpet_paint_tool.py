"""
Carpet Paint tool for greens editing.

Paints putting surface tiles while protecting fringe and rough tiles from
accidental modification. When active, protected tiles are visually dimmed.
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
)

from .base_tool import ToolContext, ToolResult

# Tiles that CAN be painted over (putting surface area)
PAINTABLE_TILES = {
    0x100,  # Placeholder
    0xB0,   # Flat
    # Slopes (dark): 0x30-0x47
    *range(0x30, 0x48),
    # Slopes (light): 0x88-0xA7
    *range(0x88, 0xA8),
}

# Tiles that are PROTECTED (dimmed, cannot paint over)
PROTECTED_TILES = {
    # Fringe: 0x48-0x6F, 0x74-0x83
    *range(0x48, 0x70),
    *range(0x74, 0x84),
    # Rough base + edge variants
    0x29, 0x2C,
    0x70, 0x71, 0x72, 0x73,
    0x84, 0x85, 0x86, 0x87,
}


class CarpetPaintTool:
    """Carpet Paint tool - paints putting surface tiles only.

    This tool only allows painting over placeholder, flat, and slope tiles.
    Fringe and rough tiles are protected and cannot be modified.
    """

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

        # Only operates in greens mode
        if context.state.mode != "greens":
            return ToolResult.not_handled()

        # Start paint stroke
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
        # Set flag for visual dimming of protected tiles
        if context.highlight_state:
            context.highlight_state.carpet_paint_active = True

    def on_deactivated(self, context):
        # Clear dimming flag
        if context.highlight_state:
            context.highlight_state.carpet_paint_active = False
        self.reset()

    def reset(self):
        self.is_painting = False
        self.last_paint_pos = None
        self.undo_pushed = False

    def get_hotkey(self) -> int | None:
        """Return 'V' key for Carpet Paint tool."""
        return pygame.K_v

    def _paint_at(self, pos: tuple[int, int], context: ToolContext) -> ToolResult:
        """Paint at screen position if target tile is paintable."""
        # Only operates in greens mode
        if context.state.mode != "greens":
            return ToolResult.not_handled()

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

        tile = view_state.screen_to_tile(pos)
        if tile and tile != self.last_paint_pos:
            row, col = tile
            if 0 <= row < GREENS_HEIGHT and 0 <= col < GREENS_WIDTH:
                current_tile = context.hole_data.greens[row][col]

                # Check if target tile is paintable
                if current_tile not in PAINTABLE_TILES:
                    # Protected tile - silently skip but update position
                    self.last_paint_pos = tile
                    return ToolResult.handled()

                selected_tile = context.greens_picker.selected_tile

                # Only paint if the value is actually changing
                if current_tile != selected_tile:
                    # Push undo state only on first actual modification
                    if not self.undo_pushed:
                        context.state.undo_manager.push_state(context.hole_data)
                        self.undo_pushed = True

                    context.hole_data.set_greens_tile(row, col, selected_tile)
                    self.last_paint_pos = tile
                    return ToolResult.modified(terrain=False)

                # Clicked on same value - update position but don't modify
                self.last_paint_pos = tile
        return ToolResult.handled()
