"""
Stamp tool for browsing and placing stamp patterns.
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
    TERRAIN_WIDTH,
)
from editor.data import StampData

from .base_tool import ToolContext, ToolResult


class StampToolState:
    """State for stamp tool."""

    def __init__(self):
        self.current_stamp: StampData | None = None
        self.preview_pos: tuple[int, int] | None = None  # (row, col)

    def set_stamp(self, stamp: StampData | None):
        """Set current stamp."""
        self.current_stamp = stamp

    def clear(self):
        """Clear stamp selection."""
        self.current_stamp = None
        self.preview_pos = None

    def reset(self):
        """Reset tool state."""
        self.clear()


class StampTool:
    """Stamp tool - browse and place stamp patterns."""

    def __init__(self):
        self.state = StampToolState()

    def handle_mouse_down(self, pos, button, modifiers, context):
        # Right click: Deselect stamp
        if button == 3:
            if self.state.current_stamp is not None:
                self.state.clear()
                context.highlight_state.stamp_preview_pos = None
                context.highlight_state.current_stamp = None
                return ToolResult(handled=True, message="Stamp: Deselected")
            return ToolResult.handled()

        if button != 1:  # Only left click
            return ToolResult.not_handled()

        # If no stamp selected, do nothing
        if self.state.current_stamp is None:
            return ToolResult(handled=True, message="Stamp: Select a stamp from the browser")

        # Check mode compatibility
        if self.state.current_stamp.mode != context.state.mode:
            return ToolResult(
                handled=True,
                message=f"Stamp: Cannot place {self.state.current_stamp.mode} stamp in {context.state.mode} mode",
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

        tile = view_state.screen_to_tile(pos)
        if not tile:
            return ToolResult.handled()

        # Place stamp
        return self._place_stamp(tile, context)

    def handle_mouse_up(self, pos, button, context):
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        # Update preview position
        if self.state.current_stamp is not None:
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
            if tile:
                self.state.preview_pos = tile
                # Update highlight state for rendering
                context.highlight_state.stamp_preview_pos = tile
                context.highlight_state.current_stamp = self.state.current_stamp
                return ToolResult.handled()

        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        # Esc: Clear stamp selection
        if key == pygame.K_ESCAPE:
            self.state.clear()
            context.highlight_state.stamp_preview_pos = None
            context.highlight_state.current_stamp = None
            return ToolResult(handled=True, message="Stamp: Cleared selection")

        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        """Called when tool becomes active."""
        # Clear any previous preview
        self.state.preview_pos = None
        context.highlight_state.stamp_preview_pos = None
        context.highlight_state.current_stamp = None

    def on_deactivated(self, context):
        """Called when tool is deactivated."""
        self.reset()
        # Clear highlight state
        context.highlight_state.stamp_preview_pos = None
        context.highlight_state.current_stamp = None

    def reset(self):
        """Reset tool state."""
        self.state.reset()

    def get_hotkey(self) -> int | None:
        """Return 'K' key for Stamp tool (K for "library")."""
        return pygame.K_k

    def set_stamp(self, stamp: StampData):
        """
        Set current stamp for placement.

        This is called by the stamp browser when user selects a stamp.
        """
        self.state.set_stamp(stamp)

    def _place_stamp(self, tile_pos: tuple[int, int], context: ToolContext) -> ToolResult:
        """
        Place stamp at tile position.

        Args:
            tile_pos: (row, col) position to place stamp
            context: Tool context

        Returns:
            ToolResult indicating success
        """
        if self.state.current_stamp is None:
            return ToolResult(handled=True, message="Stamp: No stamp selected")

        stamp = self.state.current_stamp
        place_row, place_col = tile_pos

        # Push undo state before modification
        context.state.undo_manager.push_state(context.hole_data)

        # Apply stamp tiles
        tiles_placed = 0
        for row_offset in range(stamp.height):
            for col_offset in range(stamp.width):
                target_row = place_row + row_offset
                target_col = place_col + col_offset

                tile_value = stamp.get_tile(row_offset, col_offset)

                # Skip transparent tiles (None values)
                if tile_value is None:
                    continue

                # Place based on mode
                if context.state.mode == "terrain":
                    if 0 <= target_row < len(context.hole_data.terrain) and 0 <= target_col < TERRAIN_WIDTH:
                        context.hole_data.set_terrain_tile(
                            target_row, target_col, tile_value
                        )
                        tiles_placed += 1
                else:  # greens
                    if 0 <= target_row < GREENS_HEIGHT and 0 <= target_col < GREENS_WIDTH:
                        context.hole_data.set_greens_tile(
                            target_row, target_col, tile_value
                        )
                        tiles_placed += 1

        stamp_name = stamp.get_display_name()
        return ToolResult.modified(
            terrain=(context.state.mode == "terrain"),
            message=f"Stamp: Placed '{stamp_name}' ({tiles_placed} tiles)",
        )
