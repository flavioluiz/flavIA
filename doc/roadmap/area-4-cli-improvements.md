# Area 4: CLI Improvements

The interactive CLI (`cli_interface.py`) and the CLI flags (`cli.py`) have grown organically and now contain several redundancies, inconsistencies, and gaps. This area covers consolidating existing commands, adding runtime switching capabilities, and introducing features that make the CLI a fully self-contained interface for managing flavIA without needing to restart.

**Current problems identified**:

- `/models` and `/providers` show nearly identical information (models grouped by provider) with different formatting. Neither allows any action.
- `--list-models`, `--list-providers`, `--list-tools` duplicate the slash commands at the flag level with slightly different output detail.
- `/tools` shows only tool names; `--list-tools` shows names, descriptions, and categories. Inconsistent depth.
- `/config` (slash) shows only file paths; `--config` (flag) shows paths plus active settings. Same name, different content.
- `--setup-provider`, `--manage-provider`, and `--test-provider` are only available as CLI flags -- users must exit the interactive session to use them.
- No runtime model or agent switching mid-session.
- No concept of a default "standard" agent or global (user-level) agent definitions.
- The `/agent_setup` command (Quick mode) only manages model assignments; it cannot edit contexts, tools, or create/delete agents.

---

### Task 4.1 -- Consolidate Info Commands ✓ COMPLETED

**Difficulty**: Easy | **Dependencies**: None | **Status**: DONE

~~Merge and rationalize the overlapping information commands:~~

**Implementation summary**:

1. **Created `src/flavia/display.py`** — New shared module with 4 display functions:
   - `display_providers()` — Shows providers with globally indexed models
   - `display_tools()` — Shows tools grouped by category with descriptions
   - `display_tool_schema()` — Shows full schema for a specific tool
   - `display_config()` — Shows config paths and active settings

2. **Removed `/models` and `--list-models`** — Redundant with `/providers`

3. **Updated commands to use shared module**:
   - `/providers` and `--list-providers` — Providers with indexed models
   - `/tools` and `--list-tools` — Categorized tools with descriptions
   - `/tools <name>` — Full tool schema (parameters, types, defaults)
   - `/config` and `--config` — Paths + active settings

4. **Plain text output for piping** — CLI flags detect non-TTY and strip ANSI codes

**Files modified**:
- `src/flavia/display.py` (new)
- `src/flavia/cli.py`
- `src/flavia/interfaces/cli_interface.py`
- `src/flavia/setup/provider_wizard.py`

---

### Task 4.2 -- Runtime Agent Switching in CLI ✓ COMPLETED

**Difficulty**: Easy | **Dependencies**: None | **Status**: Done

Implemented `/agent` slash command for runtime agent switching:

- `/agent` (no args) -- Lists all available agents (main + subagents) with model, tools, and context summary. Marks the active agent with `[active]`.
- `/agent <name>` -- Switches to a different agent, validates the name exists, creates a new agent instance, resets conversation, and updates the prompt to show `[agent_name] You:` for non-main agents.

**Files modified**:
- `src/flavia/display.py` -- Added `display_agents()` function
- `src/flavia/interfaces/cli_interface.py` -- Added `/agent` command handler, `_get_available_agents()` helper, updated `_read_user_input()` for agent prefix, updated `print_help()`
- `doc/usage.md` -- Documented new commands

---

### Task 4.3 -- Runtime Model Switching in CLI ✓ COMPLETED

**Difficulty**: Easy | **Dependencies**: None | **Status**: DONE

Implemented `/model` slash command for runtime model switching:

**Invocation and Behavior:**
- `/model` — Show current active model with provider, model name, reference (provider:model_id), max tokens, and description
- `/model <ref>` — Switch to a different model. Accepts index number, model ID, or `provider:model_id` format. Recreates the agent with the new model, resets conversation
- `/model list` — Alias for `/providers` (quick access to see all available models)

This replaces the workflow of exiting, running `flavia -m <model>`, and losing context. The model change updates `settings.default_model` for the session (not persisted to disk unless explicitly saved).

