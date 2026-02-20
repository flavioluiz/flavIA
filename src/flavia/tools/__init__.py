"""
Tools package for flavIA.

This module handles auto-registration of all tools.
Import this module to ensure all tools are registered.
"""

from .base import BaseTool, ToolSchema, ToolParameter
from .registry import ToolRegistry, registry, register_tool, get_registry

# Auto-register all tools by importing submodules
from . import read
from . import spawn
from . import content
from . import write
from . import academic
from . import compact
from . import research

__all__ = [
    "BaseTool",
    "ToolSchema",
    "ToolParameter",
    "ToolRegistry",
    "registry",
    "register_tool",
    "get_registry",
]


def list_available_tools() -> list[str]:
    """List all registered tool names."""
    return registry.list_tools()


def get_tool(name: str) -> BaseTool | None:
    """Get a tool by name."""
    return registry.get(name)
