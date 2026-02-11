# Area 5: File Modification Tools

Currently flavIA is read-only: agents can read files, list directories, and search content, but cannot modify any project files. The permission system (`AgentPermissions.can_write()`, `check_write_permission()` in `tools/permissions.py`) already exists and is fully implemented, but no tools use the write path. Adding write tools unlocks the agent's ability to assist with document editing, code modification, report drafting, and other productive workflows.

---

### Task 5.1 -- Write/Edit File Tools

**Difficulty**: Medium | **Dependencies**: None

Create a new `tools/write/` category with tools that let the agent modify project files:

| Tool | Description |
|------|-------------|
| `write_file` | Create a new file or overwrite an existing file entirely |
| `edit_file` | Replace a specific section of a file by matching an exact text fragment and substituting it (similar to how coding assistants do targeted edits) |
| `insert_text` | Insert text at a specific line number in a file |
| `append_file` | Append content to the end of a file |

All write tools enforce the existing `AgentPermissions.write_paths` system via `check_write_permission()` from `tools/permissions.py`. The infrastructure is already in place -- `AgentPermissions.can_write()` and `check_write_permission()` exist but no tools actually call them yet.

Safety considerations:
- All operations are logged with before/after state for auditability
- The `edit_file` tool should require an exact match of the text to be replaced (not regex), to prevent unintended modifications
- Consider creating a `.flavia/file_backups/` directory for automatic backups before edits

**Key files to modify/create**:
- `tools/write/write_file.py` (new)
- `tools/write/edit_file.py` (new)
- `tools/write/__init__.py` (new, with `register_tool()` calls)
- `tools/__init__.py` (add `write` submodule import for auto-registration)

**New dependencies**: None (uses only stdlib and existing permission infrastructure).

---

**[← Back to Roadmap](../roadmap.md)**
