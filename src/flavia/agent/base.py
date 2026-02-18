"""Base agent class for flavIA."""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
)

from flavia.config import ProviderConfig, Settings
from flavia.tools import registry

from .context import AgentContext, build_system_prompt, build_tools_description
from .profile import AgentProfile
from .status import StatusCallback, ToolStatus


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
        self.context.rag_debug = bool(getattr(settings, "rag_debug", False))

        self.client = self._create_openai_client(self.provider)

        self.tool_schemas = self._build_tool_schemas()
        self.messages: list[dict[str, Any]] = []

        # Token usage tracking
        self.last_prompt_tokens: int = 0
        self.last_completion_tokens: int = 0
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.compaction_warning_pending: bool = False
        self.compaction_warning_prompt_tokens: int = 0
        self.max_context_tokens: int = self._resolve_max_context_tokens()
        self.context.max_context_tokens = self.max_context_tokens

        # Status callback for real-time tool status updates
        self.status_callback: Optional[StatusCallback] = None
        (
            self.profile.compact_threshold,
            self.profile.compact_threshold_source,
        ) = self._resolve_compact_threshold()

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

    @staticmethod
    def _parse_compact_threshold(value: Any) -> Optional[float]:
        """Parse and validate a compact threshold value."""
        if value is None:
            return None
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return None
        if 0.0 <= threshold <= 1.0:
            return threshold
        return None

    def _resolve_compact_threshold(self) -> tuple[float, str]:
        """Resolve compaction threshold with precedence rules.

        Precedence:
        1. Agent profile threshold when explicitly configured (including inherited)
        2. Provider model-level threshold
        3. Provider-level threshold
        4. Global settings threshold
        5. Default (0.9)
        """
        profile_source = getattr(self.profile, "compact_threshold_source", "default")
        profile_threshold = self._parse_compact_threshold(
            getattr(self.profile, "compact_threshold", 0.9)
        )
        if profile_source != "default" and profile_threshold is not None:
            return profile_threshold, profile_source

        model_threshold: Optional[float] = None
        provider_threshold: Optional[float] = None
        if self.provider:
            model_config = self.provider.get_model_by_id(self.model_id)
            if model_config:
                model_threshold = self._parse_compact_threshold(
                    getattr(model_config, "compact_threshold", None)
                )
            provider_threshold = self._parse_compact_threshold(
                getattr(self.provider, "compact_threshold", None)
            )

        if model_threshold is not None:
            return model_threshold, "provider-model"
        if provider_threshold is not None:
            return provider_threshold, "provider"

        settings_configured = bool(getattr(self.settings, "compact_threshold_configured", False))
        settings_threshold = self._parse_compact_threshold(
            getattr(self.settings, "compact_threshold", 0.9)
        )
        if settings_configured and settings_threshold is not None:
            return settings_threshold, "settings"

        if profile_threshold is not None:
            return profile_threshold, profile_source
        return 0.9, "default"

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
        request_timeout = float(getattr(self.settings, "llm_request_timeout", 600))
        connect_timeout = float(getattr(self.settings, "llm_connect_timeout", 10))
        kwargs["timeout"] = httpx.Timeout(request_timeout, connect=connect_timeout)

        try:
            return OpenAI(**kwargs)
        except TypeError as exc:
            if "unexpected keyword argument 'proxies'" not in str(exc):
                raise
            # Compatibility fallback for environments where OpenAI SDK and httpx versions mismatch.
            # Remove default_headers for httpx.Client fallback if present
            http_kwargs = {k: v for k, v in kwargs.items() if k != "default_headers"}
            return OpenAI(
                **http_kwargs,
                http_client=httpx.Client(
                    timeout=httpx.Timeout(request_timeout, connect=connect_timeout)
                ),
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
        # Keep runtime context aware of current message history so tools can
        # enforce history-dependent policies.
        self.context.messages = self.messages

    def reset(self) -> None:
        """Reset agent state for new conversation."""
        self._init_system_prompt()
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.compaction_warning_pending = False
        self.compaction_warning_prompt_tokens = 0

    _COMPACTION_PROMPT = (
        "You are summarizing a conversation to preserve context for continuation.\n"
        "Summarize the following conversation between a user and an AI assistant.\n"
        "Your summary must preserve:\n"
        "- All key decisions made\n"
        "- Important facts, numbers, and references mentioned\n"
        "- Any ongoing tasks or open questions\n"
        "- File paths, code snippets, or document references discussed\n"
        "- The user's goals and preferences expressed\n"
        "\n"
        "Be concise but comprehensive. The summary will be used to continue the conversation\n"
        "with full context. Output only the summary, no preamble."
    )
    _COMPACTION_MAX_RECURSION_DEPTH = 6

    def compact_conversation(self, instructions: str | None = None) -> str:
        """Compact the conversation by summarizing its history.

        Sends the current conversation (excluding system prompt) to the LLM
        with a compaction prompt, then resets the conversation and injects
        the summary as initial context.

        Args:
            instructions: Optional custom instructions for how to summarize
                the conversation (e.g. "focus on technical decisions").

        Returns:
            The generated summary text.
        """
        # Collect conversation messages (skip system prompt at index 0)
        conversation_messages = self.messages[1:]
        if not conversation_messages:
            return ""

        summary = self._summarize_messages_for_compaction(
            conversation_messages, instructions=instructions
        )

        # Reset conversation to system prompt only
        self.reset()

        # Inject the summary as initial context
        self.messages.append(
            {
                "role": "user",
                "content": f"[Conversation summary from compaction]: {summary}",
            }
        )
        self.messages.append(
            {
                "role": "assistant",
                "content": (
                    "Understood, I have the context from our previous conversation. "
                    "How can I continue helping you?"
                ),
            }
        )
        # No direct LLM call happens after summary injection, so usage counters
        # are estimated from current in-memory messages to avoid displaying zero
        # context right after compaction.
        self.last_prompt_tokens = self._estimate_prompt_tokens_for_messages(self.messages)

        return summary

    @staticmethod
    def _estimate_prompt_tokens_for_messages(messages: list[dict[str, Any]]) -> int:
        """Estimate prompt tokens for a list of chat-style messages.

        This is a lightweight heuristic (chars/4 with per-message overhead)
        used when provider usage data is unavailable for the current prompt.
        """

        def _estimate_text_tokens(value: Any) -> int:
            if value is None:
                return 0
            if isinstance(value, str):
                text = value
            else:
                try:
                    text = json.dumps(value, ensure_ascii=False)
                except Exception:
                    text = str(value)
            if not text:
                return 0
            return max(1, (len(text) + 3) // 4)

        if not messages:
            return 0

        total = 0
        for msg in messages:
            total += 4  # rough chat-format overhead per message
            total += _estimate_text_tokens(msg.get("content", ""))

            if "tool_calls" in msg:
                total += _estimate_text_tokens(msg.get("tool_calls"))
            if "tool_call_id" in msg:
                total += _estimate_text_tokens(msg.get("tool_call_id"))
            if "name" in msg:
                total += _estimate_text_tokens(msg.get("name"))

        return max(1, total + 2)  # assistant priming overhead

    def _summarize_messages_for_compaction(
        self, messages: list[dict[str, Any]], *, instructions: str | None = None
    ) -> str:
        """Summarize messages for compaction with size-aware fallback."""
        self.log(
            f"Compaction requested: {len(messages)} messages "
            f"(last prompt tokens: {self.last_prompt_tokens})"
        )
        return self._summarize_messages_recursive(messages, depth=0, instructions=instructions)

    def _summarize_messages_recursive(
        self,
        messages: list[dict[str, Any]],
        depth: int,
        *,
        instructions: str | None = None,
    ) -> str:
        """Summarize messages, recursively splitting on retryable failures."""
        conversation_text = self._serialize_messages_for_compaction(messages)
        try:
            return self._call_compaction_llm(conversation_text, instructions=instructions)
        except RuntimeError as exc:
            if (
                len(messages) <= 1
                or depth >= self._COMPACTION_MAX_RECURSION_DEPTH
                or not self._is_retryable_compaction_error(exc)
            ):
                raise

            midpoint = len(messages) // 2
            if midpoint <= 0:
                raise

            self.log(
                f"Compaction pass failed at depth {depth} ({exc}); "
                "retrying with split conversation chunks."
            )

            left_summary = self._summarize_messages_recursive(
                messages[:midpoint], depth + 1, instructions=instructions
            )
            right_summary = self._summarize_messages_recursive(
                messages[midpoint:], depth + 1, instructions=instructions
            )

            merged_text = (
                "Conversation chunk summaries:\n\n"
                f"Part 1 summary:\n{left_summary}\n\n"
                f"Part 2 summary:\n{right_summary}"
            )

            try:
                return self._call_compaction_llm(merged_text, instructions=instructions)
            except RuntimeError as merge_exc:
                if (
                    depth >= self._COMPACTION_MAX_RECURSION_DEPTH
                    or not self._is_retryable_compaction_error(merge_exc)
                ):
                    raise
                # Last-resort fallback: preserve both summaries when merge compaction fails.
                merged_summary = f"{left_summary}\n\n{right_summary}".strip()
                if merged_summary:
                    return merged_summary
                raise

    def _call_compaction_llm(
        self, conversation_text: str, *, instructions: str | None = None
    ) -> str:
        """Call the LLM for compaction with tools disabled."""
        prompt = self._COMPACTION_PROMPT
        if instructions:
            prompt += f"\n\nAdditional instructions:\n{instructions}"

        compaction_messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": conversation_text},
        ]

        saved_tool_schemas = self.tool_schemas
        self.tool_schemas = []
        try:
            summary_response = self._call_llm(compaction_messages)
        finally:
            self.tool_schemas = saved_tool_schemas

        summary = (summary_response.content or "").strip()
        if not summary:
            raise RuntimeError("Compaction summary was empty; conversation was not compacted.")
        return summary

    @staticmethod
    def _is_retryable_compaction_error(exc: Exception) -> bool:
        """Whether a compaction failure is likely caused by prompt size/latency."""
        message = str(exc).lower()
        retry_markers = (
            "timed out",
            "timeout",
            "context",
            "maximum context",
            "too long",
            "token",
            "status 400",
            "status 413",
        )
        return any(marker in message for marker in retry_markers)

    @staticmethod
    def _serialize_messages_for_compaction(messages: list[dict[str, Any]]) -> str:
        """Serialize conversation messages into a readable text block.

        Tool-call and tool-result messages are formatted for clarity so the
        summariser can understand the conversation flow.
        """
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                text_parts = []
                if content:
                    text_parts.append(content)
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        text_parts.append(
                            f"[Called tool {fn.get('name', '?')}({fn.get('arguments', '')})]"
                        )
                lines.append(f"Assistant: {' '.join(text_parts)}")
            elif role == "tool":
                tool_id = msg.get("tool_call_id", "?")
                lines.append(f"Tool result ({tool_id}): {content}")
            else:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @property
    def context_utilization(self) -> float:
        """Context window utilization as a ratio (0.0 to 1.0).

        Computed as ``last_prompt_tokens / max_context_tokens``.  Returns
        0.0 when ``max_context_tokens`` is zero or negative.
        """
        if self.max_context_tokens <= 0:
            return 0.0
        return self.last_prompt_tokens / self.max_context_tokens

    @property
    def needs_compaction(self) -> bool:
        """Whether context utilization has reached the compaction threshold.

        Returns ``True`` when ``context_utilization >= compact_threshold``
        (from the agent profile).  The interface layer should check this
        after each ``run()`` call and offer compaction to the user.
        """
        return self.context_utilization >= self.profile.compact_threshold

    def _update_token_usage(self, usage: Any) -> None:
        """Update token usage counters from an API response ``usage`` object.

        Args:
            usage: The ``response.usage`` object returned by the OpenAI SDK.
                   May be ``None`` if the provider does not include usage data.
        """

        def _coerce_token_count(value: Any) -> int:
            """Convert provider token values to safe non-negative ints."""
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0

        if usage is None:
            # Usage can be omitted by some OpenAI-compatible providers.
            # Keep cumulative totals, but clear last-call counters.
            self.last_prompt_tokens = 0
            self.last_completion_tokens = 0
            return

        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
        else:
            prompt_tokens = getattr(usage, "prompt_tokens", 0)
            completion_tokens = getattr(usage, "completion_tokens", 0)

        self.last_prompt_tokens = _coerce_token_count(prompt_tokens)
        self.last_completion_tokens = _coerce_token_count(completion_tokens)
        self.total_prompt_tokens += self.last_prompt_tokens
        self.total_completion_tokens += self.last_completion_tokens
        # Keep context aware of current utilization so tools can make
        # budget-aware decisions (e.g. refusing to read oversized files).
        ctx = getattr(self, "context", None)
        if ctx is not None:
            ctx.current_context_tokens = self.last_prompt_tokens

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
            self._update_token_usage(getattr(response, "usage", None))
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

    # ------------------------------------------------------------------
    # Camada 3: Generic tool-result size guard
    # ------------------------------------------------------------------
    _GUARD_CHARS_PER_TOKEN = 4
    _GUARD_MAX_CONTEXT_FRACTION = 0.25
    _GUARD_REMAINING_FRACTION = 0.50
    _GUARD_KEEP_EDGE_CHARS = 500  # chars kept at start/end on truncation

    def _estimate_guard_tokens(self, text: str) -> int:
        """Estimate token count used by guard budgeting."""
        if not text:
            return 0
        return (len(text) + self._GUARD_CHARS_PER_TOKEN - 1) // self._GUARD_CHARS_PER_TOKEN

    def _guard_tool_result(self, result: str, consumed_tokens: int = 0) -> str:
        """Truncate a tool result if it would consume too much context.

        This acts as a safety net for *all* tools, not just ``read_file``.
        """
        max_ctx = getattr(self, "max_context_tokens", 128_000)
        current = getattr(self, "last_prompt_tokens", 0) + max(0, consumed_tokens)
        remaining = max(0, max_ctx - current)

        absolute_cap = int(max_ctx * self._GUARD_MAX_CONTEXT_FRACTION)
        dynamic_cap = int(remaining * self._GUARD_REMAINING_FRACTION)
        budget_tokens = max(1, min(absolute_cap, dynamic_cap))
        budget_chars = budget_tokens * self._GUARD_CHARS_PER_TOKEN

        if len(result) <= budget_chars:
            return result

        estimated_tokens = max(1, self._estimate_guard_tokens(result))
        edge = self._GUARD_KEEP_EDGE_CHARS
        head = result[:edge]
        tail = result[-edge:]
        return (
            f"[TOOL RESULT TRUNCATED: ~{estimated_tokens:,} tokens estimated, "
            f"budget is ~{budget_tokens:,} tokens ({self._GUARD_MAX_CONTEXT_FRACTION:.0%} of "
            f"context window). Showing first and last {edge} chars. "
            f"Consider using partial reads (start_line/end_line) or a sub-agent.]\n\n"
            f"--- Start ---\n{head}\n--- ... ---\n{tail}\n--- End ---"
        )

    def _process_tool_calls(self, tool_calls: list[Any]) -> list[dict[str, Any]]:
        """Process tool calls from LLM response."""
        results = []
        consumed_tokens = 0

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
            result = self._guard_tool_result(result, consumed_tokens=consumed_tokens)
            consumed_tokens += self._estimate_guard_tokens(result)

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
        if self.settings.verbose and not self.status_callback:
            print(f"[{self.context.agent_id}] {message}")

    def _notify_status(self, status: ToolStatus) -> None:
        """Notify status callback about current execution state.

        Silently ignores any errors to avoid breaking agent execution.
        """
        if self.status_callback:
            try:
                self.status_callback(status)
            except Exception:
                pass  # Never break execution due to status notification
