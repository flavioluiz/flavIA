"""Spawn predefined agent tool for flavIA."""

import json
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class SpawnPredefinedAgentTool(BaseTool):
    """Tool for spawning predefined sub-agents from configuration."""

    name = "spawn_predefined_agent"
    description = "Spawn a pre-configured specialist sub-agent"
    category = "spawn"

    def get_schema(self, subagents: dict = None, **context) -> ToolSchema:
        agent_description = "Name of the predefined agent to spawn"
        agent_enum = None

        if subagents:
            agent_names = list(subagents.keys())
            descriptions = []
            for name, config in subagents.items():
                desc = config.get("context", "")[:50]
                descriptions.append(f"- {name}: {desc}...")

            agent_description = f"Available agents:\n" + "\n".join(descriptions)
            agent_enum = agent_names

        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="agent_name",
                    type="string",
                    description=agent_description,
                    required=True,
                    enum=agent_enum,
                ),
                ToolParameter(
                    name="task",
                    type="string",
                    description="The specific task for the agent to perform",
                    required=True,
                ),
            ]
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        agent_name = args.get("agent_name", "")
        task = args.get("task", "")

        if not agent_name:
            return "Error: agent_name is required"
        if not task:
            return "Error: task is required"

        subagents = agent_context.subagents or {}
        if agent_name not in subagents:
            available = list(subagents.keys())
            return f"Error: Unknown agent '{agent_name}'. Available: {', '.join(available)}"

        payload = {"agent_name": agent_name, "task": task}
        return f"__SPAWN_PREDEFINED__:{json.dumps(payload, separators=(',', ':'))}"

    def is_available(self, agent_context: "AgentContext") -> bool:
        has_subagents = bool(agent_context.subagents)
        not_at_max = agent_context.current_depth < agent_context.max_depth
        return has_subagents and not_at_max


register_tool(SpawnPredefinedAgentTool())
