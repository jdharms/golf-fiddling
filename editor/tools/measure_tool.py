"""
Measure tool - measure distances between points in yards.
"""

import math
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

    def _calculate_cumulative_distance(self) -> float:
        """Calculate cumulative distance in yards between all consecutive points."""
        if len(self.points) < 2:
            return 0.0

        total_yards = 0.0
        for i in range(len(self.points) - 1):
            p1 = self.points[i]
            p2 = self.points[i + 1]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            segment_yards = math.sqrt(dx * dx + dy * dy) * 2
            total_yards += segment_yards

        return total_yards

    def _get_status_message(self) -> str:
        """Generate status bar message showing measurement info."""
        num_points = len(self.points)
        if num_points == 0:
            return "Measure: Click to add points, Right-click to clear"
        elif num_points == 1:
            return "Measure: 1 point - Click to add more points"
        else:
            total_distance = self._calculate_cumulative_distance()
            return f"Total Distance: {total_distance:.1f}y"

    def handle_mouse_down(self, pos, button, modifiers, context):
        """Handle mouse click - add point or clear points."""
        if context.state.mode != "terrain":
            return ToolResult.not_handled()

        # Right click - clear all points
        if button == 3:
            self.points.clear()
            message = self._get_status_message()
            return ToolResult(handled=True, message=message)

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

        # Return status message with cumulative distance
        message = self._get_status_message()
        return ToolResult(handled=True, message=message)

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
        """Called when tool becomes active - show initial status message."""
        context.state.tool_message = self._get_status_message()

    def on_deactivated(self, context):
        """Called when tool is deactivated - clear points and status message."""
        self.reset()
        context.state.tool_message = None

    def reset(self):
        """Reset tool state - clear all measurement points."""
        self.points.clear()

    def get_hotkey(self) -> int | None:
        """Return 'M' key for Measure tool."""
        return pygame.K_m