**Implementation summary:**
- Added `/model` command handler in `cli_interface.py` with three behaviors
- Added `_display_current_model()` helper to show current model details
- Added `_models_are_equivalent()` helper to check model equivalence across reference formats
- Updated `print_help()` with `/model` command documentation
- Follows same pattern as `/agent` command: validate before switch, rollback on error, show confirmation

**Files modified:**
- `src/flavia/interfaces/cli_interface.py` — Added `/model` command handler, helper functions, updated help text
- `doc/roadmap/area-4-cli-improvements.md` — Marked task as completed
- `CHANGELOG.md` — Documented new feature

---

### Task 4.4 -- In-Session Provider & Model Management ✓ COMPLETED

**Difficulty**: Medium | **Dependencies**: Task 4.1 | **Status**: DONE

Exposed provider management wizards as interactive slash commands:

| Command | Equivalent flag | Description |
|---------|----------------|-------------|
| `/provider-setup` | `--setup-provider` | Run the provider configuration wizard |
| `/provider-manage [id]` | `--manage-provider` | Manage models for a provider |
| `/provider-test [id]` | `--test-provider` | Test connection to a provider |

**Implementation summary**:
- Added `/provider-setup` — calls `run_provider_wizard(target_dir=settings.base_dir)`
- Added `/provider-manage [id]` — calls `manage_provider_models(settings, provider_id, target_dir=settings.base_dir)`
- Added `/provider-test [id]` — resolves provider, validates API key/model, calls `test_provider_connection()`

After config changes, commands prompt to use `/reset` to reload (same pattern as `/agent_setup`).

**Files modified**:
- `src/flavia/interfaces/commands.py` — Added three command handlers
- `doc/usage.md` — Documented new commands
- `CHANGELOG.md` — Added feature entry
- `doc/roadmap/area-4-cli-improvements.md` — Marked task completed

---

### Task 4.5 -- Standard Default Agent

**Difficulty**: Medium | **Dependencies**: None

Define a built-in "standard" agent that is always available, regardless of whether the project has an `agents.yaml` file. This agent:

- Uses the project's default model (from `providers.yaml` or environment)
- Has a general-purpose system prompt suitable for academic research and writing assistance
- Is registered as `"standard"` in the agent list and can be switched to via `/agent standard`
- Serves as the fallback when no `agents.yaml` exists (replacing the current minimal hardcoded fallback in `create_agent_from_settings()`)
- Cannot be deleted or overridden by project config (always present alongside project-defined agents)

The standard agent should have a reasonable default tool set (file reading, search, directory listing) and a well-crafted academic-assistant system prompt.

**Key files to modify**:
- `interfaces/cli_interface.py` -- update `create_agent_from_settings()` to always register the standard agent
- `agent/profile.py` -- add a `standard_profile()` class method or standalone function
- Consider a `defaults/standard_agent.yaml` file for the default configuration

---

### Task 4.6 -- Global Agent Definitions

**Difficulty**: Medium | **Dependencies**: Task 2.1 (structured profiles), Task 4.2 (agent switching)

Support user-level agent definitions in `~/.config/flavia/agents.yaml` that are available across all projects. These complement project-local agents in `.flavia/agents.yaml`.

Resolution order (later overrides earlier for same-name agents):
1. Built-in standard agent (Task 4.5)
2. User-level agents (`~/.config/flavia/agents.yaml`)
3. Project-level agents (`.flavia/agents.yaml`)

Example global agents:

```yaml
# ~/.config/flavia/agents.yaml
beamer-specialist:
  name: "Beamer Presentation Expert"
  role: "LaTeX Beamer academic presentation specialist"
  context: |
    You specialize in creating and improving LaTeX Beamer presentations
    for academic conferences. You follow best practices for slide design:
    minimal text, clear figures, consistent themes, proper use of
    columns, blocks, and overlays.
  tools: [read_file, list_files, search_files]

paper-reviewer:
  name: "Academic Paper Reviewer"
  role: "critical reviewer of academic papers"
  context: |
    You review academic papers with the rigor of a top-tier venue
    reviewer. You evaluate: novelty, methodology, experimental design,
    writing clarity, and proper citation of related work.
  tools: [read_file, search_files]

code-analyst:
  name: "Code Analysis Expert"
  context: |
    You specialize in code review, refactoring suggestions, and
    identifying potential bugs, performance issues, and security
    concerns in source code.
  tools: [read_file, list_files, search_files, get_file_info]
```

