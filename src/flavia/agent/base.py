"""Base agent class for flavIA."""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from openai import OpenAI, APIConnectionError, AuthenticationError, APITimeoutError, APIStatusError

from flavia.config import Settings, ProviderConfig
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

        # Resolve provider and model using new multi-provider system
        self.provider, self.model_id = settings.resolve_model_with_provider(profile.model)

        self.context = AgentContext.from_profile(
            profile=profile,
            agent_id=agent_id,
            depth=depth,
            parent_id=parent_id,
            resolved_model=self.model_id,
        )

        self.client = self._create_openai_client(self.provider)

        self.tool_schemas = self._build_tool_schemas()
        self.messages: list[dict[str, Any]] = []

        # Token usage tracking
        self.last_prompt_tokens: int = 0
        self.last_completion_tokens: int = 0
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.max_context_tokens: int = self._resolve_max_context_tokens()

        self._init_system_prompt()

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        """Build OpenAI tool schemas for available tools."""
        return registry.build_schemas(
            tool_names=self.profile.tools if self.profile.tools else None,
            agent_context=self.context,
            models=self.settings.models,
            subagents=self.profile.subagents,
        )

    def _resolve_max_context_tokens(self) -> int:
        """Resolve max context window size from provider model config.

        Returns the ``max_tokens`` value defined in the provider's model
        configuration.  Falls back to 128 000 when the provider or model
        entry is unavailable (e.g. legacy / env-var only setups).
        """
        if self.provider:
            model_config = self.provider.get_model_by_id(self.model_id)
            if model_config and model_config.max_tokens:
                return model_config.max_tokens
        return 128_000

    def _create_openai_client(self, provider: Optional[ProviderConfig] = None) -> OpenAI:
        """
        Create OpenAI client with compatibility fallback for older SDK versions.

        Args:
            provider: Optional ProviderConfig to use. If None, falls back to settings.
        """
        if provider:
            if not provider.api_key:
                raise ValueError(f"API key not configured for provider '{provider.id}'")

            # Use provider configuration
            kwargs: dict[str, Any] = {
                "api_key": provider.api_key,
                "base_url": provider.api_base_url,
            }
            # Add custom headers if provider has them
            if provider.headers:
                kwargs["default_headers"] = provider.headers
        else:
            # Fall back to legacy settings
            kwargs = {
                "api_key": self.settings.api_key,
                "base_url": self.settings.api_base_url,
            }

        # Add timeout to avoid hanging on connection issues
        kwargs["timeout"] = httpx.Timeout(60.0, connect=10.0)

        try:
            return OpenAI(**kwargs)
        except TypeError as exc:
            if "unexpected keyword argument 'proxies'" not in str(exc):
                raise
            # Compatibility fallback for environments where OpenAI SDK and httpx versions mismatch.
            # Remove default_headers for httpx.Client fallback if present
            http_kwargs = {k: v for k, v in kwargs.items() if k != "default_headers"}
            return OpenAI(
                **http_kwargs, http_client=httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
            )

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
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    @property
    def context_utilization(self) -> float:
        """Context window utilization as a ratio (0.0 to 1.0).

        Computed as ``last_prompt_tokens / max_context_tokens``.  Returns
        0.0 when ``max_context_tokens`` is zero or negative.
        """
        if self.max_context_tokens <= 0:
            return 0.0
        return self.last_prompt_tokens / self.max_context_tokens

    def _update_token_usage(self, usage: Any) -> None:
        """Update token usage counters from an API response ``usage`` object.

        Args:
            usage: The ``response.usage`` object returned by the OpenAI SDK.
                   May be ``None`` if the provider does not include usage data.
        """
        if usage is None:
            return
        self.last_prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        self.last_completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        self.total_prompt_tokens += self.last_prompt_tokens
        self.total_completion_tokens += self.last_completion_tokens

    def _call_llm(self, messages: list[dict[str, Any]]) -> Any:
        """Call the LLM with messages."""
        kwargs = {
            "model": self.model_id,
            "messages": messages,
        }

        if self.tool_schemas:
            kwargs["tools"] = self.tool_schemas
            kwargs["tool_choice"] = "auto"

        provider_hint = self.provider.id if self.provider else "default"
        api_key_hint = (
            self.provider.api_key_env_var
            if self.provider and self.provider.api_key_env_var
            else "SYNTHETIC_API_KEY"
        )
        base_url_hint = (
            "the provider API base URL in providers.yaml" if self.provider else "API_BASE_URL"
        )

        try:
            response = self.client.chat.completions.create(**kwargs)
            self._update_token_usage(response.usage)
            return response.choices[0].message
        except AuthenticationError as e:
            raise RuntimeError(
                f"Authentication failed for provider '{provider_hint}': "
                f"invalid API key. Check {api_key_hint}. Details: {e}"
            ) from e
        except APIConnectionError as e:
            raise RuntimeError(
                f"Connection failed for provider '{provider_hint}': unable to reach API server. "
                f"Check your network and {base_url_hint}. Details: {e}"
            ) from e
        except APITimeoutError as e:
            raise RuntimeError(
                f"Request timed out for provider '{provider_hint}': "
                f"the API server took too long to respond. Details: {e}"
            ) from e
        except APIStatusError as e:
            raise RuntimeError(
                f"API error from provider '{provider_hint}' (status {e.status_code}): {e.message}"
            ) from e

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
                normalized_calls.append(
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": fn.name if fn else "",
                            "arguments": fn.arguments if fn else "{}",
                        },
                    }
                )
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

            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

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
