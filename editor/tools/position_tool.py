"""
Position tool for adjusting sprite positions (tee, green, flags) with arrow keys.

Provides lightweight direct manipulation of sprite positions without a dialog.
"""

import pygame

from .base_tool import ToolContext, ToolResult


class PositionTool:
    """
    Position tool - adjust sprite positions with arrow keys.

    Mode-aware: Shows all positions in terrain mode, only flags in greens mode.
    Smart undo: Pushes undo state once per position (not per keystroke).
    """

    def __init__(self):
        self.selected_position_index: int = 0
        self.undo_position_tracker: str | None = None  # Track which position has undo state

    def _get_available_positions(self, mode: str) -> list[str]:
        """Return positions available in current mode."""
        if mode == "terrain":
            return ["tee", "green", "flag1", "flag2", "flag3", "flag4"]
        else:  # greens mode
            return ["flag1", "flag2", "flag3", "flag4"]  # Only flags in greens mode

    def _ensure_metadata_exists(self, hole_data):
        """Ensure required metadata exists with defaults."""
        # Ensure tee position exists
        if "tee" not in hole_data.metadata:
            hole_data.metadata["tee"] = {"x": 0, "y": 0}

        # Ensure flag_positions list exists with 4 entries
        if "flag_positions" not in hole_data.metadata:
            hole_data.metadata["flag_positions"] = []
        while len(hole_data.metadata["flag_positions"]) < 4:
            hole_data.metadata["flag_positions"].append({"x_offset": 0, "y_offset": 0})

    def _get_position_coords(self, pos_name: str, hole_data) -> tuple[int, int]:
        """Get pixel coordinates for a given position."""
        if pos_name == "tee":
            tee = hole_data.metadata.get("tee", {"x": 0, "y": 0})
            return tee.get("x", 0), tee.get("y", 0)
        elif pos_name == "green":
            return hole_data.green_x, hole_data.green_y
        elif pos_name.startswith("flag"):
            idx = int(pos_name[-1]) - 1  # flag1 -> index 0
            flags = hole_data.metadata.get("flag_positions", [])
            if 0 <= idx < len(flags):
                return flags[idx].get("x_offset", 0), flags[idx].get("y_offset", 0)
            return 0, 0
        return 0, 0

    def _adjust_position(self, pos_name: str, dx: int, dy: int, hole_data):
        """
        Adjust position by delta (in tiles, 8 pixels each).

        Args:
            pos_name: Position to adjust ("tee", "green", "flag1", etc.)
            dx: Delta in tiles (right = +1)
            dy: Delta in tiles (down = +1)
            hole_data: HoleData to modify
        """
        dx_pixels = dx
        dy_pixels = dy

        if pos_name == "tee":
            hole_data.metadata["tee"]["x"] += dx_pixels
            hole_data.metadata["tee"]["y"] += dy_pixels
        elif pos_name == "green":
            hole_data.green_x += dx_pixels
            hole_data.green_y += dy_pixels
        elif pos_name.startswith("flag"):
            idx = int(pos_name[-1]) - 1
            flags = hole_data.metadata["flag_positions"]
            if 0 <= idx < len(flags):
                flags[idx]["x_offset"] += dx_pixels
                flags[idx]["y_offset"] += dy_pixels

        hole_data.modified = True

    def _get_status_message(self, pos_name: str, hole_data) -> str:
        """Generate status bar message for current position."""
        x, y = self._get_position_coords(pos_name, hole_data)
        return f"Position: {pos_name.title()} ({x}, {y}) - Use arrows to adjust, Tab to cycle"

    def handle_mouse_down(self, pos, button, modifiers, context):
        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        available_positions = self._get_available_positions(context.state.mode)
        current_position = available_positions[self.selected_position_index]

        # Handle position cycling (Tab or brackets)
        if key == pygame.K_TAB and not (modifiers & pygame.KMOD_SHIFT):
            # Tab: next position
            self.selected_position_index = (self.selected_position_index + 1) % len(available_positions)
            current_position = available_positions[self.selected_position_index]
            context.highlight_state.position_tool_selected = current_position
            message = self._get_status_message(current_position, context.hole_data)
            return ToolResult(handled=True, message=message)

        elif key == pygame.K_LEFTBRACKET or (key == pygame.K_TAB and (modifiers & pygame.KMOD_SHIFT)):
            # [ or Shift+Tab: previous position
            self.selected_position_index = (self.selected_position_index - 1) % len(available_positions)
            current_position = available_positions[self.selected_position_index]
            context.highlight_state.position_tool_selected = current_position
            message = self._get_status_message(current_position, context.hole_data)
            return ToolResult(handled=True, message=message)

        elif key == pygame.K_RIGHTBRACKET:
            # ]: next position
            self.selected_position_index = (self.selected_position_index + 1) % len(available_positions)
            current_position = available_positions[self.selected_position_index]
            context.highlight_state.position_tool_selected = current_position
            message = self._get_status_message(current_position, context.hole_data)
            return ToolResult(handled=True, message=message)

        # Handle arrow keys for position adjustment
        elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            # Smart undo: push state on first arrow for this position
            if self.undo_position_tracker != current_position:
                context.state.undo_manager.push_state(context.hole_data)
                self.undo_position_tracker = current_position

            # Calculate delta
            dx, dy = 0, 0
            if key == pygame.K_LEFT:
                dx = -1
            elif key == pygame.K_RIGHT:
                dx = 1
            elif key == pygame.K_UP:
                dy = -1
            elif key == pygame.K_DOWN:
                dy = 1

            # Adjust position
            self._adjust_position(current_position, dx, dy, context.hole_data)

            # Get updated message
            message = self._get_status_message(current_position, context.hole_data)

            return ToolResult.modified(message=message)

        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        """Called when tool becomes active."""
        # Ensure metadata exists
        self._ensure_metadata_exists(context.hole_data)

        # Get available positions for current mode
        available_positions = self._get_available_positions(context.state.mode)

        # Reset selection to first available position
        self.selected_position_index = 0
        current_position = available_positions[self.selected_position_index]

        # Reset undo tracker
        self.undo_position_tracker = None

        # Set highlight state
        context.highlight_state.position_tool_selected = current_position

    def on_deactivated(self, context):
        """Called when tool is deactivated."""
        # Clear highlight state
        context.highlight_state.position_tool_selected = None

        # Reset undo tracker
        self.undo_position_tracker = None

    def reset(self):
        """Reset tool state."""
        self.selected_position_index = 0
        self.undo_position_tracker = None

    def get_hotkey(self) -> int | None:
        """Return 'R' key for Reposition."""
        return pygame.K_r