The `/agent` command (Task 4.2) lists agents from all three sources with source labels (`[built-in]`, `[global]`, `[project]`).

**Key files to modify**:
- `config/settings.py` -- load and merge global + local agents configs
- `config/loader.py` -- discover user-level `agents.yaml`
- `interfaces/cli_interface.py` -- update agent listing to show sources

---

### Task 4.7 -- Unified Slash Command Help System ✓ COMPLETED

**Difficulty**: Easy | **Dependencies**: None | **Status**: DONE

~~Improve the `/help` command from a static text block to a structured, categorized system:~~

**Implementation summary**:

1. Added command registry and dispatch layer (`register_command`, `dispatch_command`, `get_command_help`, `get_help_listing`) in `src/flavia/interfaces/commands.py`
2. Replaced static help output with categorized `/help` and detailed `/help <command>` generated from command metadata
3. Ensured aliases, examples, usage text, and related commands are part of the metadata-driven help output

**Files modified**:
- `src/flavia/interfaces/commands.py` — registry + metadata + handlers + help generation
- `src/flavia/interfaces/cli_interface.py` — command dispatch integration
- `doc/usage.md` — documented unified help and command categories

1. **`/help`** (no args): Show all commands organized by category with one-line descriptions:
   - **Session**: `/reset`, `/quit`
   - **Agents**: `/agent`, `/agent_setup`
   - **Models & Providers**: `/model`, `/providers`, `/provider-setup`, `/provider-manage`, `/provider-test`
   - **Information**: `/tools`, `/config`, `/catalog`
   - **Setup**: `/agent_setup`

2. **`/help <command>`**: Show detailed help for a specific command -- description, arguments, examples, and related commands.

3. Register commands in a lightweight command registry (a dict mapping command names to handler functions and metadata) instead of the current `if/elif` chain in `run_cli()`. This makes it easy to add new commands and auto-generate help text.

**Key files to modify**:
- `interfaces/cli_interface.py` -- implement command registry, update `/help` handler, refactor `run_cli()` dispatch

---

### Task 4.8 -- Expand questionary Adoption for Interactive Prompts ✓ COMPLETED

**Difficulty**: Medium | **Dependencies**: Task 4.7 (command registry) | **Status**: DONE

**Implementation summary**:

1. **Added questionary wrappers in `prompt_utils.py`** with automatic non-TTY fallback:
   - `is_interactive()` — Detects TTY for stdin/stdout
   - `q_select()` — Arrow-key menu selection with numbered fallback
   - `q_autocomplete()` — Text input with completion suggestions
   - `q_path()` — File/directory path with tab completion
   - `q_password()` — Masked password input
   - `q_confirm()` — Yes/no confirmation
   - `q_checkbox()` — Multi-select with checkboxes

2. **Converted numbered menus** in:
   - `setup_wizard.py`: Mode selection (Quick/Revise/Full), config choice (Simple/Analyze), model selection
   - `provider_wizard.py`: Provider type, model selection, location choice, default model, action menu, model removal
   - `catalog_command.py`: Main menu navigation

3. **Added agent autocomplete** in `/agent` command when no args provided

4. **Created test helpers** in `tests/helpers/questionary_mocks.py`

5. **Removed obsolete functions**: `safe_prompt_with_style()`, `safe_confirm_with_style()` removed from prompt_utils.py

**Files modified**:
- `src/flavia/setup/prompt_utils.py` — New wrappers, removed obsolete functions
- `src/flavia/setup_wizard.py` — Converted to `q_select()`
- `src/flavia/setup/provider_wizard.py` — Converted menus and selection
- `src/flavia/interfaces/catalog_command.py` — Converted menu
- `src/flavia/interfaces/commands.py` — Agent autocomplete
- `tests/helpers/questionary_mocks.py` — New test utilities
- `tests/test_setup_wizard_flow.py` — Updated mocks
- `tests/test_catalog_command.py` — Updated mocks
- `tests/test_provider_management_regressions.py` — Updated mocks

