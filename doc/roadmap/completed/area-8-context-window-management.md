# Area 8: Context Window Management & Compaction

The agent system currently has no awareness of context window limits. Messages accumulate indefinitely in `self.messages` (the conversation history list in `BaseAgent`), and the `response.usage` token counts returned by the OpenAI-compatible API are discarded. The `max_tokens` field already exists in `ModelConfig` (per-provider, e.g. 128000 for Kimi-K2.5, 200000 for Claude) but is never used at runtime.

This area introduces token usage tracking, context window monitoring, and a compaction mechanism that summarizes the conversation history when the context window approaches its limit.

---

### Task 8.1 -- Token Usage Tracking & Display ✅

**Difficulty**: Easy | **Dependencies**: None | **Status**: Done

Capture the `response.usage` object returned by the OpenAI-compatible API after each LLM call, and expose the model's `max_tokens` to the agent so it can compute context utilization.

**Changes to `_call_llm()` in `agent/base.py`**:
- Currently returns only `response.choices[0].message`, discarding the rest. Change to also capture `response.usage` (which contains `prompt_tokens`, `completion_tokens`, `total_tokens`).
- Store cumulative token usage in new instance attributes on `BaseAgent`:
  - `self.last_prompt_tokens: int` -- prompt tokens from the most recent call
  - `self.last_completion_tokens: int` -- completion tokens from the most recent call
  - `self.total_prompt_tokens: int` -- cumulative prompt tokens across all calls in the session
  - `self.total_completion_tokens: int` -- cumulative completion tokens
- Expose `self.max_context_tokens: int` -- loaded from the resolved `ModelConfig.max_tokens` at agent initialization.

**Changes to `RecursiveAgent.run()` in `agent/recursive.py`**:
- After each `_call_llm()` call, update the token counters.
- Compute context utilization: `utilization = self.last_prompt_tokens / self.max_context_tokens`.
- Return or expose the utilization alongside the response text (e.g., as a property or as part of a structured return object).

**Display in CLI (`interfaces/cli_interface.py`)**:
- After each agent response, show a compact token usage line, e.g.:
  `[tokens: 12,450 / 128,000 (9.7%) | response: 850 tokens]`
- Use color coding: green (<70%), yellow (70-89%), red (≥90%).

**Display in Telegram (`interfaces/telegram_interface.py`)**:
- Append a token usage footer to each response message, e.g.:
  `📊 Context: 12,450/128,000 (9.7%)`

**Key files to modify**:
- `agent/base.py` -- capture `response.usage`, add token counter attributes, expose `max_context_tokens`
- `agent/recursive.py` -- update counters after each LLM call, expose utilization
- `interfaces/cli_interface.py` -- display token usage after each response
- `interfaces/telegram_interface.py` -- append token usage to responses

**New dependencies**: None.

---

### Task 8.2 -- Context Compaction with Confirmation ✅

**Difficulty**: Medium | **Dependencies**: Task 8.1 | **Status**: Done

When context utilization reaches a configurable threshold, warn the user and offer to compact the conversation. Compaction generates a summary of the conversation history via a dedicated LLM call, then resets the chat with the summary injected as initial context.

**Threshold configuration**:
- Add a `compact_threshold` field to the agent configuration (in `agents.yaml`) with a default of `0.9` (90%):
  ```yaml
  main:
    compact_threshold: 0.9  # trigger compaction warning at 90% context usage
  ```
- The `AgentProfile` dataclass in `agent/profile.py` gains a `compact_threshold: float = 0.9` field.
- The threshold can also be set globally in provider-level or settings-level config.

**Warning and confirmation flow**:
- After each `_call_llm()` call in `RecursiveAgent.run()`, check if `utilization >= compact_threshold`.
- If triggered, the agent does NOT compact automatically. Instead, it signals the interface layer.
- The interface (CLI or Telegram) presents a warning and asks for confirmation:
  - **CLI**: `⚠ Context usage at 92% (117,760/128,000 tokens). Compact conversation? [y/N]`
  - **Telegram**: Send a message: `⚠ Context usage at 92%. Reply /compact to summarize and continue, or keep chatting.`
- If the user confirms (or sends `/compact`), trigger compaction. Otherwise, continue normally (the warning will appear again after the next response).

**Compaction mechanism**:
- Create a `compact_conversation()` method on `BaseAgent` (or `RecursiveAgent`):
  1. Take the current `self.messages` list (excluding the system prompt).
  2. Build a compaction prompt that asks the LLM to summarize the entire conversation into a concise but comprehensive summary, preserving: key decisions, important facts, code/document references, and any ongoing task context.
  3. Make a dedicated `_call_llm()` call with a temporary message list containing the compaction prompt + the conversation history.
  4. Call `self.reset()` to reinitialize messages to just the system prompt.
  5. Inject the summary as a special message (e.g., `{"role": "user", "content": "[Conversation summary from compaction]: ..."}` followed by `{"role": "assistant", "content": "Understood, I have the context from our previous conversation. How can I continue helping you?"}`).
  6. Reset token counters.

