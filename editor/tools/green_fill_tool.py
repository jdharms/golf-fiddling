"""
Green fill tool - fills exterior with rough tiles and interior with flat putting surface.
"""

import pygame

from editor.algorithms.green_fill import GreenFill

from .base_tool import ToolResult


class GreenFillTool:
    """Green fill tool - fills rough tiles outside fringe and flat tiles inside."""

    def __init__(self):
        self._filler = GreenFill()

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
        """Execute green fill when tool is activated (action tool)."""
        # Only works in greens mode
        if context.state.mode != "greens":
            return

        greens = context.hole_data.greens
        if not greens:
            return

        # Replace rough tiles with placeholders
        with_placeholders = self._replace_rough_with_placeholder(greens)

        # Run fill algorithm
        filled = self._filler.fill(with_placeholders)

        # Find changes
        changes = []
        for row_idx, (orig_row, filled_row) in enumerate(zip(greens, filled)):
            for col_idx, (orig_tile, filled_tile) in enumerate(zip(orig_row, filled_row)):
                if orig_tile != filled_tile:
                    changes.append((row_idx, col_idx, filled_tile))

        if not changes:
            return

        # Push undo state before applying
        context.state.undo_manager.push_state(context.hole_data)

        # Apply changes
        for row, col, tile in changes:
            context.hole_data.set_greens_tile(row, col, tile)

    def on_deactivated(self, context):
        pass

    def reset(self):
        pass

    def get_hotkey(self) -> int | None:
        """Return 'U' key for Green Fill tool."""
        return pygame.K_u

    def is_action_tool(self) -> bool:
        """Identify this as an action tool."""
        return True

    def _replace_rough_with_placeholder(
        self, greens: list[list[int]]
    ) -> list[list[int]]:
        """Replace all rough tiles with placeholder value."""
        result = []
        for row in greens:
            new_row = [
                GreenFill.PLACEHOLDER if tile in GreenFill.ROUGH_TILES else tile
                for tile in row
            ]
            result.append(new_row)
        return result