---

**Original specification (for reference)**:

flavIA's interactive CLI currently uses plain `input()` for all user prompts (via `safe_prompt()`/`safe_confirm()` in `prompt_utils.py`), with `questionary.checkbox()` used only in 2 places. The `questionary` library (already a dependency) provides a rich set of interactive prompts that significantly improve UX: autocomplete, file path selection with tab completion, single/multi-select menus, password masking, and more.

This task expands `questionary` adoption across all interactive CLI prompts, making the interface more discoverable, efficient, and consistent. The implementation targets 7 specific areas while maintaining backward compatibility for non-TTY environments.

**Important decision -- No InquirerPy**: After evaluating alternatives, `questionary` should remain the sole interactive prompt library. InquirerPy (`inquirerpy`) is abandoned (last release June 2022, dev status Pre-Alpha, only supports Python 3.8-3.10), while `questionary` is actively maintained (last release August 2025, 19,200+ projects depend on it, supports Python 3.9-3.13). All functionality needed is already available in questionary; fuzzy search can be added later with `iterfzf` if needed.

**questionary prompt types available** (from official docs, all usable in flavIA):

| Prompt Type | Description | Current flavIA use | Target for expansion |
|---|---|---|---|
| `questionary.text()` | Free text input | ❌ (uses `input()`) | Optional for text fields where advanced features needed |
| `questionary.password()` | Hidden text input | ❌ (uses `getpass`) | API keys, passwords, tokens |
| `questionary.path()` | File/directory path with tab completion | ❌ | PDF selection in setup, catalog add source, file operations |
| `questionary.confirm()` | Yes/no | ❌ (uses `safe_confirm()`) | Replace simple confirmations |
| `questionary.select()` | Pick one from list (arrow keys, shortcuts) | ❌ | Numbered lists → menu selection |
| `questionary.rawselect()` | Pick one by number | ❌ | Alternative for numeric selection |
| `questionary.checkbox()` | Multi-select with space toggle | ✅ (2 places) | Potential expansion for batch operations |
| `questionary.autocomplete()` | Free text with suggestions (`match_middle`, `ignore_case`) | ❌ | Slash commands, agent names, file search |
| `questionary.press_any_key_to_continue()` | Wait for keypress | ❌ | Pause before long outputs |

**7 specific implementations**:

1. **Slash command autocomplete** (`questionary.autocomplete()`):
   - Detect when user input starts with `/` and show available slash commands with suggestions
   - Filter as user types, support `match_middle=True` for easier matching
   - After selection, trigger the corresponding command handler
   - Integration with the command registry from Task 4.7

2. **Agent name autocomplete**:
   - `/agent <tab>` shows all available agent names (built-in standard, global, project-level)
   - Filter as user types with substring matching
   - After selection, switch to the agent

3. **File path autocomplete** (`questionary.path()`):
   - Replace plain `input()` for all file path entry points
   - **Setup wizard**: PDF source file selection (supports `file_filter=["*.pdf"]`, `only_files=True`)
   - **Catalog browser**: Add source files/directories with tab completion
   - **Config management**: Paths to config files, agent YAMLs, etc.
   - Supports multi-column view, custom `get_paths` callback, `only_directories=True` for directory selection

4. **Model/provider selection** (`questionary.select()`):
   - Replace the manual numbered list + `input()` pattern used in `_select_model_for_setup()` and provider wizard
   - Show available models in an arrow-key navigable menu
   - Include metadata (provider name, context size, rate limits) in the selection
   - Support keyboard shortcuts (e.g., `1`, `2`, `3`) for power users

5. **Setup wizard menus**:
   - Mode selection: `[Quick] Full mode with AI-generated agents` vs `[Revise] Revise existing config` vs `[Full] Full manual setup`
   - Config choice: `[1] Simple minimal config` vs `[2] AI-assisted analysis` vs `[3] Advanced with all options`
   - Catalog menu options (add, scan, search, remove)
   - Use `questionary.select()` for cleaner UX than numbered lists

