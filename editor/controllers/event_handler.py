"""
NES Open Tournament Golf - Event Handler

Handles user input events including mouse, keyboard, and window events.
"""

from collections.abc import Callable

import pygame
from pygame import Rect

from editor.core.constants import (
    CANVAS_OFFSET_X,
    CANVAS_OFFSET_Y,
    STATUS_HEIGHT,
)
from editor.ui.pickers import GreensTilePicker, TilePicker
from editor.ui.widgets import Button
from golf.formats.hole_data import HoleData

from .editor_state import EditorState


class EventHandler:
    """Handles all user input events."""

    def __init__(
        self,
        state: EditorState,
        hole_data: HoleData,
        terrain_picker: TilePicker,
        greens_picker: GreensTilePicker,
        buttons: list[Button],
        screen_width: int,
        screen_height: int,
        tool_manager,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        on_mode_change: Callable[[], None],
        on_flag_change: Callable[[], None],
        on_resize: Callable[[int, int], None],
        on_terrain_modified: Callable[[], None] | None = None,
    ):
        """
        Initialize event handler.

        Args:
            state: Editor state
            hole_data: Hole data
            terrain_picker: Terrain tile picker
            greens_picker: Greens tile picker
            buttons: List of UI buttons
            screen_width: Screen width
            screen_height: Screen height
            tool_manager: Tool manager for handling tools
            on_load: Callback for load action
            on_save: Callback for save action
            on_mode_change: Callback when mode changes
            on_flag_change: Callback when flag selection changes
            on_resize: Callback for window resize (width, height)
            on_terrain_modified: Callback when terrain is modified
        """
        self.state = state
        self.hole_data = hole_data
        self.terrain_picker = terrain_picker
        self.greens_picker = greens_picker
        self.buttons = buttons
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.tool_manager = tool_manager
        self.on_load = on_load
        self.on_save = on_save
        self.on_mode_change = on_mode_change
        self.on_flag_change = on_flag_change
        self.on_resize = on_resize
        self.on_terrain_modified = on_terrain_modified

        # Create tool context (will be updated by Application with transform_logic and forest_filler)
        from editor.tools.base_tool import ToolContext

        self.tool_context = ToolContext(
            hole_data=hole_data,
            state=state,
            terrain_picker=terrain_picker,
            greens_picker=greens_picker,
            transform_logic=None,  # Will be set by Application
            forest_filler=None,  # Will be set by Application
            screen_width=screen_width,
            screen_height=screen_height,
        )

    def update_screen_size(self, width: int, height: int):
        """Update screen dimensions."""
        self.screen_width = width
        self.screen_height = height

    def handle_events(self, events: list[pygame.event.Event]) -> bool:
        """
        Handle all pygame events.

        Args:
            events: List of pygame events to process

        Returns:
            True if application should continue running, False if quit requested
        """
        for event in events:
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if not self._handle_global_keys(event):
                    # Let active tool handle key events (for tool-specific shortcuts like Ctrl+F)
                    tool = self.tool_manager.get_active_tool()
                    if tool:
                        modifiers = pygame.key.get_mods()
                        result = tool.handle_key_down(
                            event.key, modifiers, self.tool_context
                        )
                        self._process_tool_result(result)

            elif event.type == pygame.KEYUP:
                # Let tools handle key up (e.g., transform cancels on shift release)
                tool = self.tool_manager.get_active_tool()
                if tool:
                    result = tool.handle_key_up(event.key, self.tool_context)
                    self._process_tool_result(result)
                # Also check transform tool specifically for shift release
                transform_tool = self.tool_manager.get_tool("transform")
                if (
                    transform_tool
                    and hasattr(transform_tool, "state")
                    and transform_tool.state.is_active
                ):
                    result = transform_tool.handle_key_up(event.key, self.tool_context)
                    self._process_tool_result(result)

            # Handle button events
            button_handled = False
            for button in self.buttons:
                if button.handle_event(event):
                    button_handled = True
                    break  # Stop after first button handles it

            # Handle picker events
            picker_handled = False
            if self.state.mode == "greens":
                picker_handled = self.greens_picker.handle_event(event)
            else:
                picker_handled = self.terrain_picker.handle_event(event)

            # Handle canvas events (only if button/picker didn't handle)
            if event.type == pygame.MOUSEBUTTONDOWN and not (
                button_handled or picker_handled
            ):
                modifiers = pygame.key.get_mods()

                # Try transform tool first if shift held
                if modifiers & pygame.KMOD_SHIFT:
                    transform_tool = self.tool_manager.get_tool("transform")
                    if transform_tool:
                        result = transform_tool.handle_mouse_down(
                            event.pos, event.button, modifiers, self.tool_context
                        )
                        if result.handled:
                            self._process_tool_result(result)
                            continue

                # Try eyedropper on right click
                if event.button == 3:
                    eyedropper_tool = self.tool_manager.get_tool("eyedropper")
                    if eyedropper_tool:
                        result = eyedropper_tool.handle_mouse_down(
                            event.pos, event.button, modifiers, self.tool_context
                        )
                        if result.handled:
                            self._process_tool_result(result)
                            continue

                # Handle scrolling
                if event.button == 4:  # Scroll up
                    self.state.canvas_offset_y = max(0, self.state.canvas_offset_y - 20)
                    continue
                elif event.button == 5:  # Scroll down
                    self.state.canvas_offset_y += 20
                    continue

                # Default to active tool (paint)
                tool = self.tool_manager.get_active_tool()
                if tool:
                    result = tool.handle_mouse_down(
                        event.pos, event.button, modifiers, self.tool_context
                    )
                    self._process_tool_result(result)

            elif event.type == pygame.MOUSEBUTTONUP and not picker_handled:
                # Check transform first (might be active)
                transform_tool = self.tool_manager.get_tool("transform")
                if (
                    transform_tool
                    and hasattr(transform_tool, "state")
                    and transform_tool.state.is_active
                ):
                    result = transform_tool.handle_mouse_up(
                        event.pos, event.button, self.tool_context
                    )
                    self._process_tool_result(result)
                    continue

                # Otherwise delegate to active tool
                tool = self.tool_manager.get_active_tool()
                if tool:
                    result = tool.handle_mouse_up(
                        event.pos, event.button, self.tool_context
                    )
                    self._process_tool_result(result)

            elif event.type == pygame.MOUSEMOTION:
                # Check if transform is active
                transform_tool = self.tool_manager.get_tool("transform")
                if (
                    transform_tool
                    and hasattr(transform_tool, "state")
                    and transform_tool.state.is_active
                ):
                    result = transform_tool.handle_mouse_motion(
                        event.pos, self.tool_context
                    )
                    self._process_tool_result(result)
                    continue

                # Otherwise delegate to active tool
                tool = self.tool_manager.get_active_tool()
                if tool:
                    result = tool.handle_mouse_motion(event.pos, self.tool_context)
                    self._process_tool_result(result)

            elif event.type == pygame.VIDEORESIZE:
                self.on_resize(event.w, event.h)

        return True

    def _process_tool_result(self, result):
        """Process a tool result and trigger necessary callbacks."""
        if result.terrain_modified and self.on_terrain_modified:
            self.on_terrain_modified()

        if result.message:
            print(result.message)  # TODO: Better status display

    def _handle_global_keys(self, event) -> bool:
        """Handle keyboard input."""
        if event.key == pygame.K_g:
            self.state.toggle_grid()

        elif event.key == pygame.K_1:
            self.state.selected_palette = 1
        elif event.key == pygame.K_2:
            self.state.selected_palette = 2
        elif event.key == pygame.K_3:
            self.state.selected_palette = 3

        elif event.key == pygame.K_TAB:
            # Cycle modes
            modes = ["terrain", "palette", "greens"]
            idx = modes.index(self.state.mode)
            self.state.set_mode(modes[(idx + 1) % len(modes)])
            self.on_mode_change()

        elif event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.on_save()
        elif event.key == pygame.K_o and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.on_load()
        elif event.key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                # Ctrl+Shift+Z = Redo (alternative to Ctrl+Y)
                self._redo()
            else:
                # Ctrl+Z = Undo
                self._undo()
        elif event.key == pygame.K_y and pygame.key.get_mods() & pygame.KMOD_CTRL:
            # Ctrl+Y = Redo
            self._redo()
        elif event.key == pygame.K_x and pygame.key.get_mods() & pygame.KMOD_CTRL:
            # Ctrl+X = Toggle invalid tile highlighting
            self.state.toggle_invalid_tiles()
        elif event.key == pygame.K_f and pygame.key.get_mods() & pygame.KMOD_CTRL:
            # Ctrl+F = Forest fill
            forest_fill_tool = self.tool_manager.get_tool("forest_fill")
            if forest_fill_tool:
                result = forest_fill_tool.handle_key_down(
                    event.key, pygame.key.get_mods(), self.tool_context
                )
                self._process_tool_result(result)

        elif event.key == pygame.K_LEFT:
            self.state.canvas_offset_x = max(0, self.state.canvas_offset_x - 20)
        elif event.key == pygame.K_RIGHT:
            self.state.canvas_offset_x += 20
        elif event.key == pygame.K_UP:
            self.state.canvas_offset_y = max(0, self.state.canvas_offset_y - 20)
        elif event.key == pygame.K_DOWN:
            self.state.canvas_offset_y += 20

        elif event.key == pygame.K_LEFTBRACKET:  # [
            # Previous flag position
            if self.hole_data.metadata.get("flag_positions"):
                num_flags = len(self.hole_data.metadata["flag_positions"])
                self.state.selected_flag_index = (
                    self.state.selected_flag_index - 1
                ) % num_flags
                self.on_flag_change()

        elif event.key == pygame.K_RIGHTBRACKET:  # ]
            # Next flag position
            if self.hole_data.metadata.get("flag_positions"):
                num_flags = len(self.hole_data.metadata["flag_positions"])
                self.state.selected_flag_index = (
                    self.state.selected_flag_index + 1
                ) % num_flags
                self.on_flag_change()

        elif event.key == pygame.K_v:  # Toggle sprites (V for "view")
            self.state.toggle_sprites()
        else:
            # Key not handled by global handler
            return False

        # Key was handled
        return True

    def _get_canvas_rect(self) -> Rect:
        """Get the canvas drawing area."""
        return Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            self.screen_width - CANVAS_OFFSET_X,
            self.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT,
        )

    def _undo(self):
        """Undo last action."""
        if self.state.undo_manager.can_undo():
            previous_state = self.state.undo_manager.undo(self.hole_data)
            if previous_state:
                self._restore_hole_data(previous_state)
                # Invalidate terrain validation cache
                if self.on_terrain_modified:
                    self.on_terrain_modified()

    def _redo(self):
        """Redo last undone action."""
        if self.state.undo_manager.can_redo():
            next_state = self.state.undo_manager.redo(self.hole_data)
            if next_state:
                self._restore_hole_data(next_state)
                # Invalidate terrain validation cache
                if self.on_terrain_modified:
                    self.on_terrain_modified()

    def _restore_hole_data(self, snapshot: HoleData):
        """Restore hole data from snapshot."""
        self.hole_data.terrain = snapshot.terrain
        self.hole_data.attributes = snapshot.attributes
        self.hole_data.greens = snapshot.greens
        self.hole_data.green_x = snapshot.green_x
        self.hole_data.green_y = snapshot.green_y
        self.hole_data.metadata = snapshot.metadata
        self.hole_data.modified = True  # Restoring counts as modification