**Compaction prompt design** (suggested):
```
You are summarizing a conversation to preserve context for continuation.
Summarize the following conversation between a user and an AI assistant.
Your summary must preserve:
- All key decisions made
- Important facts, numbers, and references mentioned
- Any ongoing tasks or open questions
- File paths, code snippets, or document references discussed
- The user's goals and preferences expressed

Be concise but comprehensive. The summary will be used to continue the conversation
with full context. Output only the summary, no preamble.
```

**Key files to modify**:
- `agent/base.py` or `agent/recursive.py` -- add `compact_conversation()` method
- `agent/profile.py` -- add `compact_threshold` field to `AgentProfile`
- `interfaces/cli_interface.py` -- handle compaction warning, prompt for confirmation
- `interfaces/telegram_interface.py` -- handle compaction warning, respond to confirmation

**New dependencies**: None.

---

### Task 8.3 -- Manual /compact Slash Command ✅

**Difficulty**: Easy | **Dependencies**: Task 8.2 | **Status**: Done

Add a `/compact` slash command available in both CLI and Telegram that allows the user to manually trigger conversation compaction at any time, regardless of context utilization level.

**CLI implementation** (`interfaces/cli_interface.py`):
- Add a `/compact` case to the `if/elif` slash command chain in `run_cli()`.
- Show current token usage, then ask for confirmation: `Context: 45,000/128,000 (35%). Compact conversation? [y/N]`
- If confirmed, call `agent.compact_conversation()` and display the generated summary.
- After compaction, show the new token usage (which should be much lower).

**Telegram implementation** (`interfaces/telegram_interface.py`):
- Register a new `CommandHandler("compact", self._compact_command)`.
- The `_compact_command` handler calls `agent.compact_conversation()` on the user's agent.
- Reply with a confirmation message including the before/after token usage.

**Key files to modify**:
- `interfaces/cli_interface.py` -- add `/compact` to command dispatch and `print_help()`
- `interfaces/telegram_interface.py` -- add `_compact_command` handler and register it

---

### Task 8.4 -- Tool Result Size Protection ✅

**Difficulty**: Medium | **Dependencies**: Task 8.1 | **Status**: Done

Prevent large tool results from exceeding the context window by implementing proactive size guards at both the tool-level and result-level. Previously, tools like `read_file` would load entire files (e.g., a 500KB Markdown file = ~125K tokens) directly into the conversation, causing `Context limit exceeded` errors.

**Four-layer protection system**:

**Layer 1 — Tool-level size guard in `read_file`** (`src/flavia/tools/read/read_file.py`):
- Before reading, checks `stat().st_size` and estimates token count via `bytes / 4`
- Compares estimated tokens against a dynamic budget (see Layer 4)
- If file exceeds budget:
  - Returns preview of first ~50 lines instead of full content
  - Provides metadata: file size (KB/MB), total lines, estimated tokens, % of context window
  - Shows instructions for partial reads using `start_line`/`end_line` parameters
- Added optional `start_line` and `end_line` parameters to the tool schema for partial file reading
- Partial-read parameters are validated as integers and invalid values return explicit tool errors
- Partial reads are also size-checked; results exceeding budget are truncated with warning

**Layer 2 — Context awareness exposure** (`src/flavia/agent/context.py` + `base.py`):
- `AgentContext` now exposes:
  - `max_context_tokens: int = 128_000` — total context window size
  - `current_context_tokens: int = 0` — actual tokens used in last LLM call
- `BaseAgent._update_token_usage()` propagates `last_prompt_tokens` to `context.current_context_tokens` after each LLM call
- Any tool can inspect current context usage via `agent_context.current_context_tokens`

**Layer 3 — Generic tool result guard** (`src/flavia/agent/base.py` + `recursive.py`):
- New `BaseAgent._guard_tool_result(result: str) -> str` method:
  - Estimates token count of any tool output
  - Truncates if it would consume more than 25% of context window
  - Shows head (500 chars) + tail (500 chars) with explanatory message
- Applied in both `_process_tool_calls()` (BaseAgent) and `_process_tool_calls_with_spawns()` (RecursiveAgent)
- Budgeting is cumulative per LLM turn, so each additional tool result in the same turn uses the remaining guard budget
- Acts as a safety net for *all* tools, not just `read_file`
- Spawn results (`__SPAWN_AGENT__:*` and `__SPAWN_PREDEFINED__:*`) bypass truncation

**Layer 4 — Dynamic context budget** (`src/flavia/tools/read/read_file.py`):
- Budget shrinks as conversation fills: `budget = min(25% of total, 50% of remaining)`
- In practice:
  - Empty context (0%): 25 of 100K tokens allowed per result
  - Half-full (50%): 25 of 100K (absolute cap)
  - Near-full (90%): 5 of 100K (dynamic cap dominates)
  - Almost-full (95%): 2.5 of 100K