6. **Catalog browser menus**:
   - Replace `console.input()` menu navigation with `questionary.select()`
   - File search with `questionary.autocomplete()` for catalog file names
   - More discoverable than numeric menu choices

7. **Password/API key entry** (`questionary.password()`):
   - Replace `getpass.getpass()` for API keys and passwords
   - During provider setup wizard: prompt for API keys with masking
   - Email/password for external services ( Tasks 7.1, 7.2)
   - `questionary.password()` integrates better with prompt_toolkit's styling than `getpass`

**Architecture decisions**:

1. **questionary as sole library**: Keep questionary, do NOT add InquirerPy. Document rationale in roadmap (active vs abandoned, Python version support, feature parity).

2. **Fallback for non-TTY**: Maintain plain `input()` or `console.input()` fallback when:
   - `stdin` is not a TTY (e.g., piping from a file: `cat script.txt | flavia`)
   - `questionary` import fails (edge case)
   - User explicitly opts out (optional `--no-interactive` flag)
   - Detection: `sys.stdin.isatty()` or check for `InquirerPy-compatible` environment

3. **Migration path from readline to prompt_toolkit history**:
   - Current: `readline` imports and config loaded but never fully configured (no `completer` or specific `bind` for tab completion)
   - questionary uses `prompt_toolkit` which has its own history mechanism (`PromptSession` with `history` parameter)
   - Plan: Gradually migrate to `prompt_toolkit.PromptSession` for the main chat loop
   - Until Task 4.8 is complete, keep existing `readline` config for backward compatibility
   - The migration can happen incrementally: first wrap `questionary` calls, then replace the main chat `input()` loop with `prompt_toolkit.PromptSession`

4. **Role of `prompt_utils.py` after migration**:
   - Option A: Convert `prompt_utils.py` to thin wrappers over questionary, keeping API for backward compatibility with existing code
   - Option B: Directly use questionary in most places, keep `prompt_utils.py` only for non-TTY fallback and special cases
   - Recommendation: Option B -- simpler, fewer abstraction layers, questionary API is already excellent
   - The `safe_prompt_with_style()` and `safe_confirm_with_style()` functions can be removed (questionary handles styling natively)

5. **Testing impact**:
   - Current tests that mock `input()` need to be updated for questionary prompts
   - questionary prompts are typically tested with `pytest-monkeypatch` or by providing answers via a callback
   - Example: `questionary.select(...).ask_async()` can be mocked with `pytest-mock` or by providing `Input` sequence
   - Add utility test helpers in `tests/helpers/` for common prompt patterns
   - Consider using `pytest-interactive` for manual testing verification

6. **What can be removed/simplified**:
   - Manual numbered-list pattern (e.g., `print("[1] Option 1\n[2] Option 2")` then `input("Select: ")`) → replaced by `questionary.select()`
   - `safe_prompt_with_style()` and `safe_confirm_with_style()` (style is built into questionary)
   - Some `readline` config (prompt_toolkit handles history and completion)
   - Custom validation functions that replicate questionary's built-in `validate` parameter

**Dependencies impact**:

- **No new dependencies**: `questionary>=2.0.0` is already in `pyproject.toml`
- questionary pulls in `prompt_toolkit` as a required dependency (already present)
- If fuzzy search is needed later: consider `iterfzf` or `pyfzf` as lightweight optional extras
- No changes to `pyproject.toml` needed for this task

**Implementation order** (within Task 4.8):

1. **Phase 1 -- Command autocomplete** (highest value, relatively simple):
   - Integrate `questionary.autocomplete()` with the command registry from Task 4.7
   - Detect `/` prefix in main chat loop
   - Test with existing `/agent`, `/reset`, `/quit` commands

2. **Phase 2 -- Replace numbered menus with `questionary.select()`**:
   - Setup wizard mode selection, config choice, catalog menu
   - Model/provider selection wizards
   - Immediate UX improvement with minimal risk

