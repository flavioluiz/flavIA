"""Recursive agent with parallel execution for flavIA."""

import json
from pathlib import Path
import re
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures.thread import _threads_queues, _worker
from typing import Any, Optional

from flavia.config import Settings
from flavia.tools.compact.compact_context import COMPACT_SENTINEL

from .base import BaseAgent
from .profile import AgentProfile
from .status import ToolStatus


class _DaemonThreadPoolExecutor(ThreadPoolExecutor):
    """Thread pool executor that uses daemon threads.

    Daemon workers ensure the CLI can exit cleanly even if sub-agent tasks
    are still running after an interruption.
    """

    def _adjust_thread_count(self) -> None:
        # Mirrors ThreadPoolExecutor internals, but marks workers as daemon.
        if self._idle_semaphore.acquire(timeout=0):
            return

        def weakref_cb(_, q=self._work_queue):
            q.put(None)

        num_threads = len(self._threads)
        if num_threads < self._max_workers:
            thread_name = f"{self._thread_name_prefix or self}_{num_threads}"
            t = threading.Thread(
                name=thread_name,
                target=_worker,
                args=(
                    weakref.ref(self, weakref_cb),
                    self._work_queue,
                    self._initializer,
                    self._initargs,
                ),
            )
            t.daemon = True
            t.start()
            self._threads.add(t)
            _threads_queues[t] = self._work_queue


