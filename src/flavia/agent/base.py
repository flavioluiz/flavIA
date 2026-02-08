"""Base agent class for flavIA."""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from openai import OpenAI

from flavia.config import Settings
from flavia.tools import registry

from .context import AgentContext, build_system_prompt, build_tools_description
from .profile import AgentProfile


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    def __init__(
        self,
        settings: Settings,
        profile: AgentProfile,
        agent_id: str = "main",
        depth: int = 0,
        parent_id: Optional[str] = None,
    ):
        self.settings = settings
        self.profile = profile
        self.model_id = settings.resolve_model(profile.model)

        self.context = AgentContext.from_profile(
            profile=profile,
            agent_id=agent_id,
            depth=depth,
            parent_id=parent_id,
            resolved_model=self.model_id,
        )

        self.client = self._create_openai_client()

        self.tool_schemas = self._build_tool_schemas()
        self.messages: list[dict[str, Any]] = []
        self._init_system_prompt()

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        """Build OpenAI tool schemas for available tools."""
        return registry.build_schemas(
            tool_names=self.profile.tools if self.profile.tools else None,
            agent_context=self.context,
            models=self.settings.models,
            subagents=self.profile.subagents,
        )

    def _create_openai_client(self) -> OpenAI:
        """Create OpenAI client with compatibility fallback for older SDK versions."""
        kwargs = {
            "api_key": self.settings.api_key,
            "base_url": self.settings.api_base_url,
        }
        try:
            return OpenAI(**kwargs)
        except TypeError as exc:
            if "unexpected keyword argument 'proxies'" not in str(exc):
                raise
            # Compatibility fallback for environments where OpenAI SDK and httpx versions mismatch.
            return OpenAI(**kwargs, http_client=httpx.Client())

    def _init_system_prompt(self) -> None:
        """Initialize the system prompt."""
        tools_desc = build_tools_description(self.tool_schemas)
        system_prompt = build_system_prompt(
            self.profile,
            self.context,
            tools_desc,
        )
        self.messages = [{"role": "system", "content": system_prompt}]

    def reset(self) -> None:
        """Reset agent state for new conversation."""
        self._init_system_prompt()

    def _call_llm(self, messages: list[dict[str, Any]]) -> Any:
        """Call the LLM with messages."""
        kwargs = {
            "model": self.model_id,
            "messages": messages,
        }

        if self.tool_schemas:
            kwargs["tools"] = self.tool_schemas
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message

    def _assistant_message_to_dict(self, message: Any) -> dict[str, Any]:
        """Normalize assistant message to API-safe chat message dict."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": message.content if message.content is not None else "",
        }

        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            normalized_calls = []
            for call in tool_calls:
                fn = getattr(call, "function", None)
                normalized_calls.append({
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": fn.name if fn else "",
                        "arguments": fn.arguments if fn else "{}",
                    },
                })
            msg["tool_calls"] = normalized_calls

        return msg

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool by name."""
        return registry.execute(name, args, self.context)

    def _process_tool_calls(self, tool_calls: list[Any]) -> list[dict[str, Any]]:
        """Process tool calls from LLM response."""
        results = []

        for tool_call in tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            if self.settings.verbose:
                print(f"[{self.context.agent_id}] Tool: {name}({args})")

            result = self._execute_tool(name, args)
            result = self._handle_spawn_result(result, name, args)

            results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        return results

    def _handle_spawn_result(self, result: str, tool_name: str, args: dict) -> str:
        """Handle special spawn results. Override in subclasses."""
        return result

    @abstractmethod
    def run(self, user_message: str) -> str:
        """Run the agent with a user message."""
        pass

    def log(self, message: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.settings.verbose:
            print(f"[{self.context.agent_id}] {message}")
