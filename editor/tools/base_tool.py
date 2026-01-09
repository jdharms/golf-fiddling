"""
Tool protocol and base definitions for editor tools.
"""

from typing import Protocol


class Tool(Protocol):
    """Protocol defining the tool interface.

    Tools don't need to inherit from this - they just need to implement these methods.
    This provides duck typing with type checking support.
    """

    def handle_mouse_down(
        self, pos: tuple[int, int], button: int, modifiers: int, context: "ToolContext"
    ) -> "ToolResult":
        """Handle mouse button down event."""
        ...

    def handle_mouse_up(
        self, pos: tuple[int, int], button: int, context: "ToolContext"
    ) -> "ToolResult":
        """Handle mouse button up event."""
        ...

    def handle_mouse_motion(
        self, pos: tuple[int, int], context: "ToolContext"
    ) -> "ToolResult":
        """Handle mouse motion event."""
        ...

    def handle_key_down(
        self, key: int, modifiers: int, context: "ToolContext"
    ) -> "ToolResult":
        """Handle key down event (for tool-specific shortcuts)."""
        ...

    def handle_key_up(self, key: int, context: "ToolContext") -> "ToolResult":
        """Handle key up event."""
        ...

    def on_activated(self, context: "ToolContext") -> None:
        """Called when tool becomes active."""
        ...

    def on_deactivated(self, context: "ToolContext") -> None:
        """Called when tool is deactivated."""
        ...

    def reset(self) -> None:
        """Reset tool state."""
        ...

    def get_hotkey(self) -> int | None:
        """Return pygame key constant for this tool's activation hotkey.

        Returns None if tool has no hotkey.
        """
        ...


class ToolContext:
    """Context object providing tools access to application state.

    This acts as a facade, limiting what tools can access and preventing
    tight coupling to Application internals.
    """

    def __init__(
        self,
        hole_data,
        state,
        terrain_picker,
        greens_picker,
        transform_logic,
        forest_filler,
        screen_width: int,
        screen_height: int,
        tool_manager=None,
        highlight_state=None,
        stamp_library=None,
        on_revert_to_previous_tool=None,
        on_select_flag=None,
    ):
        self.hole_data = hole_data
        self.state = state
        self.terrain_picker = terrain_picker
        self.greens_picker = greens_picker
        self.transform_logic = transform_logic
        self.forest_filler = forest_filler
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.tool_manager = tool_manager
        self.highlight_state = highlight_state
        self.stamp_library = stamp_library
        self._on_revert_to_previous_tool = on_revert_to_previous_tool
        self._on_select_flag = on_select_flag

    def get_selected_tile(self) -> int:
        """Get currently selected tile based on mode."""
        if self.state.mode == "greens":
            return self.greens_picker.selected_tile
        else:
            return self.terrain_picker.selected_tile

    def set_selected_tile(self, tile: int) -> None:
        """Set selected tile based on mode."""
        if self.state.mode == "greens":
            self.greens_picker.selected_tile = tile
        else:
            self.terrain_picker.selected_tile = tile

    def get_eyedropper_tool(self):
        """Get eyedropper tool for delegation (used by Paint tool)."""
        if self.tool_manager:
            return self.tool_manager.get_tool("eyedropper")
        return None

    def request_revert_to_previous_tool(self):
        """Request that the application revert to the previously active tool.

        Used by dialog tools (like Metadata Editor) to automatically switch
        back to the previous tool after the dialog closes.
        """
        if self._on_revert_to_previous_tool:
            self._on_revert_to_previous_tool()

    def select_flag(self, index: int):
        """Request that the application change the visible flag.

        Used by tools (like PositionTool) to sync the visible flag with
        the currently selected position being edited.
        """
        if self._on_select_flag:
            self._on_select_flag(index)


class ToolResult:
    """Result of a tool operation."""

    def __init__(
        self,
        handled: bool = False,
        needs_undo_push: bool = False,
        needs_render: bool = False,
        terrain_modified: bool = False,
        message: str | None = None,
    ):
        self.handled = handled
        self.needs_undo_push = needs_undo_push
        self.needs_render = needs_render
        self.terrain_modified = terrain_modified
        self.message = message

    @staticmethod
    def handled() -> "ToolResult":
        """Event handled but no action needed."""
        return ToolResult(handled=True)

    @staticmethod
    def not_handled() -> "ToolResult":
        """Event not handled."""
        return ToolResult(handled=False)

    @staticmethod
    def modified(terrain: bool = False, message: str | None = None) -> "ToolResult":
        """Content was modified."""
        return ToolResult(
            handled=True,
            needs_undo_push=False,  # Tool handles undo timing
            needs_render=True,
            terrain_modified=terrain,
            message=message,
        )
