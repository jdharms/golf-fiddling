"""
Fringe Generation Tool - Interactive path-based fringe tile generation.

Allows users to trace a path using arrow keys, then automatically generates
fringe tiles using neighbor frequency analysis and arc consistency.
"""

import pygame
from pygame import Rect

from editor.algorithms.fringe_generator import FringeGenerator
from editor.controllers.view_state import ViewState
from editor.core.constants import CANVAS_OFFSET_X, CANVAS_OFFSET_Y, STATUS_HEIGHT

from .base_tool import ToolContext, ToolResult

# Greens grid dimensions
GREENS_WIDTH = 24
GREENS_HEIGHT = 24
GREENS_PLACEHOLDER_TILE = 0x100

# Path constraints
MIN_PATH_LENGTH = 4  # Minimum tiles in path before loop closure allowed

# Arrow key to direction mapping
DIRECTION_KEYS = {
    pygame.K_UP: "up",
    pygame.K_DOWN: "down",
    pygame.K_LEFT: "left",
    pygame.K_RIGHT: "right",
}


class FringeToolState:
    """State for fringe generation pathing interaction."""

    def __init__(self):
        """Initialize pathing state."""
        # Pathing state
        self.is_active: bool = False
        self.initial_pos: tuple[int, int] | None = None  # (row, col) where path started
        self.current_pos: tuple[int, int] | None = None  # Current position in path
        self.path: list[tuple[int, int]] = []  # Ordered list of positions

        # Original tiles (for restoration on Escape)
        self.original_tiles: dict[tuple[int, int], int] = {}