3. **Phase 3 -- File path autocomplete**:
   - Replace file path inputs with `questionary.path()`
   - Setup wizard PDF selection, catalog add source
   - Add `file_filter` and `only_directories` as appropriate

4. **Phase 4 -- Agent name autocomplete**:
   - `/agent` command with `questionary.autocomplete()` showing available agents
   - Filter from built-in, global, and project-level agents

5. **Phase 5 -- Password masked input**:
   - Replace `getpass` with `questionary.password()`
   - Provider setup wizard API key entry
   - Services setup (email, calendar) in future tasks

6. **Phase 6 -- Non-TTY fallback**:
   - Implement `is_interactive()` check for TTY detection
   - Fallback to `input()`/`console.input()` when not interactive
   - Add `--no-interactive` flag if needed

7. **Phase 7 -- Cleanup**:
   - Remove obsolete functions (`safe_prompt_with_style()`, numbered-list helpers)
   - Update tests to work with questionary prompts
   - Document the migration for contributors

**Key files to modify**:
- `src/flavia/interfaces/cli_interface.py` -- main chat loop, command dispatch, slash commands
- `src/flavia/setup/prompt_utils.py` -- simplify/refactor wrappers, add non-TTY fallback
- `src/flavia/setup_wizard.py` -- replace numbered menus with `questionary.select()`, file path selection with `questionary.path()`
- `src/flavia/setup/provider_wizard.py` -- model selection with `questionary.select()`, password entry with `questionary.password()`
- `src/flavia/interfaces/catalog_command.py` -- replace `console.input()` menus with questionary
- `tests/**/*test*.py` -- update mock patterns for questionary prompts
- `pyproject.toml` -- no changes (questionary already present)

**New dependencies**: None (questionary already a dependency).

---

### Task 4.9 -- Configurable LLM API Timeout Management

**Difficulty**: Medium | **Dependencies**: None

Add a configurable timeout system for LLM API calls to allow runtime adjustment of timeout values and better handle different provider requirements:

**Requirements**:

1. **CLI flag for timeout configuration**:
   - Add `--api-timeout <seconds>` flag to set the API request timeout (default: 600s)
   - Add `--connect-timeout <seconds>` flag to set the connection timeout (default: 10s)
   - Timeouts should apply to both the main OpenAI client and the fallback httpx.Client

2. **Configuration file support**:
   - Allow timeout values to be set in `.flavia/config.yaml`:
     ```yaml
     timeouts:
       api: 600
       connect: 10
     ```

3. **Provider-level overrides** (optional enhancement):
   - Allow per-provider timeout overrides in `providers.yaml`:
     ```yaml
     providers:
       synthetic:
         api_base_url: "https://api.synthetic.new/openai/v1"
         timeout: 300  # override for this specific provider
         connect_timeout: 5
     ```

4. **Better timeout UX**:
   - Show current timeout values in `/config` output
   - Add `/timeout show` and `/timeout set <seconds>` slash commands for runtime adjustments
   - Provide helpful error messages suggesting timeout adjustments when timeouts occur

5. **Graceful timeout handling**:
   - Ensure timeout exceptions don't leave the agent in an inconsistent state
   - Allow retry mechanism with increased timeout on explicit user request
   - Consider exponential backoff for transient network issues

**Rationale**:
- Current hardcoded 600s timeout may be insufficient for very long LLM generations on slow connections
- Different providers and models have varying response times
- Some academic workflows (e.g., multi-tool chains, long reasoning models) may benefit from longer timeouts
- Configurable timeouts give users control for their specific network conditions and model choices

**Key files to modify**:
- `src/flavia/agent/base.py` -- accept timeout parameters from settings
- `src/flavia/config/settings.py` -- add timeout configuration fields
- `src/flavia/config/loader.py` -- load timeout values from config.yaml
- `src/flavia/interfaces/cli_interface.py` -- add timeout slash commands and flags
- `src/flavia/cli.py` -- add `--api-timeout` and `--connect-timeout` flags
- `doc/usage.md` -- document timeout configuration

---

**[← Back to Roadmap](../roadmap.md)**
