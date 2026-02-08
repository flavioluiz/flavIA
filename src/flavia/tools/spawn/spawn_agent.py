"""Spawn agent tool for flavIA."""

import json
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class SpawnAgentTool(BaseTool):
    """Tool for spawning dynamic sub-agents."""

    name = "spawn_agent"
    description = "Create a specialized sub-agent to handle a specific task"
    category = "spawn"

    def get_schema(self, models: list = None, **context) -> ToolSchema:
        model_description = "Model to use for the sub-agent"
        model_enum = None

        if models:
            model_names = [m.name for m in models]
            model_description = f"Model to use. Available: {', '.join(model_names)}"
            model_enum = [str(i) for i in range(len(models))] + [m.id for m in models]

        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="task",
                    type="string",
                    description="Clear description of the task for the sub-agent",
                    required=True,
                ),
                ToolParameter(
                    name="context",
                    type="string",
                    description="System context/persona for the sub-agent",
                    required=True,
                ),
                ToolParameter(
                    name="model",
                    type="string",
                    description=model_description,
                    required=False,
                    enum=model_enum,
                ),
                ToolParameter(
                    name="tools",
                    type="array",
                    description="List of tools the sub-agent can use",
                    required=False,
                    items={"type": "string"},
                ),
            ]
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        task = args.get("task", "")
        context = args.get("context", "")
        model = args.get("model")
        tools = args.get("tools")

        if not task:
            return "Error: task is required"
        if not context:
            return "Error: context is required"

        payload: dict[str, Any] = {
            "task": task,
            "context": context,
        }
        if model:
            payload["model"] = model
        if tools:
            payload["tools"] = tools

        return f"__SPAWN_AGENT__:{json.dumps(payload, separators=(',', ':'))}"

    def is_available(self, agent_context: "AgentContext") -> bool:
        return agent_context.current_depth < agent_context.max_depth


register_tool(SpawnAgentTool())
