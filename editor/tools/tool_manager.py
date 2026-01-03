"""
Tool manager for registering and switching between editor tools.
"""

from typing import Literal, overload

from .base_tool import Tool, ToolContext
from .eyedropper_tool import EyedropperTool
from .forest_fill_tool import ForestFillTool
from .paint_tool import PaintTool
from .row_operations_tool import RowOperationsTool
from .transform_tool import TransformTool


class ToolManager:
    """Manages tool registration and activation."""

    def __init__(self):
        self.tools: dict[str, Tool] = {}
        self.active_tool: Tool | None = None
        self.active_tool_name: str | None = None

    def register_tool(self, name: str, tool: Tool):
        """Register a tool with a name."""
        self.tools[name] = tool

    @overload
    def get_tool(self, name: Literal["paint"]) -> PaintTool | None: ...

    @overload
    def get_tool(self, name: Literal["transform"]) -> TransformTool | None: ...

    @overload
    def get_tool(self, name: Literal["eyedropper"]) -> EyedropperTool | None: ...

    @overload
    def get_tool(self, name: Literal["forest_fill"]) -> ForestFillTool | None: ...

    @overload
    def get_tool(self, name: Literal["row_operations"]) -> RowOperationsTool | None: ...

    def get_tool(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self.tools.get(name)

    def set_active_tool(self, name: str, context: ToolContext) -> bool:
        """Set the active tool by name."""
        if name not in self.tools:
            return False

        if self.active_tool and self.active_tool_name != name:
            self.active_tool.on_deactivated(context)

        self.active_tool = self.tools[name]
        self.active_tool_name = name
        self.active_tool.on_activated(context)

        return True

    def get_active_tool(self) -> Tool | None:
        """Get the currently active tool."""
        return self.active_tool

    def get_active_tool_name(self) -> str | None:
        """Get the name of the currently active tool."""
        return self.active_tool_name
