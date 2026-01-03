"""
Eyedropper tool for sampling tiles from the canvas.
"""

from pygame import Rect

from editor.controllers.view_state import ViewState
from editor.core.constants import (
    CANVAS_OFFSET_X,
    CANVAS_OFFSET_Y,
    GREENS_WIDTH,
    STATUS_HEIGHT,
    TERRAIN_WIDTH,
)

from .base_tool import ToolResult


class EyedropperTool:
    """Eyedropper tool - samples tiles/palettes from canvas."""

    def handle_mouse_down(self, pos, button, modifiers, context):
        if button == 3:  # Right click
            return self._sample_at(pos, context)
        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        pass

    def reset(self):
        pass

    def _sample_at(self, pos, context) -> ToolResult:
        """Sample tile/palette at position."""
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
            tile = view_state.screen_to_tile(pos)
            if tile:
                row, col = tile
                if (
                    0 <= row < len(context.hole_data.terrain)
                    and 0 <= col < TERRAIN_WIDTH
                ):
                    context.terrain_picker.selected_tile = context.hole_data.terrain[
                        row
                    ][col]
                    return ToolResult.handled()

        elif mode == "palette":
            supertile = view_state.screen_to_supertile(pos)
            if supertile:
                row, col = supertile
                if 0 <= row < len(context.hole_data.attributes) and 0 <= col < len(
                    context.hole_data.attributes[row]
                ):
                    context.state.selected_palette = context.hole_data.attributes[row][
                        col
                    ]
                    return ToolResult.handled()

        elif mode == "greens":
            tile = view_state.screen_to_tile(pos)
            if tile:
                row, col = tile
                if 0 <= row < len(context.hole_data.greens) and 0 <= col < GREENS_WIDTH:
                    context.greens_picker.selected_tile = context.hole_data.greens[row][
                        col
                    ]
                    return ToolResult.handled()

        return ToolResult.not_handled()