class FringeGenerationTool:
    """
    Tool for generating fringe tiles using interactive path tracing.

    User clicks on a tile to start, uses arrow keys to draw a path,
    and the algorithm generates appropriate fringe tiles when the loop closes.
    """

    def __init__(self):
        """Initialize tool with fresh state and load fringe generation data."""
        self.state = FringeToolState()
        self.generator = FringeGenerator()
        self.generator.load_data()

    def handle_mouse_down(self, pos: tuple[int, int], button: int, modifiers: int, context: ToolContext) -> ToolResult:
        """Handle mouse click to start pathing."""
        # Only process in greens mode
        if context.state.mode != "greens":
            return ToolResult.not_handled()

        # Only left button
        if button != 1:
            return ToolResult.not_handled()

        # If already pathing, ignore clicks
        if self.state.is_active:
            return ToolResult.handled()

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

        # Convert screen to tile
        tile_pos = view_state.screen_to_tile(pos)
        if tile_pos is None:
            return ToolResult.not_handled()

        row, col = tile_pos

        # Start pathing
        self.state.is_active = True
        self.state.initial_pos = (row, col)
        self.state.current_pos = (row, col)
        self.state.path = [(row, col)]

        # Store original tile
        original_tile = context.hole_data.greens[row][col]
        self.state.original_tiles[(row, col)] = original_tile

        # Push undo state before generation
        context.state.undo_manager.push_state(context.hole_data)

        # Convert to placeholder if not already
        if original_tile != GREENS_PLACEHOLDER_TILE:
            context.hole_data.set_greens_tile(row, col, GREENS_PLACEHOLDER_TILE)

        # Update highlights
        self._update_highlights(context)

        return ToolResult.modified(message="Fringe path started - use arrow keys to trace")

    def handle_mouse_up(self, pos: tuple[int, int], button: int, context: ToolContext) -> ToolResult:
        """Handle mouse release (no-op for this tool)."""
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos: tuple[int, int], context: ToolContext) -> ToolResult:
        """Handle mouse motion (no-op for this tool)."""
        return ToolResult.not_handled()

    def handle_key_down(self, key: int, modifiers: int, context: ToolContext) -> ToolResult:
        """Handle keyboard input for path navigation."""
        # Only process if pathing is active
        if not self.state.is_active:
            return ToolResult.not_handled()

        # Arrow keys for navigation
        if key in DIRECTION_KEYS:
            # Perform move
            direction = DIRECTION_KEYS[key]
            return self._move_in_direction(direction, context)

        # Escape to cancel
        if key == pygame.K_ESCAPE:
            return self._cancel_pathing(context)

        # Tab passthrough for mode switching
        if key == pygame.K_TAB:
            return ToolResult.not_handled()

        return ToolResult.handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context: ToolContext):
        """Called when tool is activated."""
        self.reset()

    def on_deactivated(self, context: ToolContext):
        """Called when tool is deactivated."""
        # Clear highlights
        self._update_highlights(context)
        self.reset()

    def reset(self):
        """Reset tool state."""
        self.state = FringeToolState()

    def get_hotkey(self):
        """Return hotkey for activating this tool (None = no hotkey initially)."""
        return None

    def _update_highlights(self, context: ToolContext) -> None:
        """Update highlight state for current path."""
        if context.highlight_state is None:
            return

        if self.state.is_active:
            context.highlight_state.fringe_path = list(self.state.path)
            context.highlight_state.fringe_initial_pos = self.state.initial_pos
            context.highlight_state.fringe_current_pos = self.state.current_pos
        else:
            context.highlight_state.fringe_path = None
            context.highlight_state.fringe_initial_pos = None
            context.highlight_state.fringe_current_pos = None

    def _move_in_direction(self, direction: str, context: ToolContext) -> ToolResult:
        """
        Move current position in given direction and update path.

        Handles:
        - Backtracking (removing from path)
        - Loop completion (triggering generation)
        - Out of bounds (ignoring move)
        - Converting tiles to placeholders
        """
        if not self.state.is_active or self.state.current_pos is None:
            return ToolResult.not_handled()

        # Calculate new position
        row, col = self.state.current_pos
        deltas = {
            "up": (-1, 0),
            "down": (1, 0),
            "left": (0, -1),
            "right": (0, 1),
        }
        dr, dc = deltas[direction]
        new_row, new_col = row + dr, col + dc

        # Validate bounds (greens are 24x24)
        if not (0 <= new_row < GREENS_HEIGHT and 0 <= new_col < GREENS_WIDTH):
            return ToolResult.handled()  # Ignore out-of-bounds moves

        new_pos = (new_row, new_col)

        # Check for backtracking (moving back to previous position)
        if len(self.state.path) >= 2 and new_pos == self.state.path[-2]:
            # Remove last position from path
            removed_pos = self.state.path.pop()

            # Restore original tile if we have it
            if removed_pos in self.state.original_tiles:
                r, c = removed_pos
                original_tile = self.state.original_tiles[removed_pos]
                context.hole_data.set_greens_tile(r, c, original_tile)
                del self.state.original_tiles[removed_pos]

            # Update current position to previous
            self.state.current_pos = self.state.path[-1]

            # Update highlights
            self._update_highlights(context)

            return ToolResult.modified(message=f"Path length: {len(self.state.path)}")

        # Check for loop completion (returning to initial position)
        if len(self.state.path) >= MIN_PATH_LENGTH and new_pos == self.state.initial_pos:
            return self._generate_fringe(context)

        # Extend path to new position
        # Store original tile if not already stored
        if new_pos not in self.state.original_tiles:
            original_tile = context.hole_data.greens[new_row][new_col]
            self.state.original_tiles[new_pos] = original_tile

        # Convert to placeholder
        context.hole_data.set_greens_tile(new_row, new_col, GREENS_PLACEHOLDER_TILE)

        # Add to path
        self.state.path.append(new_pos)
        self.state.current_pos = new_pos

        # Update highlights
        self._update_highlights(context)

        return ToolResult.modified(message=f"Path length: {len(self.state.path)}")

    def _generate_fringe(self, context: ToolContext) -> ToolResult:
        """
        Generate fringe tiles using the traced path.

        Calls the FringeGenerator algorithm and applies results.
        """
        try:
            # Generate fringe tiles
            results = self.generator.generate(self.state.path)

            # Apply results
            for (row, col), tile_id in results:
                context.hole_data.set_greens_tile(row, col, tile_id)

            # Show success message
            num_tiles = len(results)
            message = f"Generated {num_tiles} fringe tile{'s' if num_tiles != 1 else ''}"

            # Clear state and highlights
            self.state = FringeToolState()
            self._update_highlights(context)

            # Revert to paint tool
            context.request_revert_to_previous_tool()

            return ToolResult.modified(message=message)

        except ValueError as e:
            error_msg = str(e)

            # Map technical errors to user-friendly messages
            if "Shape key not found" in error_msg:
                user_message = "Fringe shape not recognized - try a different path"
            elif "No valid candidates" in error_msg:  # Fixed typo
                user_message = "Could not generate fringe for this path - try a simpler shape"
            else:
                user_message = f"Fringe generation failed: {error_msg}"

            # Cancel pathing and show error to user
            self._cancel_pathing(context)
            return ToolResult(handled=True, message=user_message)

    def _cancel_pathing(self, context: ToolContext) -> ToolResult:
        """Cancel pathing and restore original tiles."""
        # Restore all original tiles
        for (row, col), original_tile in self.state.original_tiles.items():
            context.hole_data.set_greens_tile(row, col, original_tile)

        # Clear state and highlights
        self.state = FringeToolState()
        self._update_highlights(context)

        return ToolResult.modified(message="Fringe path cancelled")