class RecursiveAgent(BaseAgent):
    """Agent capable of spawning and managing sub-agents."""

    MAX_ITERATIONS = 20
    MAX_ITERATIONS_MESSAGE_RE = re.compile(r"^Maximum iterations reached \((\d+)\)\.")
    DOC_MENTION_RE = re.compile(r'(?<![A-Za-z0-9])@(?:"[^"]+"|\'[^\']+\'|[^\s@"\']+)')
    MENTION_TRAILING_PUNCT = ".,;:!?)]}"
    MAX_MENTION_GROUNDING_REMINDERS = 3
    MAX_COMPARISON_FORMAT_REMINDERS = 2
    CITATION_MARKER_RE = re.compile(r"\[\d+\]")
    CROSS_DOC_COMPARISON_PATTERNS = (
        "compare",
        "comparar",
        "comparação",
        "comparacao",
        "versus",
        " vs ",
        "esperado x",
        "enviado x",
        "expected x",
        "item por item",
        "subitem por subitem",
    )
    EXHAUSTIVE_QUERY_PATTERNS = (
        "todos os itens",
        "todos os subitens",
        "item por item",
        "subitem por subitem",
        "sem descrições",
        "sem descricoes",
        "sem descrição",
        "sem descricao",
        "lista completa",
        "apenas lista",
        "somente lista",
        "sem detalhes",
        "compare",
        "comparar",
        "comparação",
        "comparacao",
        "versus",
        "esperado x",
        "enviado x",
        "expected x",
        "all items",
        "all subitems",
        "item by item",
        "subitem by subitem",
        "compare",
        "comparison",
        "without descriptions",
        "list only",
    )
    WRITE_TOOL_NAMES = {
        "write_file",
        "edit_file",
        "insert_text",
        "append_file",
        "delete_file",
        "create_directory",
        "remove_directory",
    }

    def __init__(
        self,
        settings: Settings,
        profile: AgentProfile,
        agent_id: str = "main",
        depth: int = 0,
        parent_id: Optional[str] = None,
    ):
        super().__init__(settings, profile, agent_id, depth, parent_id)
        self._child_counter = 0
        self._child_counter_lock = threading.Lock()
        self._active_children: dict[str, "RecursiveAgent"] = {}

    @classmethod
    def format_max_iterations_message(cls, limit: int) -> str:
        """Format the max-iterations termination message."""
        return (
            f"Maximum iterations reached ({limit}). "
            "Would you like to continue with more iterations or try a more specific request?"
        )

    @classmethod
    def extract_max_iterations_limit(cls, response_text: str) -> Optional[int]:
        """Extract max-iterations limit from a termination message."""
        if not response_text:
            return None
        match = cls.MAX_ITERATIONS_MESSAGE_RE.match(response_text.strip())
        if not match:
            return None
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None

    def run(
        self,
        user_message: str,
        *,
        max_iterations: Optional[int] = None,
        continue_from_current: bool = False,
    ) -> str:
        """Run the agent with a user message."""
        self.compaction_warning_pending = False
        self.compaction_warning_prompt_tokens = 0
        self._compaction_warning_injected = False
        if not continue_from_current:
            self.messages.append({"role": "user", "content": user_message})

        try:
            iteration_limit = (
                int(max_iterations) if max_iterations is not None else self.MAX_ITERATIONS
            )
        except (TypeError, ValueError):
            iteration_limit = self.MAX_ITERATIONS
        iteration_limit = max(1, iteration_limit)

        iterations = 0
        pending_spawns: list[dict[str, Any]] = []
        had_write_tool_call = False
        had_successful_write = False
        write_failures: list[str] = []
        required_mentions = self._extract_doc_mentions(user_message)
        requires_mention_scoped_search = self._requires_mention_scoped_search(user_message)
        requires_cross_doc_coverage = self._requires_cross_doc_coverage(
            user_message,
            mention_count=len(required_mentions),
        )
        force_exhaustive_retrieval = self._requires_exhaustive_retrieval(user_message)
        mention_enforcement_attempts = 0
        coverage_enforcement_attempts = 0
        comparison_format_enforcement_attempts = 0
        had_grounded_search = False
        covered_mentions: set[str] = set()

        while iterations < iteration_limit:
            iterations += 1

            self._notify_status(
                ToolStatus.waiting_llm(self.context.agent_id, self.context.current_depth)
            )
            response = self._call_llm(self.messages)
            self.messages.append(self._assistant_message_to_dict(response))
            if self.needs_compaction:
                self.compaction_warning_pending = True
                self.compaction_warning_prompt_tokens = max(
                    self.compaction_warning_prompt_tokens,
                    self.last_prompt_tokens,
                )

            if not response.tool_calls:
                if (
                    requires_cross_doc_coverage
                    and required_mentions
                    and covered_mentions != required_mentions
                ):
                    remaining_mentions = sorted(required_mentions - covered_mentions)
                    if coverage_enforcement_attempts >= self.MAX_MENTION_GROUNDING_REMINDERS:
                        return self._mention_coverage_error_message(remaining_mentions)
                    coverage_enforcement_attempts += 1
                    self.messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[System notice] This is a multi-file comparison request. "
                                "Before answering, call search_chunks again and include the remaining "
                                f"@mentions in the query: {self._format_mentions(remaining_mentions)}."
                            ),
                        }
                    )
                    continue
                if (
                    requires_cross_doc_coverage
                    and had_grounded_search
                    and not self._has_citation_markers(str(response.content or ""))
                ):
                    if (
                        comparison_format_enforcement_attempts
                        >= self.MAX_COMPARISON_FORMAT_REMINDERS
                    ):
                        return self._comparison_format_error_message()
                    comparison_format_enforcement_attempts += 1
                    self.messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[System notice] For comparative multi-file tasks, answer in two stages:\n"
                                "1) Evidence matrix grouped by source file.\n"
                                "2) Conclusions based only on cited evidence.\n"
                                "Every factual claim must include at least one citation marker like [1]. "
                                "If evidence is missing, explicitly write 'not found in retrieved evidence'."
                            ),
                        }
                    )
                    continue
                if (
                    requires_mention_scoped_search
                    and not had_grounded_search
                ):
                    if mention_enforcement_attempts >= self.MAX_MENTION_GROUNDING_REMINDERS:
                        return self._mention_grounding_error_message()
                    mention_enforcement_attempts += 1
                    self.messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[System notice] The user referenced files using @mentions. "
                                "Before answering, you must call search_chunks with the user query "
                                "(including @mentions) to ground the response in indexed evidence."
                            ),
                        }
                    )
                    continue
                fallback = (
                    "I could not produce a textual response. Please try rephrasing your question."
                )
                final_text = response.content or fallback
                if had_write_tool_call and not had_successful_write and write_failures:
                    details = "\n".join(f"- {item}" for item in write_failures[-3:])
                    final_text += f"\n\nWrite operations were not applied due to errors:\n{details}"
                return final_text

            tool_results, spawns = self._process_tool_calls_with_spawns(
                response.tool_calls,
                force_search_mode="exhaustive" if force_exhaustive_retrieval else None,
            )

            # Inject context-window warning for the LLM to see on next iteration.
            # Only injected once per run() and only when there are tool calls
            # (i.e. the loop will continue), so the LLM can act on it.
            if self.needs_compaction and not self._compaction_warning_injected:
                self._compaction_warning_injected = True
                pct = self.context_utilization * 100
                remaining = self.max_context_tokens - self.last_prompt_tokens
                warning = (
                    f"[System notice] Context window is at {pct:.0f}% capacity "
                    f"({self.last_prompt_tokens:,}/{self.max_context_tokens:,} tokens, "
                    f"~{remaining:,} remaining). "
                    "You have the compact_context tool available to summarize the "
                    "conversation and free up space. Consider using it now, or wrap "
                    "up your current task quickly."
                )
                self.messages.append({"role": "user", "content": warning})

            for tool_call, tool_result in zip(response.tool_calls, tool_results):
                tool_name = getattr(getattr(tool_call, "function", None), "name", "")
                if tool_name == "search_chunks":
                    tool_args = self._parse_tool_args(getattr(tool_call, "function", None))
                    query_value = tool_args.get("query")
                    if isinstance(query_value, str):
                        query_mentions = self._extract_doc_mentions(query_value)
                        for query_mention in query_mentions:
                            for required_mention in required_mentions:
                                if self._mentions_equivalent(required_mention, query_mention):
                                    covered_mentions.add(required_mention)
                    result_text = str(tool_result.get("content", ""))
                    if result_text.startswith("No indexed documents match the @file references"):
                        return result_text
                    if not self._is_error_result(result_text):
                        had_grounded_search = True
                if tool_name not in self.WRITE_TOOL_NAMES:
                    continue
                had_write_tool_call = True
                result_text = str(tool_result.get("content", ""))
                if self._is_error_result(result_text):
                    write_failures.append(f"{tool_name}: {result_text}")
                else:
                    had_successful_write = True

            self.messages.extend(tool_results)
            pending_spawns.extend(spawns)

            if (
                requires_mention_scoped_search
                and not had_grounded_search
                and not any(
                    getattr(getattr(tc, "function", None), "name", "") == "search_chunks"
                    for tc in response.tool_calls
                )
            ):
                if mention_enforcement_attempts >= self.MAX_MENTION_GROUNDING_REMINDERS:
                    return self._mention_grounding_error_message()
                mention_enforcement_attempts += 1
                self.messages.append(
                    {
                        "role": "user",
                        "content": (
                            "[System notice] You still need to call search_chunks for the @mentioned files "
                            "before producing the final answer."
                        ),
                    }
                )

            if pending_spawns:
                spawn_results = self._execute_spawns_parallel(pending_spawns)

                for spawn_result in spawn_results:
                    tool_call_id = spawn_result["tool_call_id"]
                    for msg in self.messages:
                        if msg.get("tool_call_id") == tool_call_id:
                            msg["content"] = spawn_result["content"]
                            break

                pending_spawns = []

        self.log(f"Max iterations reached ({iteration_limit})")
        return self.format_max_iterations_message(iteration_limit)

    @staticmethod
    def _mention_grounding_error_message() -> str:
        """Message returned when mention-scoped grounding could not be enforced."""
        return (
            "Unable to complete the answer because @file grounding was required but `search_chunks` "
            "was not executed successfully. Please retry, keeping the @file references explicit."
        )

    @staticmethod
    def _mention_coverage_error_message(remaining_mentions: list[str]) -> str:
        """Message returned when cross-document mention coverage remains incomplete."""
        suffix = ""
        if remaining_mentions:
            suffix = " Missing evidence scope for: " + ", ".join(f"@{item}" for item in remaining_mentions)
        return (
            "Unable to complete the answer because multi-file grounding was incomplete."
            f"{suffix} Please retry with explicit @file references."
        )

    @staticmethod
    def _comparison_format_error_message() -> str:
        """Message returned when comparative output lacks required citation grounding."""
        return (
            "Unable to complete the comparative answer with grounded citations. "
            "Please retry and keep explicit @file scope so evidence can be cited item by item."
        )

    def _requires_mention_scoped_search(self, user_message: str) -> bool:
        """Return True when @mentions should trigger mandatory search_chunks grounding."""
        if not isinstance(user_message, str) or not user_message.strip():
            return False
        if not self.DOC_MENTION_RE.search(user_message):
            return False

        context = getattr(self, "context", None)
        if context is None:
            return False

        available_tools = set(getattr(context, "available_tools", []) or [])
        if "search_chunks" not in available_tools:
            return False

        base_dir = getattr(context, "base_dir", None)
        if base_dir is None:
            return False
        return (base_dir / ".index" / "index.db").exists()

    def _requires_exhaustive_retrieval(self, user_message: str) -> bool:
        """Return True when query should default to exhaustive retrieval profile."""
        if not isinstance(user_message, str) or not user_message.strip():
            return False
        lowered = user_message.lower()
        return any(pattern in lowered for pattern in self.EXHAUSTIVE_QUERY_PATTERNS)

    def _requires_cross_doc_coverage(self, user_message: str, *, mention_count: int) -> bool:
        """Return True when multi-document requests should cover each mentioned scope."""
        if mention_count < 2:
            return False
        if not isinstance(user_message, str) or not user_message.strip():
            return False
        lowered = user_message.lower()
        return any(pattern in lowered for pattern in self.CROSS_DOC_COMPARISON_PATTERNS)

    @classmethod
    def _extract_doc_mentions(cls, text: str) -> set[str]:
        """Extract normalized @mention tokens from free text."""
        if not isinstance(text, str) or not text.strip():
            return set()

        mentions: set[str] = set()
        for match in cls.DOC_MENTION_RE.finditer(text):
            raw = (match.group(0) or "").strip()
            if not raw.startswith("@"):
                continue
            token = raw[1:].strip()
            if token.startswith(("'", '"')) and token.endswith(("'", '"')) and len(token) >= 2:
                token = token[1:-1]
            token = token.rstrip(cls.MENTION_TRAILING_PUNCT).strip()
            token = cls._normalize_mention_token(token)
            if token:
                mentions.add(token)
        return mentions

    @staticmethod
    def _normalize_mention_token(token: str) -> str:
        """Normalize mention token for robust set comparisons."""
        normalized = token.strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized.lower().strip("/")

    @staticmethod
    def _format_mentions(mentions: list[str]) -> str:
        """Render mentions for user/system notices."""
        if not mentions:
            return "(none)"
        return ", ".join(f"@{item}" for item in mentions)

    @classmethod
    def _has_citation_markers(cls, text: str) -> bool:
        """Return True when text contains inline retrieval citation markers like [1]."""
        if not isinstance(text, str) or not text.strip():
            return False
        return bool(cls.CITATION_MARKER_RE.search(text))

    @staticmethod
    def _parse_tool_args(function_obj: Any) -> dict[str, Any]:
        """Parse JSON tool call arguments into a dict."""
        arguments = getattr(function_obj, "arguments", "")
        try:
            parsed = json.loads(arguments)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _mentions_equivalent(required: str, candidate: str) -> bool:
        """Return True when two mention tokens likely refer to the same target file."""
        if required == candidate:
            return True
        if not required or not candidate:
            return False
        if required.endswith(f"/{candidate}") or candidate.endswith(f"/{required}"):
            return True
        return Path(required).stem == Path(candidate).stem

    @staticmethod
    def _is_error_result(result_text: str) -> bool:
        """Return True when a tool result indicates failure/cancellation."""
        lowered = result_text.strip().lower()
        return lowered.startswith("error:") or lowered.startswith("operation cancelled")

    def _process_tool_calls_with_spawns(
        self,
        tool_calls: list[Any],
        *,
        force_search_mode: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Process tool calls and identify spawn requests."""
        results = []
        spawns = []
        consumed_tokens = 0

        for tool_call in tool_calls:
            name = tool_call.function.name
            try:
                parsed_args = json.loads(tool_call.function.arguments)
                args = parsed_args if isinstance(parsed_args, dict) else {}
            except json.JSONDecodeError:
                args = {}
            if (
                name == "search_chunks"
                and force_search_mode
                and isinstance(args, dict)
                and "retrieval_mode" not in args
            ):
                args["retrieval_mode"] = force_search_mode

            self.log(f"Tool: {name}({args})")

            self._notify_status(
                ToolStatus.executing_tool(
                    name, args, self.context.agent_id, self.context.current_depth
                )
            )
            result = self._execute_tool(name, args)

            if name == "spawn_agent" and result.startswith("__SPAWN_AGENT__:"):
                spawn_info = self._parse_spawn_agent(result, args)
                spawn_info["tool_call_id"] = tool_call.id
                spawns.append(spawn_info)
                # Note: we intentionally do NOT emit a second SPAWNING_AGENT
                # status here.  The EXECUTING_TOOL notification above already
                # contains "Spawning agent: ..." which the UI uses to detect
                # spawn tasks and nest child agents.  Emitting a second status
                # would cause the tree renderer to consume two children per
                # spawn, breaking the hierarchy.
                result = "[Spawning sub-agent...]"

            elif name == "spawn_predefined_agent" and result.startswith("__SPAWN_PREDEFINED__:"):
                spawn_info = self._parse_spawn_predefined(result, args)
                spawn_info["tool_call_id"] = tool_call.id
                spawns.append(spawn_info)
                # Same rationale as above – avoid duplicate spawn notification.
                result = "[Spawning predefined agent...]"

            elif name == "compact_context" and result.startswith(COMPACT_SENTINEL):
                # Extract optional instructions from sentinel payload
                instructions: str | None = None
                if ":" in result:
                    _, payload = result.split(":", 1)
                    try:
                        data = json.loads(payload)
                        candidate = data.get("instructions")
                        if isinstance(candidate, str) and candidate.strip():
                            instructions = candidate
                    except (json.JSONDecodeError, AttributeError):
                        pass

                try:
                    summary = self.compact_conversation(instructions=instructions)
                    result = (
                        f"Conversation compacted successfully. Summary:\n{summary}"
                        if summary
                        else "Nothing to compact (conversation is empty)."
                    )
                except Exception as exc:
                    result = f"Compaction failed: {exc}"

            else:
                # Apply generic size guard to non-spawn tool results
                result = self._guard_tool_result(result, consumed_tokens=consumed_tokens)

            consumed_tokens += self._estimate_guard_tokens(result)

            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

        return results, spawns

    def _parse_spawn_agent(self, result: str, args: dict) -> dict[str, Any]:
        """Parse spawn_agent result into spawn request."""
        _, data = result.split(":", 1)
        payload = self._parse_spawn_payload(data)

        if payload is not None:
            task = payload.get("task", args.get("task", ""))
            context = payload.get("context", args.get("context", ""))
            model = payload.get("model")
            tools = payload.get("tools")
            if tools is not None and not isinstance(tools, list):
                tools = None
        else:
            # Backward-compatible parsing for older delimiter payloads.
            parts = data.split("|")
            task = parts[0] if len(parts) > 0 else args.get("task", "")
            context = parts[1] if len(parts) > 1 else args.get("context", "")
            model = parts[2] if len(parts) > 2 and parts[2] else None
            tools_str = parts[3] if len(parts) > 3 else ""
            tools = [t.strip() for t in tools_str.split(",") if t.strip()] if tools_str else None

        return {
            "type": "dynamic",
            "task": task,
            "context": context,
            "model": model,
            "tools": tools,
        }

    def _parse_spawn_predefined(self, result: str, args: dict) -> dict[str, Any]:
        """Parse spawn_predefined_agent result into spawn request."""
        _, data = result.split(":", 1)
        payload = self._parse_spawn_payload(data)
        if payload is not None:
            agent_name = payload.get("agent_name", args.get("agent_name", ""))
            task = payload.get("task", args.get("task", ""))
        else:
            # Backward-compatible parsing for older delimiter payloads.
            parts = data.split("|")
            agent_name = parts[0] if len(parts) > 0 else args.get("agent_name", "")
            task = parts[1] if len(parts) > 1 else args.get("task", "")

        return {
            "type": "predefined",
            "agent_name": agent_name,
            "task": task,
        }

    def _parse_spawn_payload(self, data: str) -> Optional[dict[str, Any]]:
        """Parse JSON payload used by spawn tools."""
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _execute_spawns_parallel(self, spawns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute spawn requests in parallel."""
        if not spawns:
            return []

        results = []
        try:
            configured_workers = int(self.settings.parallel_workers)
        except (TypeError, ValueError):
            configured_workers = 1
        workers = max(1, min(len(spawns), configured_workers))

        executor = _DaemonThreadPoolExecutor(max_workers=workers, thread_name_prefix="flavia-spawn")
        futures = {}
        interrupted = False

        try:
            for spawn in spawns:
                future = executor.submit(self._execute_single_spawn, spawn)
                futures[future] = spawn["tool_call_id"]

            for future in as_completed(futures):
                tool_call_id = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = f"Error in sub-agent: {e}"

                results.append(
                    {
                        "tool_call_id": tool_call_id,
                        "content": result,
                    }
                )
        except KeyboardInterrupt:
            interrupted = True
            for future in futures:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=not interrupted, cancel_futures=interrupted)

        return results

    def _execute_single_spawn(self, spawn: dict[str, Any]) -> str:
        """Execute a single spawn request."""
        if spawn["type"] == "predefined":
            return self._spawn_predefined(spawn["agent_name"], spawn["task"])
        else:
            return self._spawn_dynamic(
                spawn["task"],
                spawn["context"],
                spawn.get("model"),
                spawn.get("tools"),
            )

    def _spawn_predefined(self, agent_name: str, task: str) -> str:
        """Spawn a predefined sub-agent."""
        subagent_profile = self.profile.create_subagent_profile(agent_name)
        if not subagent_profile:
            return f"Error: Unknown predefined agent '{agent_name}'"

        with self._child_counter_lock:
            self._child_counter += 1
            child_id = f"{self.context.agent_id}.{agent_name}.{self._child_counter}"

        self.log(f"Spawning predefined agent: {agent_name} as {child_id}")

        child = RecursiveAgent(
            settings=self.settings,
            profile=subagent_profile,
            agent_id=child_id,
            depth=self.context.current_depth + 1,
            parent_id=self.context.agent_id,
        )
        child.status_callback = self.status_callback
        if hasattr(child, "context") and hasattr(self, "context"):
            child.context.rag_turn_id = getattr(self.context, "rag_turn_id", None)
            child.context.rag_turn_counter = getattr(self.context, "rag_turn_counter", 0)
            child.context.rag_debug = bool(getattr(self.context, "rag_debug", False))

        try:
            result = child.run(task)
            self._notify_status(
                ToolStatus.agent_completed(
                    result[:200] if result else "",
                    child_id,
                    self.context.current_depth + 1,
                )
            )
            return f"[{agent_name}]: {result}"
        except Exception as e:
            return f"Error in {agent_name}: {e}"

    def _spawn_dynamic(
        self,
        task: str,
        context: str,
        model: Optional[str] = None,
        tools: Optional[list[str]] = None,
    ) -> str:
        """Spawn a dynamic sub-agent."""
        with self._child_counter_lock:
            self._child_counter += 1
            child_number = self._child_counter
            child_id = f"{self.context.agent_id}.sub.{child_number}"

        self.log(f"Spawning dynamic agent: {child_id}")

        profile = AgentProfile(
            context=context,
            model=model or self.profile.model,
            base_dir=self.profile.base_dir,
            tools=tools or self.profile.tools,
            subagents={},
            name=f"sub-{child_number}",
            max_depth=self.profile.max_depth,
            compact_threshold=self.profile.compact_threshold,
            compact_threshold_source=self.profile.compact_threshold_source,
            converted_access_mode=self.profile.converted_access_mode,
            allow_converted_read=self.profile.allow_converted_read,
            permissions=self.profile.permissions.copy(),
        )

        child = RecursiveAgent(
            settings=self.settings,
            profile=profile,
            agent_id=child_id,
            depth=self.context.current_depth + 1,
            parent_id=self.context.agent_id,
        )
        child.status_callback = self.status_callback
        if hasattr(child, "context") and hasattr(self, "context"):
            child.context.rag_turn_id = getattr(self.context, "rag_turn_id", None)
            child.context.rag_turn_counter = getattr(self.context, "rag_turn_counter", 0)
            child.context.rag_debug = bool(getattr(self.context, "rag_debug", False))

        try:
            result = child.run(task)
            self._notify_status(
                ToolStatus.agent_completed(
                    result[:200] if result else "",
                    child_id,
                    self.context.current_depth + 1,
                )
            )
            return f"[sub-agent]: {result}"
        except Exception as e:
            return f"Error in sub-agent: {e}"
