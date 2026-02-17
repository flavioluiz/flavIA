"""Context and prompt builders for flavIA."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .profile import AgentPermissions, AgentProfile

from typing import TYPE_CHECKING as _TYPE_CHECKING

if _TYPE_CHECKING:
    from flavia.tools.write_confirmation import WriteConfirmation


@dataclass
class AgentContext:
    """Runtime context for an agent."""

    agent_id: str = "main"
    name: str = "agent"
    current_depth: int = 0
    max_depth: int = 3
    parent_id: Optional[str] = None
    base_dir: Path = field(default_factory=Path.cwd)
    available_tools: list[str] = field(default_factory=list)
    subagents: dict[str, Any] = field(default_factory=dict)
    model_id: str = "hf:moonshotai/Kimi-K2.5"
    messages: list[dict[str, Any]] = field(default_factory=list)
    permissions: AgentPermissions = field(default_factory=lambda: AgentPermissions())
    write_confirmation: Optional["WriteConfirmation"] = None
    dry_run: bool = False
    max_context_tokens: int = 128_000
    current_context_tokens: int = 0

    @classmethod
    def from_profile(
        cls,
        profile: AgentProfile,
        agent_id: str = "main",
        depth: int = 0,
        parent_id: Optional[str] = None,
        resolved_model: str = None,
    ) -> "AgentContext":
        """Create context from an agent profile."""
        return cls(
            agent_id=agent_id,
            name=profile.name,
            current_depth=depth,
            max_depth=profile.max_depth,
            parent_id=parent_id,
            base_dir=profile.base_dir,
            available_tools=profile.tools.copy(),
            subagents=profile.subagents.copy(),
            model_id=resolved_model or str(profile.model),
            permissions=profile.permissions.copy(),
        )

    def can_spawn(self) -> bool:
        """Check if this context allows spawning sub-agents."""
        return self.current_depth < self.max_depth

    def create_child_context(
        self,
        child_id: str,
        profile: AgentProfile,
        resolved_model: str = None,
    ) -> "AgentContext":
        """Create a child context for a sub-agent."""
        return AgentContext(
            agent_id=child_id,
            name=profile.name,
            current_depth=self.current_depth + 1,
            max_depth=self.max_depth,
            parent_id=self.agent_id,
            base_dir=profile.base_dir,
            available_tools=profile.tools.copy(),
            subagents=profile.subagents.copy(),
            model_id=resolved_model or str(profile.model),
            permissions=profile.permissions.copy(),
            write_confirmation=self.write_confirmation,
            dry_run=self.dry_run,
        )


def _load_catalog_context(base_dir: Path, max_length: int = 2000) -> str:
    """Load content catalog summary if available."""
    try:
        from flavia.content.catalog import ContentCatalog

        config_dir = base_dir / ".flavia"
        catalog = ContentCatalog.load(config_dir)
        if catalog is not None:
            return catalog.generate_context_summary(max_length=max_length)
    except Exception:
        pass
    return ""


def _build_catalog_first_guidance(context: AgentContext) -> str:
    """Build workflow guidance that prioritizes catalog usage before file reads."""
    tools = set(context.available_tools or [])
    has_query = "query_catalog" in tools
    has_search_chunks = "search_chunks" in tools
    has_summary = "get_catalog_summary" in tools
    has_read = "read_file" in tools
    has_spawn = "spawn_predefined_agent" in tools or "spawn_agent" in tools

    if not (has_query or has_summary):
        return ""

    lines = ["\nWorkflow policy for content discovery:"]

    if has_summary:
        lines.append(
            "- For broad tasks, start with `get_catalog_summary` to map the project before "
            "opening files."
        )

    if has_query and has_search_chunks:
        lines.append(
            "Use `search_chunks` when answering questions about document content (what, how, why). "
            "Use `query_catalog` to discover which files exist or filter by type/name."
        )

    if has_query:
        lines.append(
            "- Use `query_catalog` to shortlist relevant files by `file_type`, `name`, and "
            "`text_search`."
        )
        lines.append(
            "- For video tasks, query with `file_type='video'` and prioritize entries with "
            "`converted_to` (transcript) and `frame_descriptions`."
        )

    if has_read:
        lines.append(
            "- Only use `read_file` after shortlisting; avoid scanning many `.md` files blindly."
        )

    if has_spawn:
        lines.append(
            "- For large multi-file tasks, delegate focused searches to subagents instead of one "
            "agent reading everything."
        )

    lines.append(
        "- Use `search_files`/`list_files` as fallback when the catalog is missing or clearly "
        "insufficient."
    )

    if has_query and has_read:
        lines.append("\nVideo workflow playbook:")
        lines.append(
            "1. Run `query_catalog(file_type='video', text_search=...)` to find candidate videos."
        )
        lines.append(
            "2. For each candidate, check catalog metadata first: `summary`, `converted_to`, and "
            "`frame_descriptions`."
        )
        lines.append(
            "3. Read the audio transcript from `converted_to` for narrative/order of content."
        )
        lines.append(
            "4. Read frame description markdown files from `frame_descriptions` for visual details "
            "(figures, equations, board content)."
        )
        lines.append(
            "5. Only expand to additional files/videos when the shortlist evidence is insufficient."
        )
    return "\n".join(lines)


def build_system_prompt(
    profile: AgentProfile,
    context: AgentContext,
    tools_description: str = "",
) -> str:
    """Build the system prompt for an agent."""
    parts = []

    # Base context from profile (with base_dir substitution)
    if profile.context:
        ctx = profile.context.strip()
        ctx = ctx.replace("{base_dir}", str(context.base_dir))
        parts.append(ctx)

    # Agent identity
    identity = f"\n[Agent ID: {context.agent_id}]"
    if context.parent_id:
        identity += f" [Parent: {context.parent_id}]"
    identity += f" [Depth: {context.current_depth}/{context.max_depth}]"
    parts.append(identity)

    # Working directory
    parts.append(f"\nWorking directory: {context.base_dir}")

    # Content catalog context (inject project overview for main agents)
    if context.current_depth == 0:
        catalog_context = _load_catalog_context(context.base_dir)
        if catalog_context:
            parts.append(f"\n{catalog_context}")
    catalog_guidance = _build_catalog_first_guidance(context)
    if catalog_guidance:
        parts.append(catalog_guidance)

    # Permissions info
    permissions = context.permissions
    if permissions.explicit or permissions.read_paths or permissions.write_paths:
        perm_lines = ["\nAccess permissions:"]
        if permissions.read_paths:
            read_paths_str = ", ".join(str(p) for p in permissions.read_paths)
            perm_lines.append(f"  Read: {read_paths_str}")
        else:
            perm_lines.append("  Read: (none)")
        if permissions.write_paths:
            write_paths_str = ", ".join(str(p) for p in permissions.write_paths)
            perm_lines.append(f"  Write: {write_paths_str}")
        else:
            perm_lines.append("  Write: (none)")
        parts.append("\n".join(perm_lines))

    # File-write reliability guard to reduce hallucinated "I wrote the file" responses.
    parts.append(
        "\nExecution policy for filesystem changes:\n"
        "- Use write tools for any filesystem modification request.\n"
        "- Never claim a file/directory was changed unless a write tool returned a success result.\n"
        "- If a write tool returns an error or cancellation, clearly report the failure."
    )
    parts.append(
        "\nTool-call policy:\n"
        "- Every tool call must include `execution_note` with a detailed pre-execution message.\n"
        "- `execution_note` should clearly explain the immediate next action and intent."
    )

    # Tools info
    if tools_description:
        parts.append(f"\nAvailable tools:\n{tools_description}")

    # Sub-agents info
    if context.subagents and context.can_spawn():
        subagent_list = ", ".join(context.subagents.keys())
        parts.append(f"\nAvailable specialist agents: {subagent_list}")

    if not context.can_spawn():
        parts.append("\n[Maximum depth reached - cannot spawn sub-agents]")

    return "\n".join(parts)


def build_tools_description(tools: list[Any]) -> str:
    """Build a text description of available tools."""
    if not tools:
        return ""

    lines = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        lines.append(f"- {name}: {desc}")

    return "\n".join(lines)
