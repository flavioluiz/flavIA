# Write Tool Safety Features

flavIA provides comprehensive safety mechanisms for file modification operations to prevent accidental data loss and ensure informed user consent.

## Overview

All write operations go through multiple safety layers:

1. **Permission System** - Path-based access control
2. **User Confirmation** - Interactive approval with operation preview
3. **Automatic Backups** - Timestamped copies before destructive operations
4. **Dry-Run Mode** - Preview changes without modifying files

## Write Tools

Seven write tools are available, each with full safety integration:

| Tool | Purpose |
|------|---------|
| `write_file` | Create new file or overwrite existing file |
| `edit_file` | Replace exact text fragment in a file |
| `insert_text` | Insert text at specific line number |
| `append_file` | Append content to end of file |
| `delete_file` | Delete a file |
| `create_directory` | Create directory with parents |
| `remove_directory` | Remove directory (optionally recursive) |

## Permission System

The permission system controls which paths agents can read from and write to.

### Default Behavior

- **Read access**: Base directory and all subdirectories
- **Write access**: Base directory and all subdirectories (with confirmation)
- **Blocked**: Paths outside base directory (prevents path traversal)

### Explicit Permissions

Configure in `agents.yaml`:

```yaml
main:
  permissions:
    explicit: true
    read_paths:
      - "docs/"
      - "src/"
      - "tests/"
    write_paths:
      - "docs/"
      - "output/"
```

When `explicit: true`, **only** listed paths are accessible. Empty lists deny all access.

## User Confirmation

### Interactive Confirmation

When an agent requests a file operation, you see:

```text
Write confirmation: Edit file: ./src/config.py (replacing 245 chars)

Changes:
--- a/src/config.py
+++ b/src/config.py
@@ -10,7 +10,7 @@

 class Config:
     def __init__(self):
-        self.timeout = 30
+        self.timeout = 60
         self.retry = 3

Allow? [y/N]
```

Features of the preview:
- **Diffs** for edit operations (colored syntax highlighting)
- **Content preview** for write/append operations (truncated if large)
- **Context lines** for insert operations (what's before/after)
- **File content** for delete operations (first lines preview)
- **Directory contents** for directory removal

### Declining Operations

Type `n` or press Enter (default is No) to decline. The agent is notified:

```text
Operation cancelled by user
```

The agent can adjust its approach or ask for clarification.

## Automatic Backups

Before any destructive operation (overwrite, edit, delete), a timestamped backup is created:

```text
.flavia/file_backups/config.py.20250212_143022_123456.bak
```

Backups are created:
- **Before overwriting** existing files
- **Before editing** file content
- **Before deleting** files
- **Before appending** to existing files
- **Not created** for new file creation or directory operations

### Backup Naming

Format: `<original-name>.<YYYYMMDD>_<HHMMSS>_<microsecond>.bak`

Example:
```
report.md.20250212_143022_123456.bak
```

### Restoring from Backup

Backups are regular files that can be manually restored:

```bash
# Find recent backup
ls -lt .flavia/file_backups/

# Restore
cp .flavia/file_backups/config.py.20250212_143022_123456.bak src/config.py
```

## Dry-Run Mode

Preview all file operations without actually modifying anything.

### Usage

```bash
flavia --dry-run
```

When active, the CLI shows:

```text
Active model: openai:gpt-4o | DRY-RUN MODE
```

### How It Works

1. Agent requests file operation
2. User sees normal confirmation prompt with preview
3. User approves operation
4. **Instead of executing**, tool returns:
   ```
   [DRY-RUN] Would edit: src/config.py
   --- a/src/config.py
   +++ b/src/config.py
   ...
   ```
5. No files are modified, no backups created

### Use Cases

- **Testing agent workflows** - See what the agent plans to do
- **Exploring capabilities** - Learn how write tools work safely
- **Reviewing batch operations** - Preview multiple file changes
- **Teaching/demos** - Show file operations without risk

### Example Session

```bash
$ flavia --dry-run

You: Please update the timeout in config.py to 60 seconds

Agent [gpt-4o]: I'll update the timeout setting in src/config.py.

Write confirmation: Edit file: ./src/config.py (replacing 245 chars)

Changes:
--- a/src/config.py
+++ b/src/config.py
@@ -10,7 +10,7 @@

 class Config:
     def __init__(self):
-        self.timeout = 30
+        self.timeout = 60
         self.retry = 3

Allow? [y/N] y

Agent [gpt-4o]: [DRY-RUN] Would edit: src/config.py

--- a/src/config.py
+++ b/src/config.py
...

The timeout has been updated to 60 seconds.

# File is unchanged!
$ grep timeout src/config.py
        self.timeout = 30
```

## Configuration Modes

### Auto-Approve (Not Recommended)

For batch/CI workflows, you can bypass confirmation:

```python
from flavia.tools.write_confirmation import WriteConfirmation

wc = WriteConfirmation()
wc.set_auto_approve(True)
```

⚠️ **Warning**: This removes the safety confirmation. Only use in controlled environments with explicit permissions configured.

### Telegram Mode

Write operations are **denied by default** in Telegram mode since there's no interactive confirmation mechanism.

To enable writes in Telegram, you must implement a custom confirmation callback.

## Safety Best Practices

1. **Start with dry-run** - Use `--dry-run` when testing new workflows
2. **Review previews** - Always read the diff/preview before approving
3. **Use explicit permissions** - Limit write access to specific directories
4. **Keep backups** - The `.flavia/file_backups/` directory is your safety net
5. **Version control** - Use git for additional protection
6. **Test incrementally** - Make small changes, verify, then proceed

## Technical Details

### Fail-Safe Design

The confirmation system defaults to **deny** if:
- No confirmation handler is configured
- Confirmation callback raises an exception
- User doesn't explicitly approve

### Preview Generation

Previews are generated **before** confirmation to show exactly what will happen:

1. For **edits**: unified diff with 3 lines of context
2. For **writes**: first 20 lines of content (truncated if longer)
3. For **inserts**: 3 lines before and after insertion point
4. For **deletes**: first 10 lines of file content
5. For **directories**: list of contents (up to 20 items)

### Dry-Run Propagation

The `dry_run` flag propagates to child agents:

```python
# Parent context
parent_ctx.dry_run = True

# Child inherits dry_run
child_ctx = parent_ctx.create_child_context(...)
assert child_ctx.dry_run is True
```

This ensures sub-agents also operate in preview-only mode.

### Backward Compatibility

The preview system is backward compatible:
- Old-style confirmation callbacks (without preview parameter) still work
- Existing code continues to function unchanged
- Preview parameter is optional

## See Also

- [Usage Guide](usage.md) - Interactive commands and flags
- [Configuration](configuration.md) - Permission and agent setup
- [Architecture](architecture.md) - Tool system design
