"""Action tool for adding terrain rows."""

import pygame
from .base_tool import Tool, ToolContext, ToolResult


class AddRowTool:
    """Action tool that adds a terrain row at the bottom."""

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
        """Execute add row operation when activated."""
        # Get the row operations tool
        row_ops = context.tool_manager.get_tool("row_operations")
        if row_ops:
            # This will push undo and modify terrain
            row_ops.add_row(context, at_top=False)

    def on_deactivated(self, context: ToolContext):
        pass

    def reset(self):
        pass

    def get_hotkey(self):
        """Return '+' key (same as '=' key)."""
        return pygame.K_EQUALS

    def is_action_tool(self):
        """Identify this as an action tool."""
        return True
