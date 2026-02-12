# Area 5: File Modification Tools ✓

**Status**: Complete

This area added write capabilities to flavIA's previously read-only agent system. The permission infrastructure (`AgentPermissions.can_write()`, `check_write_permission()` in `tools/permissions.py`) already existed but no tools used the write path. Seven write tools were implemented, along with user confirmation, operation previews, dry-run support, and an automatic backup system.

---

### Task 5.1 -- Write/Edit File Tools ✓

**Difficulty**: Medium | **Dependencies**: None | **Status**: Done

Created `tools/write/` with seven tools that let the agent modify project files, plus supporting infrastructure for safe write operations.

#### Tools implemented

| Tool | Description |
|------|-------------|
| `write_file` | Create a new file or overwrite an existing file entirely |
| `edit_file` | Replace a specific text fragment by exact match (must occur exactly once) |
| `insert_text` | Insert text at a specific line number (1-based) |
| `append_file` | Append content to the end of a file (creates the file if it doesn't exist) |
| `delete_file` | Delete a file (with automatic backup before deletion) |
| `create_directory` | Create a directory (equivalent to `mkdir -p`) |
| `remove_directory` | Remove a directory (empty, or recursive with confirmation) |

#### Safety mechanisms

1. **Permission enforcement**: All tools check `AgentPermissions.write_paths` via `check_write_permission()`. If the agent lacks write access to the target path, the operation is denied.

2. **User confirmation**: All write operations require explicit user approval before execution. The mechanism uses a callback pattern:
   - `WriteConfirmation` class in `tools/write_confirmation.py` with three modes:
     - **Callback mode**: delegates to a registered callback (CLI prompt, etc.)
     - **Auto-approve mode**: for testing and non-interactive contexts
     - **Fail-safe deny**: if no confirmation handler is configured, operations are denied
   - The CLI interface registers a callback that temporarily restores terminal settings (since the agent runs in a thread with suppressed input), presents a `[y/N]` prompt, and re-suppresses after the answer.
   - Telegram interface: no confirmation handler is set, so write operations are naturally denied (fail-safe).

3. **Automatic backups**: Before destructive file operations (write, edit, insert, append, delete), a backup is created in `.flavia/file_backups/` with a high-resolution timestamped filename (e.g., `config.yaml.20250210_143022_123456.bak`). The `FileBackup` class in `tools/backup.py` handles backup creation and old backup cleanup.

4. **Edit safety**: `edit_file` requires the text to replace to appear exactly once in the file. If it appears zero times or more than once, the operation is rejected with a clear error message.

### Task 5.2 -- Write Operation Preview + Dry-Run Mode ✓

**Difficulty**: Medium | **Dependencies**: Task 5.1 | **Status**: Done

Extended the write stack with pre-execution previews and a non-destructive execution mode.

#### Features implemented

1. **Operation previews in confirmation flow**:
   - New `tools/write/preview.py` module with `OperationPreview` and formatting helpers
   - Unified diffs for edits/overwrites when possible
   - Content previews for write/append operations
   - Context-aware insertion previews (before/after lines)
   - File preview before delete and directory listing before recursive removal

2. **Dry-run mode (`--dry-run`)**:
   - New runtime flag propagated through `Settings` and `AgentContext`
   - All seven write tools now support preview-only execution after normal permission and confirmation checks
   - No filesystem modifications in dry-run mode
   - No backup creation in dry-run mode

3. **CLI visualization improvements**:
   - Confirmation callback now accepts optional preview payloads
   - Rich diff rendering in CLI for better review before approval
   - Explicit DRY-RUN indicator in active model header

4. **Backward compatibility and robustness**:
   - Legacy confirmation callbacks without preview parameter remain supported
   - Callback signature detection avoids retry-on-`TypeError` ambiguity and duplicate callback side effects

#### Files created

| File | Purpose |
|------|---------|
| `tools/write_confirmation.py` | WriteConfirmation class with callback/auto-approve/deny modes |
| `tools/backup.py` | FileBackup class with timestamped backups and cleanup |
| `tools/write/__init__.py` | Package init, imports all 7 tool modules for auto-registration |
| `tools/write/write_file.py` | Write/overwrite file tool |
| `tools/write/edit_file.py` | Exact text replacement tool |
| `tools/write/insert_text.py` | Line-number insertion tool |
| `tools/write/append_file.py` | File append tool |
| `tools/write/delete_file.py` | File deletion tool |
| `tools/write/create_directory.py` | Directory creation tool |
| `tools/write/remove_directory.py` | Directory removal tool |
| `tools/write/preview.py` | Preview dataclass and formatting helpers for write operations |

#### Files modified

| File | Change |
|------|--------|
| `tools/__init__.py` | Added `from . import write` for auto-registration |
| `tools/permissions.py` | Added `can_write_path()` boolean helper |
| `agent/context.py` | Added `write_confirmation` field, propagated in `create_child_context()` |
| `agent/status.py` | Added display formatters for all 7 write tools |
| `interfaces/cli_interface.py` | WriteConfirmation callback with terminal restore logic |
| `interfaces/commands.py` | `recreate_agent()` preserves write_confirmation across agent switches |
| `cli.py` | Added `--dry-run` CLI flag |
| `config/settings.py` | Added `dry_run` runtime setting |
| `config/loader.py` | `.gitignore` template includes `file_backups/` |

#### Tests

| Test file | Count | Coverage |
|-----------|-------|----------|
| `tests/test_write_tools.py` | 35 | All 7 tools: create, overwrite, edit, insert, append, delete, mkdir, rmdir |
| `tests/test_write_tools_security.py` | 16 | Path traversal, symlink attacks, permission denial, confirmation gate |
| `tests/test_write_confirmation.py` | 16 | Callback modes, preview compatibility, fail-safe deny, callback signature handling |
| `tests/test_backup.py` | 10 | Backup creation, timestamped names, cleanup of old backups |
| `tests/test_preview.py` | 23 | Diff generation, content/file/dir preview formatting, insertion context |
| `tests/test_dry_run.py` | 17 | Dry-run behavior for all write tools, no filesystem changes, no backups |

All project tests pass (527 passed, 6 skipped).

---

**[Back to Roadmap](../roadmap.md)**
