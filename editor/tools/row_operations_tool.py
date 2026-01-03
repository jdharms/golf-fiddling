"""
Row operations tool - add and remove terrain rows.
"""

from .base_tool import ToolContext, ToolResult


class RowOperationsTool:
    """Tool for adding and removing terrain rows."""

    def __init__(self):
        pass

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

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        pass

    def reset(self):
        pass

    def add_row(self, context: ToolContext, at_top: bool = False) -> ToolResult:
        """Add terrain row with undo support."""
        # Push undo state before modification
        context.state.undo_manager.push_state(context.hole_data)

        # Add the row
        context.hole_data.add_terrain_row(at_top)

        # Return result indicating terrain was modified
        return ToolResult.modified(terrain=True)

    def remove_row(self, context: ToolContext, from_top: bool = False) -> ToolResult:
        """Remove terrain row with undo support."""
        # Prevent removing the last row
        if len(context.hole_data.terrain) <= 1:
            return ToolResult(handled=True, message="Cannot remove last terrain row")

        # Push undo state before modification
        context.state.undo_manager.push_state(context.hole_data)

        # Remove the row
        context.hole_data.remove_terrain_row(from_top)

        # Return result indicating terrain was modified
        return ToolResult.modified(terrain=True)
