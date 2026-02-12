"""Context compaction tool for flavIA.

Allows the agent to proactively compact the conversation context,
either autonomously or in response to natural language user requests.
"""

import json
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

# Sentinel prefix detected by RecursiveAgent._process_tool_calls_with_spawns()
COMPACT_SENTINEL = "__COMPACT_CONTEXT__"


class CompactContextTool(BaseTool):
    """Tool that lets the agent compact its own conversation context."""

    name = "compact_context"
    description = (
        "Compact the current conversation by summarizing it to free up context window space. "
        "Use this when context is running low, when the user asks to summarize or condense "
        "the conversation, or when you receive a system notice about context capacity."
    )
    category = "context"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="instructions",
                    type="string",
                    description=(
                        "Optional custom instructions for how to summarize the conversation. "
                        "Examples: 'focus on technical decisions', 'preserve all file paths', "
                        "'keep only the most recent tasks', "
                        "'summarize what was done and what is pending'."
                    ),
                    required=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        """Return a sentinel string for the agent loop to intercept and execute."""
        instructions = args.get("instructions", "")
        if instructions:
            payload = json.dumps({"instructions": instructions}, separators=(",", ":"))
            return f"{COMPACT_SENTINEL}:{payload}"
        return COMPACT_SENTINEL


register_tool(CompactContextTool())
