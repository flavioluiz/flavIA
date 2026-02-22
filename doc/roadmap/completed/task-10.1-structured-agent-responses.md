# Task 10.1 — Structured Agent Responses

**Status**: ✅ Completed
**Area**: 10 — Telegram File Delivery
**Approach**: Context-based (pending_actions on AgentContext)

---

## Problem

`RecursiveAgent.run()` returns `str`. Tools had no way to register side-effect actions (like
sending a file) for the messaging interface to execute after `run()` completes.

## Design Decision

Used the **context-based approach** — added `pending_actions` to `AgentContext` rather than
changing `run()`'s return type. This avoids breaking 15+ call sites (CLI, setup wizard, tests)
that only care about the text response.

## Changes

| File | Change |
|------|--------|
| `src/flavia/agent/context.py` | Added `SendFileAction` dataclass; added `pending_actions: list[SendFileAction]` field to `AgentContext` |
| `src/flavia/agent/__init__.py` | Exported `SendFileAction` |
| `src/flavia/agent/recursive.py` | Clears `pending_actions` at start of `run()` |
| `src/flavia/interfaces/base_bot.py` | Removed local `SendFileAction` definition; imports it from `flavia.agent`; wired `_process_agent_response()` to read `pending_actions` |
| `tests/test_structured_agent_response.py` | New: 9 tests covering all plumbing |

## What This Enables (Task 10.2)

A future `send_file` tool can simply do:

```python
from flavia.agent.context import SendFileAction

class SendFileTool(BaseTool):
    def execute(self, args, agent_context):
        agent_context.pending_actions.append(
            SendFileAction(path=str(path), filename=name, caption=caption)
        )
        return f"File queued for delivery: {name}"
```

The full pipeline connects automatically:
`tool → context → _process_agent_response() → BotResponse → _send_response() → _send_file() → Telegram/WhatsApp`

## Backward Compatibility

- `SendFileAction` is importable from `flavia.agent`, `flavia.agent.context`, `flavia.interfaces`,
  and `flavia.interfaces.base_bot` — all resolve to the same class.
- `run()` still returns `str`.
- 1315 tests pass, 6 skipped.

**[← Back to Area 10](../active/area-10-telegram-file-delivery.md)**
