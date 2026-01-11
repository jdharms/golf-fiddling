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

        # Key repeat state (same pattern as PositionTool)
        self.held_key: int | None = None
        self.key_held_since: float | None = None
        self.last_repeat_time: float | None = None
        self.repeat_active: bool = False


class FringeGenerationTool:
    """
    Tool for generating fringe tiles using interactive path tracing.

    User clicks on a tile to start, uses arrow keys to draw a path,
    and the algorithm generates appropriate fringe tiles when the loop closes.
    """

    # Timing for key repeat (same as PositionTool)
    INITIAL_DELAY = 0.5  # 500ms delay before repeating starts
    REPEAT_INTERVAL = 0.05  # 50ms between repeats (20 moves/second)

    def __init__(self):
        """Initialize tool with fresh state and load fringe generation data."""
        self.state = FringeToolState()
        self.generator = FringeGenerator()
        self.generator.load_data()

    def handle_mouse_down(self, pos, button, modifiers, context: ToolContext):
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

        # Convert to placeholder if not already
        if original_tile != 0x100:
            context.hole_data.set_greens_tile(row, col, 0x100)

        # Update highlights
        context.highlight_state.fringe_initial_pos = (row, col)
        context.highlight_state.fringe_current_pos = (row, col)
        context.highlight_state.fringe_path = [(row, col)]

        return ToolResult.modified(message="Fringe path started - use arrow keys to trace")

    def handle_mouse_up(self, pos, button, context: ToolContext):
        """Handle mouse release (no-op for this tool)."""
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context: ToolContext):
        """Handle mouse motion (no-op for this tool)."""
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context: ToolContext):
        """Handle keyboard input for path navigation."""
        # Only process if pathing is active
        if not self.state.is_active:
            return ToolResult.not_handled()

        # Arrow keys for navigation
        if key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            # Start key repeat tracking
            self.state.held_key = key
            self.state.key_held_since = pygame.time.get_ticks() / 1000.0
            self.state.last_repeat_time = self.state.key_held_since
            self.state.repeat_active = False

            # Perform immediate move
            direction = {
                pygame.K_UP: "up",
                pygame.K_DOWN: "down",
                pygame.K_LEFT: "left",
                pygame.K_RIGHT: "right",
            }[key]
            return self._move_in_direction(direction, context)

        # Escape to cancel
        if key == pygame.K_ESCAPE:
            return self._cancel_pathing(context)

        # Tab passthrough for mode switching
        if key == pygame.K_TAB:
            return ToolResult.not_handled()

        return ToolResult.handled()

    def handle_key_up(self, key, context: ToolContext):
        """Handle key release to stop repeat."""
        if key == self.state.held_key:
            self.state.held_key = None
            self.state.key_held_since = None
            self.state.last_repeat_time = None
            self.state.repeat_active = False
        return ToolResult.not_handled()

    def update(self, context: ToolContext):
        """Handle key repeat timing (called every frame)."""
        if not self.state.is_active or self.state.held_key is None:
            return ToolResult.not_handled()

        current_time = pygame.time.get_ticks() / 1000.0
        time_held = current_time - self.state.key_held_since

        # Check if we should start repeating
        if not self.state.repeat_active and time_held >= self.INITIAL_DELAY:
            self.state.repeat_active = True
            self.state.last_repeat_time = current_time

        # Perform repeat if active
        if self.state.repeat_active:
            time_since_last = current_time - self.state.last_repeat_time
            if time_since_last >= self.REPEAT_INTERVAL:
                direction = {
                    pygame.K_UP: "up",
                    pygame.K_DOWN: "down",
                    pygame.K_LEFT: "left",
                    pygame.K_RIGHT: "right",
                }[self.state.held_key]
                self._move_in_direction(direction, context)
                self.state.last_repeat_time = current_time

        return ToolResult.not_handled()

    def on_activated(self, context: ToolContext):
        """Called when tool is activated."""
        self.reset()

    def on_deactivated(self, context: ToolContext):
        """Called when tool is deactivated."""
        # Clear highlights
        context.highlight_state.fringe_path = None
        context.highlight_state.fringe_initial_pos = None
        context.highlight_state.fringe_current_pos = None
        self.reset()

    def reset(self):
        """Reset tool state."""
        self.state = FringeToolState()

    def get_hotkey(self):
        """Return hotkey for activating this tool (None = no hotkey initially)."""
        return None

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
        if not (0 <= new_row < 24 and 0 <= new_col < 24):
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
            context.highlight_state.fringe_current_pos = self.state.current_pos
            context.highlight_state.fringe_path = list(self.state.path)

            return ToolResult.modified(message=f"Path length: {len(self.state.path)}")

        # Check for loop completion (returning to initial position)
        print(f"initial pos: {self.state.initial_pos}")
        if len(self.state.path) >= 4 and new_pos == self.state.initial_pos:
            print("completion")
            return self._generate_fringe(context)

        # Extend path to new position
        # Store original tile if not already stored
        if new_pos not in self.state.original_tiles:
            original_tile = context.hole_data.greens[new_row][new_col]
            self.state.original_tiles[new_pos] = original_tile

        # Convert to placeholder
        context.hole_data.set_greens_tile(new_row, new_col, 0x100)

        # Add to path
        self.state.path.append(new_pos)
        self.state.current_pos = new_pos

        # Update highlights
        context.highlight_state.fringe_current_pos = new_pos
        context.highlight_state.fringe_path = list(self.state.path)

        return ToolResult.modified(message=f"Path length: {len(self.state.path)}")

    def _generate_fringe(self, context: ToolContext) -> ToolResult:
        """
        Generate fringe tiles using the traced path.

        Calls the FringeGenerator algorithm and applies results.
        """
        # Push undo state before generation
        context.state.undo_manager.push_state(context.hole_data)

        try:
            # Generate fringe tiles
            results = self.generator.generate(self.state.path)

            print(results)

            # Apply results
            for (row, col), tile_id in results:
                context.hole_data.set_greens_tile(row, col, tile_id)

            # Clear state and highlights
            self.state = FringeToolState()
            context.highlight_state.fringe_path = None
            context.highlight_state.fringe_initial_pos = None
            context.highlight_state.fringe_current_pos = None

            # Revert to paint tool
            context.request_revert_to_previous_tool()

            return ToolResult.modified(message="Fringe generated successfully!")

        except ValueError as e:
            # Generation failed - show error but keep path active
            error_msg = str(e)
            if "Shape key not found" in error_msg:
                print("shape key not found")
                return ToolResult.handled()
            elif "No valid candidates" in error_msg:
                print("no valid canddiates")
                return ToolResult.handled()
            else:
                print(e)
                return ToolResult.handled()

    def _cancel_pathing(self, context: ToolContext) -> ToolResult:
        """Cancel pathing and restore original tiles."""
        # Restore all original tiles
        for (row, col), original_tile in self.state.original_tiles.items():
            context.hole_data.set_greens_tile(row, col, original_tile)

        # Clear state and highlights
        self.state = FringeToolState()
        context.highlight_state.fringe_path = None
        context.highlight_state.fringe_initial_pos = None
        context.highlight_state.fringe_current_pos = None

        # Revert to paint tool
        context.request_revert_to_previous_tool()

        return ToolResult.modified(message="Fringe path cancelled")
