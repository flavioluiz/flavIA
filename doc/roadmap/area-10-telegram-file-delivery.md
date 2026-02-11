# Area 10: Telegram File Delivery

Enable the Telegram bot to send files directly in the chat. The user asks the agent for a file (e.g., "send me the final report for project X"), the agent uses existing tools (`query_catalog`, `list_files`, `search_files`) to locate the file and confirm with the user, then calls the `send_file` tool to deliver it as a Telegram document.

**Current limitation**: `RecursiveAgent.run()` returns a plain `str`. There is no mechanism for a tool to trigger a side effect (like sending a file) back through the messaging interface. This area introduces structured agent responses to bridge that gap.

---

### Task 10.1 -- Structured Agent Responses

**Difficulty**: Medium | **Dependencies**: None (foundational for all file delivery tasks)

Replace the plain `str` return from `agent.run()` with a structured `AgentResponse` that can carry both text and actionable side effects.

**Design**:

```python
@dataclass
class SendFileAction:
    """Instruction to send a file through the messaging interface."""
    path: str          # Absolute path to the file
    filename: str      # Display name for the recipient
    caption: str = ""  # Optional caption/description

@dataclass
class AgentAction:
    """Union of possible agent actions."""
    send_file: SendFileAction | None = None
    # Future actions can be added here (e.g., send_image, request_confirmation)

@dataclass
class AgentResponse:
    """Structured response from an agent run."""
    text: str                          # The text response (always present)
    actions: list[AgentAction] = field(default_factory=list)

    @property
    def has_actions(self) -> bool:
        return len(self.actions) > 0
```

**Backward compatibility**: All existing consumers of `agent.run()` must continue to work.

- `CLIInterface`: uses `response.text` only (file actions are not applicable in CLI; the tool returns a message like "File path: /abs/path/to/file.pdf" as fallback)
- `TelegramBot._handle_message()`: uses `response.text` for the text reply, then iterates `response.actions` to execute side effects (Task 10.3)

**Implementation approach**: The simplest path is to have `RecursiveAgent.run()` return `AgentResponse` and update the two call sites (CLI and Telegram). An alternative is to keep returning `str` and use a shared `AgentContext.pending_actions` list that the caller inspects after `run()` completes -- this avoids changing the return type signature. Both approaches should be evaluated at implementation time; the context-based approach may be simpler for backward compatibility.

**Key files to modify**:
- `agent/base.py` -- define `AgentResponse`, `AgentAction`, `SendFileAction`
- `agent/recursive.py` -- populate `AgentResponse` from `run()`
- `agent/context.py` -- if using the context-based approach, add `pending_actions: list[AgentAction]`
- `interfaces/cli_interface.py` -- adapt to `AgentResponse` or read `pending_actions`
- `interfaces/telegram_interface.py` -- adapt to `AgentResponse` or read `pending_actions`

---

### Task 10.2 -- Send File Tool

**Difficulty**: Easy | **Dependencies**: Task 10.1

Create the `send_file` tool that validates a file path and registers a `SendFileAction` for the messaging interface to execute.

**Important**: This tool does NOT search for files. The agent is already capable of locating files using `query_catalog`, `list_files`, `search_files`, and `get_file_info`. The expected workflow is:

1. User asks for a file
2. Agent uses existing tools to find it
3. Agent confirms the file with the user
4. Agent calls `send_file(path=...)` to deliver it

**Tool schema**:

