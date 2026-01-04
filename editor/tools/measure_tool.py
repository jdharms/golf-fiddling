"""
Measure tool - measure distances between points in yards.
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


class MeasureTool:
    """Measure tool - click to add measurement points, right-click to clear."""

    def __init__(self):
        """Initialize measure tool with empty points list."""
        self.points: list[tuple[int, int]] = []  # Game pixel coordinates

    def handle_mouse_down(self, pos, button, modifiers, context):
        """Handle mouse click - add point or clear points."""
        if context.state.mode != "terrain":
            return ToolResult.not_handled()

        # Right click - clear all points
        if button == 3:
            self.points.clear()
            return ToolResult.handled()

        # Only handle left click
        if button != 1:
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

        # Convert screen position to game pixel coordinates
        game_pixel_pos = view_state.screen_to_game_pixels(pos)
        if not game_pixel_pos:
            return ToolResult.handled()

        # Add point to measurement sequence
        self.points.append(game_pixel_pos)

        return ToolResult.handled()

    def handle_mouse_up(self, pos, button, context):
        """Handle mouse release - not used by measure tool."""
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        """Handle mouse motion - not used by measure tool."""
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        """Handle key press - not used by measure tool."""
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        """Handle key release - not used by measure tool."""
        return ToolResult.not_handled()

    def on_activated(self, context):
        """Called when tool becomes active."""
        pass

    def on_deactivated(self, context):
        """Called when tool is deactivated - clear points for clean state."""
        self.reset()

    def reset(self):
        """Reset tool state - clear all measurement points."""
        self.points.clear()

    def get_hotkey(self) -> int | None:
        """Return 'M' key for Measure tool."""
        return pygame.K_m
