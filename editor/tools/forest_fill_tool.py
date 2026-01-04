"""
Forest fill tool - intelligent WFC-based forest region filling.
"""

import pygame
from pygame import Rect

from editor.controllers.view_state import ViewState
from editor.core.constants import (
    CANVAS_OFFSET_X,
    CANVAS_OFFSET_Y,
    STATUS_HEIGHT,
)

from .base_tool import ToolResult


class ForestFillTool:
    """Forest fill tool - fills placeholder regions with forest tiles."""

    def handle_mouse_down(self, pos, button, modifiers, context):
        if button != 1:  # Only left click
            return ToolResult.not_handled()

        # Only in terrain mode
        if context.state.mode != "terrain":
            return ToolResult(
                handled=True, message="Forest Fill: Only available in terrain mode"
            )

        if not context.forest_filler:
            return ToolResult(
                handled=True,
                message="Forest fill not available (neighbor data missing)",
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

        # Get clicked tile
        tile = view_state.screen_to_tile(pos)
        if not tile:
            return ToolResult.handled()

        clicked_row, clicked_col = tile

        # Detect all regions
        regions = context.forest_filler.detect_regions(context.hole_data.terrain)

        if not regions:
            return ToolResult(
                handled=True, message="Forest Fill: No placeholder regions detected"
            )

        # Find which region contains the clicked tile
        clicked_region = None
        for region in regions:
            if region.contains_tile((clicked_row, clicked_col)):
                clicked_region = region
                break

        if not clicked_region:
            return ToolResult(
                handled=True,
                message="Forest Fill: Click inside a forest placeholder region"
            )

        # Fill only this region
        changes = context.forest_filler.fill_region(
            context.hole_data.terrain, clicked_region
        )

        if not changes:
            return ToolResult(
                handled=True, message="Forest Fill: No fillable cells found in this region"
            )

        # Push undo state before applying
        context.state.undo_manager.push_state(context.hole_data)

        # Apply changes
        for (row, col), tile_value in changes.items():
            context.hole_data.set_terrain_tile(row, col, tile_value)

        message = f"Forest Fill: Filled {len(changes)} tiles"
        return ToolResult.modified(terrain=True, message=message)

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

    def get_hotkey(self) -> int | None:
        """Return 'F' key for Forest Fill tool."""
        return pygame.K_f
