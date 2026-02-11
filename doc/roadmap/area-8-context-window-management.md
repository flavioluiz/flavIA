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

**[← Back to Roadmap](../roadmap.md)**
