# Area 2: Agent System Improvements

Agents are currently defined in `agents.yaml` with a free-form `context` field (the system prompt), a tools list, subagents dict, and permissions. The `build_system_prompt()` function in `context.py` composes the full prompt. The setup wizard has an AI-assisted mode that generates agents via a setup agent.

---

### Task 2.1 -- Structured Agent Profiles

**Difficulty**: Medium | **Dependencies**: None

Redesign `agents.yaml` to support structured context fields instead of a single free-form `context` string. New schema:

```yaml
main:
  name: "Research Assistant"
  role: "academic research assistant specializing in ML and NLP"
  expertise:
    - "machine learning"
    - "transformer architectures"
    - "attention mechanisms"
  personality: "precise, thorough, academically rigorous"
  instructions: |
    When analyzing papers, always cite specific sections.
    Compare methodologies across papers when relevant.
  context: |
    Legacy free-form context (still supported for backward compat)
  tools: [...]
  subagents: {...}
```

The `build_system_prompt()` function in `context.py` would compose a richer, more effective prompt from these structured fields when available, falling back to raw `context` for full backward compatibility. The `AgentProfile` dataclass in `profile.py` would gain optional fields (`role`, `expertise`, `personality`, `instructions`) that map to the new YAML keys.

**Key files to modify**:
- `agent/profile.py` -- add new fields to `AgentProfile`
- `agent/context.py` -- update `build_system_prompt()` to use structured fields
- `config/settings.py` -- no change needed (already loads raw YAML dict)

---

### Task 2.2 -- CLI Agent Management Commands

**Difficulty**: Medium | **Dependencies**: Task 2.1 (benefits from structured profiles), Task 4.2 (agent switching)

Add new slash commands for agent CRUD operations (agent switching itself is covered by Task 4.2):

| Command | Description |
|---------|-------------|
| `/agent-edit <name>` | Interactively edit agent context, tools, and permissions |
| `/agent-create` | Create a new agent interactively via prompts |
| `/agent-list` | Show all agents with full details (expanded `/agent`) |
| `/agent-delete <name>` | Remove an agent from configuration |

All changes persist to `.flavia/agents.yaml`. After modification, the settings and agent profile are reloaded.

**Key files to modify**:
- `interfaces/cli_interface.py` -- add slash command handlers
- `config/settings.py` -- use `reset_settings()` + `load_settings()` after YAML changes

---

### Task 2.3 -- Meta-Agent for Agent Generation

**Difficulty**: Hard | **Dependencies**: Task 2.1, Task 2.2

Create a specialized "agent architect" agent that can be invoked from the CLI at any time (not just during `--init`) to analyze the project content and generate or improve agent configurations. This extends the existing setup wizard's AI-assisted mode (see `SETUP_AGENT_CONTEXT` in `setup_wizard.py`).

The meta-agent would:
- Analyze the content catalog and current agent configurations
- Suggest improvements to agent contexts, tool assignments, and subagent structures
- Generate structured profiles (per Task 2.1 schema)
- Support iterative refinement with user feedback (similar to the setup wizard's revision rounds)

Invokable via `/agent-improve` or `/agent-generate` slash commands.

**Key files to modify/create**:
- New tool in `tools/setup/` or a dedicated meta-agent profile
- `interfaces/cli_interface.py` -- add slash commands
- Reference pattern: `setup_wizard.py` `SETUP_AGENT_CONTEXT` and `create_agents_config` tool

---

**[← Back to Roadmap](../roadmap.md)**