- Prevents large reads when context is already close to the limit

**User-facing changes**:
- Large file reads now return structured messages instead of raw content:
  ```
  ⚠ FILE TOO LARGE FOR FULL READ

  File: big_report.md
  Size: 2.4 MB (~620,000 tokens)
  Total lines: 15,000
  Would occupy: 484.4% of context window
  Current context usage: 25.0%
  Budget for this read: ~25,600 tokens

  --- Preview (lines 1-50) ---
  [first 50 lines shown]
  --- End of preview ---

  To read this file, use partial reads:
    - read_file(path="big_report.md", start_line=1, end_line=500)
    - read_file(path="big_report.md", start_line=501, end_line=1000)
    - ...and so on in chunks of ~500 lines

  Or delegate to a sub-agent that can process the file in its own context window.
  ```

**Key files to modify**:
- `src/flavia/tools/read/read_file.py` — size guard, preview, partial reads, dynamic budget
- `src/flavia/agent/context.py` — added `max_context_tokens`, `current_context_tokens` fields
- `src/flavia/agent/base.py` — propagate tokens to context, add `_guard_tool_result()` method
- `src/flavia/agent/recursive.py` — apply guard to non-spawn tool results
- `tests/test_read_file_size_guard.py` — comprehensive test coverage for all 4 layers

**Testing**:
- Unit tests for token estimation and budget computation
- Integration tests for small files (normal reads pass through)
- Integration tests for large files (blocked with preview)
- Integration tests for partial reads (start_line/end_line)
- Integration tests for dynamic budget shrinks with context usage
- Test coverage for generic guard truncating arbitrary tool outputs

**New dependencies**: None.

---

### Task 8.5 -- Context Compaction Tool ✅

**Difficulty**: Easy | **Dependencies**: Tasks 8.1, 8.2 | **Status**: Done

Create a `compact_context` tool that agents can call to summarize their own conversation on-demand with custom instructions. Unlike the `/compact` slash command which is triggered by the user, this tool allows the agent itself to initiate compaction when it deems appropriate, or in response to user requests embedded in natural language.

**Implementation**:
- Created `src/flavia/tools/compact/compact_context.py` with `CompactContextTool` class
- Uses the **sentinel string pattern** (`__COMPACT_CONTEXT__`): since tools only receive `AgentContext` (a passive dataclass) and cannot call agent methods directly, the tool returns a sentinel string that the agent loop intercepts
- `RecursiveAgent._process_tool_calls_with_spawns()` detects the sentinel and calls `compact_conversation()` with the optional `instructions` parameter
- The entire compaction pipeline (`compact_conversation()` → `_summarize_messages_for_compaction()` → `_summarize_messages_recursive()` → `_call_compaction_llm()`) now accepts an optional `instructions` parameter that gets appended to the compaction prompt
- Tool registered via auto-import in `src/flavia/tools/__init__.py`

**Mid-execution context warning** (bonus feature):
- When the agent is in a tool execution loop and context usage crosses the `compact_threshold`, a system notice is injected into `self.messages` informing the LLM that context is running low
- The warning mentions the `compact_context` tool availability and includes current token stats
- Injected only once per `run()` call via a `_compaction_warning_injected` flag, and only when tool calls are present (ensuring the loop will continue and the LLM can act on the warning)
- The LLM can then decide to use `compact_context`, finish its current task quickly, or take other appropriate action

**Compaction summary display consistency** (bonus fix):
- CLI automatic compaction (`_prompt_compaction()`) now captures and displays the summary text after compaction
- Telegram `/compact` command now includes a summary preview (truncated to 500 chars) in the reply message

**Key files created**:
- `src/flavia/tools/compact/__init__.py` — package init
- `src/flavia/tools/compact/compact_context.py` — tool implementation
- `tests/test_compact_context_tool.py` — 23 tests covering schema, sentinel execution, sentinel detection, instructions parameter, and mid-execution warning injection

**Key files modified**:
- `src/flavia/tools/__init__.py` — auto-register compact tool
- `src/flavia/agent/base.py` — `instructions` parameter throughout compaction pipeline
- `src/flavia/agent/recursive.py` — sentinel detection, context warning injection, `_compaction_warning_injected` flag
- `src/flavia/interfaces/cli_interface.py` — summary display on auto-compaction
- `src/flavia/interfaces/telegram_interface.py` — summary preview in `/compact` reply

**Testing**: 23 new tests + updated existing compaction and Telegram tests. Full suite: 666 passed, 6 skipped.

**New dependencies**: None.

---

**[← Back to Roadmap](../../roadmap.md)** | **[CHANGELOG](../../CHANGELOG.md)**
