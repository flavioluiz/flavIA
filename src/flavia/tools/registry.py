"""Tool registry for flavIA."""

from typing import TYPE_CHECKING, Any, Optional

from .base import BaseTool, ToolSchema

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class ToolRegistry:
    """Centralized registry for all tools."""

    _instance: Optional["ToolRegistry"] = None
    _tools: dict[str, BaseTool]

    def __new__(cls) -> "ToolRegistry":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        if not tool.name:
            raise ValueError(f"Tool {tool.__class__.__name__} has no name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all(self) -> dict[str, BaseTool]:
        """Get all registered tools."""
        return self._tools.copy()

    def get_by_category(self, category: str) -> list[BaseTool]:
        """Get all tools in a category."""
        return [t for t in self._tools.values() if t.category == category]

    def get_available(self, agent_context: "AgentContext") -> list[BaseTool]:
        """Get tools available in current context."""
        return [
            t for t in self._tools.values()
            if t.is_available(agent_context)
        ]

    def build_schemas(
        self,
        tool_names: Optional[list[str]] = None,
        agent_context: Optional["AgentContext"] = None,
        **schema_context
    ) -> list[dict[str, Any]]:
        """Build OpenAI-compatible tool schemas."""
        schemas = []

        if tool_names:
            tools = [self._tools[n] for n in tool_names if n in self._tools]
        else:
            tools = list(self._tools.values())

        for tool in tools:
            if agent_context and not tool.is_available(agent_context):
                continue
            schema = tool.get_schema(**schema_context)
            schemas.append(schema.to_openai_schema())

        return schemas

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        agent_context: "AgentContext"
    ) -> str:
        """Execute a tool by name."""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")

        if not tool.is_available(agent_context):
            return f"Error: Tool '{name}' is not available in current context"

        is_valid, error = tool.validate_args(args)
        if not is_valid:
            return f"Error: {error}"

        return tool.execute(args, agent_context)

    def list_tools(self) -> list[str]:
        """Get list of all tool names."""
        return list(self._tools.keys())

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()


# Global registry instance
registry = ToolRegistry()


def register_tool(tool: BaseTool) -> BaseTool:
    """Register a tool."""
    registry.register(tool)
    return tool


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return registry