```python
class SendFileTool(BaseTool):
    name = "send_file"
    description = (
        "Send a file to the user through the messaging interface (e.g., Telegram). "
        "Use this AFTER locating the file with query_catalog or list_files and "
        "confirming with the user which file they want. "
        "In CLI mode, this displays the file path instead of sending."
    )
    category = "content"
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | yes | Path to the file to send (relative to project root or absolute) |
| `caption` | string | no | Optional caption/description to accompany the file |

**Validation**:
- File exists on disk
- File size <= 50 MB (Telegram API limit for `sendDocument`)
- Read permission check via `check_read_permission`
- Path resolves within the project directory (security: no path traversal)

**Behavior by interface**:
- **Telegram**: Registers `SendFileAction` in the agent context. The bot picks it up after `run()` completes and calls `reply_document()`.
- **CLI**: Returns a text message with the absolute file path and size, e.g., `"File ready: /home/user/project/docs/report.pdf (1.2 MB)"`

**Key files to create/modify**:
- `tools/content/send_file.py` (new)
- `tools/content/__init__.py` -- register the new tool

**Note on agent configuration**: The `send_file` tool should be included in the default tool set for Telegram-facing agents. Agents configured in `agents.yaml` should list `send_file` in their `tools` array to enable this capability. CLI-only agents can also include it (with the path-display fallback).

---

### Task 10.3 -- Telegram File Delivery Handler

**Difficulty**: Medium | **Dependencies**: Task 10.1, Task 10.2

Wire the `SendFileAction` into the Telegram bot so files are actually delivered to the user.

**Changes to `TelegramBot._handle_message()`**:

```python
async def _handle_message(self, update, context) -> None:
    # ... existing authorization + agent.run() logic ...

    response = agent.run(user_message)

    # Send text response (existing behavior)
    if response.text:
        # ... existing chunking logic for text ...

    # Process actions (new)
    for action in response.actions:
        if action.send_file:
            await self._deliver_file(update, action.send_file)

async def _deliver_file(self, update, action: SendFileAction) -> None:
    """Send a file as a Telegram document."""
    path = Path(action.path)
    if not path.exists():
        await update.message.reply_text(f"Error: file not found: {action.filename}")
        return

    try:
        with open(path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=action.filename,
                caption=action.caption or None,
            )
        self._log_event(
            update,
            "file:sent",
            f"path={action.path} size={path.stat().st_size}",
        )
    except Exception as e:
        self._log_event(update, "file:error", str(e)[:200])
        await update.message.reply_text(f"Error sending file: {str(e)[:200]}")
```

**Error handling**:
- File not found (deleted between tool execution and delivery)
- File too large (double-check at send time)
- Telegram API timeout/network error
- Permission denied on file read

**Logging**: Every file send (success or failure) is logged with `_log_event` using action `file:sent` or `file:error`, including path and file size.

**MIME type**: `python-telegram-bot` auto-detects MIME types, but we can optionally pass `content_type` from Python's `mimetypes.guess_type()` for edge cases.

**Key files to modify**:
- `interfaces/telegram_interface.py` -- add `_deliver_file()`, update `_handle_message()`

---

## Expected User Interaction Flow

```
User:  "me envie o relatorio final do projeto X"
         |
Agent:  [calls query_catalog(text_search="relatorio final projeto X")]
         |
Agent:  "Encontrei 2 arquivos:
         1. docs/relatorios/projeto-x-final-v2.pdf (1.2 MB)
         2. docs/relatorios/projeto-x-final-v1.pdf (980 KB)
         Qual deseja receber?"
         |
User:  "o v2"
         |
Agent:  [calls send_file(path="docs/relatorios/projeto-x-final-v2.pdf")]
         |
Agent:  "Enviando o arquivo projeto-x-final-v2.pdf..."
         |
Bot:    [reply_document() -- file appears in Telegram chat]
```

---

## Dependency Graph

```
Task 10.1 (Structured Agent Responses) ──┬── Task 10.2 (Send File Tool)
                                          └── Task 10.3 (Telegram File Delivery Handler)
Task 10.2 ── Task 10.3

Cross-area:
  Beneficia-se de Task 3.4 (Abstract Messaging Interface) -- AgentResponse/actions
    se encaixa naturalmente numa abstração multi-plataforma
  Beneficia-se de Task 3.1 (YAML Bot Config) -- config de tamanho max por bot
  Independente de todas as demais áreas
```

---

## Estimates

| Task | Difficulty | Effort |
|------|------------|--------|
| 10.1 Structured Agent Responses | Medium | 1-2 days |
| 10.2 Send File Tool | Easy | 0.5-1 day |
| 10.3 Telegram File Delivery Handler | Medium | 1 day |
| **Total** | | **2.5-4 days** |

---

**[<- Back to Roadmap](../roadmap.md)**
