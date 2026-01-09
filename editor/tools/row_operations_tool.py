"""
Row operations tool - add and remove terrain rows.
"""

from golf.formats.hole_data import HoleData

from .base_tool import ToolContext, ToolResult


def _update_scroll_limit(hole_data: HoleData):
    """Update scroll_limit based on terrain_height using formula: (height - 28) / 2."""
    scroll_limit = (hole_data.terrain_height - 28) // 2
    hole_data.metadata["scroll_limit"] = max(0, scroll_limit)
    hole_data.modified = True


class RowOperationsTool:
    """Tool for adding and removing terrain rows (in pairs of 2)."""

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

    def get_hotkey(self) -> int | None:
        return None

    def add_row(self, context: ToolContext, at_top: bool = False) -> ToolResult:
        """Add TWO terrain rows with undo support.

        Constraints:
        - Maximum 48 rows
        - Add in pairs (2 rows at a time)
        - Restore hidden rows before creating new ones
        - Update scroll_limit after operation
        """
        hole_data = context.hole_data

        # Check maximum constraint
        if hole_data.terrain_height >= 48:
            return ToolResult(handled=True, message="Cannot exceed 48 rows")

        if hole_data.terrain_height + 2 > 48:
            return ToolResult(
                handled=True, message="Would exceed 48 row limit (can only add in pairs of 2)"
            )

        # Push undo state before modification
        context.state.undo_manager.push_state(hole_data)

        # Check if we can restore hidden rows first
        physical_row_count = len(hole_data.terrain)
        rows_to_restore = min(2, physical_row_count - hole_data.terrain_height)

        if rows_to_restore > 0:
            # Restore hidden rows by increasing height
            hole_data.terrain_height += rows_to_restore

        # If we still need more rows (restored fewer than 2), add physical rows
        rows_still_needed = 2 - rows_to_restore
        for _ in range(rows_still_needed):
            hole_data.add_terrain_row(at_top)
            hole_data.terrain_height += 1

        # Update scroll limit
        _update_scroll_limit(hole_data)

        # Return result indicating terrain was modified
        return ToolResult.modified(terrain=True)

    def remove_row(self, context: ToolContext, from_top: bool = False) -> ToolResult:
        """Remove TWO terrain rows with undo support (soft removal).

        Constraints:
        - Minimum 30 rows
        - Remove in pairs (2 rows at a time)
        - Soft removal: decrease terrain_height, keep data
        - Update scroll_limit after operation
        """
        hole_data = context.hole_data

        # Check minimum constraint
        if hole_data.terrain_height <= 30:
            return ToolResult(handled=True, message="Cannot have fewer than 30 rows")

        # Push undo state before modification
        context.state.undo_manager.push_state(hole_data)

        # Soft removal: decrease height by 2, keep physical data
        hole_data.terrain_height -= 2

        # Update scroll limit
        _update_scroll_limit(hole_data)

        # Return result indicating terrain was modified
        return ToolResult.modified(terrain=True)
