"""
Tool manager for registering and switching between editor tools.
"""

from typing import Dict, Optional
from .base_tool import Tool, ToolContext


class ToolManager:
    """Manages tool registration and activation."""

    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.active_tool: Optional[Tool] = None
        self.active_tool_name: Optional[str] = None

    def register_tool(self, name: str, tool: Tool):
        """Register a tool with a name."""
        self.tools[name] = tool

    def get_tool(self, name: str) -> Optional[Tool]:
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

    def get_active_tool(self) -> Optional[Tool]:
        """Get the currently active tool."""
        return self.active_tool

    def get_active_tool_name(self) -> Optional[str]:
        """Get the name of the currently active tool."""
        return self.active_tool_name
