"""Action tool for removing terrain rows."""

import pygame
from .base_tool import Tool, ToolContext, ToolResult


class RemoveRowTool:
    """Action tool that removes a terrain row from the bottom."""

    def handle_mouse_down(self, pos, button, modifiers, context):
        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context: ToolContext):
        """Execute remove row operation when activated."""
        # Get the row operations tool
        row_ops = context.tool_manager.get_tool("row_operations")
        if row_ops:
            # This will push undo and modify terrain
            row_ops.remove_row(context, from_top=False)

    def on_deactivated(self, context: ToolContext):
        pass

    def reset(self):
        pass

    def get_hotkey(self):
        """Return '-' key."""
        return pygame.K_MINUS

    def is_action_tool(self):
        """Identify this as an action tool."""
        return True
