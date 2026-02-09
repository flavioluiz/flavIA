"""Context and prompt builders for flavIA."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .profile import AgentPermissions, AgentProfile


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
            permissions=profile.permissions,
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
            permissions=profile.permissions,
        )


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

    # Permissions info
    permissions = context.permissions
    if permissions.read_paths or permissions.write_paths:
        perm_lines = ["\nAccess permissions:"]
        if permissions.read_paths:
            read_paths_str = ", ".join(str(p) for p in permissions.read_paths)
            perm_lines.append(f"  Read: {read_paths_str}")
        if permissions.write_paths:
            write_paths_str = ", ".join(str(p) for p in permissions.write_paths)
            perm_lines.append(f"  Write: {write_paths_str}")
        parts.append("\n".join(perm_lines))

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
