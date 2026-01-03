"""
Forest fill tool - intelligent WFC-based forest region filling.
"""

import pygame
from .base_tool import Tool, ToolContext, ToolResult


class ForestFillTool:
    """Forest fill tool - fills placeholder regions with forest tiles."""

    def handle_mouse_down(self, pos, button, modifiers, context):
        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        # Ctrl+F activates forest fill
        if key == pygame.K_f and (modifiers & pygame.KMOD_CTRL):
            return self._trigger_forest_fill(context)
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        pass

    def reset(self):
        pass

    def _trigger_forest_fill(self, context) -> ToolResult:
        """Execute forest fill on detected regions."""
        if context.state.mode != "terrain":
            return ToolResult(
                handled=True, message="Forest Fill: Only available in terrain mode"
            )

        if not context.forest_filler:
            return ToolResult(
                handled=True,
                message="Forest fill not available (neighbor data missing)",
            )

        # Detect regions
        regions = context.forest_filler.detect_regions(context.hole_data.terrain)

        if not regions:
            return ToolResult(
                handled=True, message="Forest Fill: No placeholder regions detected"
            )

        # Fill all regions
        all_changes = {}
        for region in regions:
            changes = context.forest_filler.fill_region(
                context.hole_data.terrain, region
            )
            all_changes.update(changes)

        if not all_changes:
            return ToolResult(
                handled=True, message="Forest Fill: No fillable cells found"
            )

        # Push undo state before applying
        context.state.undo_manager.push_state(context.hole_data)

        # Apply changes
        for (row, col), tile in all_changes.items():
            context.hole_data.set_terrain_tile(row, col, tile)

        message = (
            f"Forest Fill: Filled {len(all_changes)} tiles in {len(regions)} region(s)"
        )
        return ToolResult.modified(terrain=True, message=message)
