"""Agent profile dataclass for flavIA."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class AgentProfile:
    """Profile defining an agent's configuration."""

    context: str
    model: str | int = "hf:moonshotai/Kimi-K2.5"
    base_dir: Path = field(default_factory=Path.cwd)
    tools: list[str] = field(default_factory=list)
    subagents: dict[str, Any] = field(default_factory=dict)
    name: str = "agent"
    max_depth: int = 3

    @classmethod
    def from_config(cls, config: dict[str, Any], parent: Optional["AgentProfile"] = None) -> "AgentProfile":
        """Create profile from configuration dict."""
        if parent:
            base_dir = parent.base_dir
            model = parent.model
            max_depth = parent.max_depth
        else:
            base_dir = Path.cwd()
            model = "hf:moonshotai/Kimi-K2.5"
            max_depth = 3

        if "path" in config:
            path = Path(config["path"])
            if path.is_absolute():
                base_dir = path
            else:
                base_dir = base_dir / path

        if "model" in config:
            model = config["model"]

        if "max_depth" in config:
            max_depth = config["max_depth"]

        return cls(
            context=config.get("context", ""),
            model=model,
            base_dir=base_dir,
            tools=config.get("tools", []),
            subagents=config.get("subagents", {}),
            name=config.get("name", "agent"),
            max_depth=max_depth,
        )

    def create_subagent_profile(self, subagent_name: str) -> Optional["AgentProfile"]:
        """Create a profile for a named subagent."""
        if subagent_name not in self.subagents:
            return None

        config = self.subagents[subagent_name].copy()
        config["name"] = subagent_name

        return AgentProfile.from_config(config, parent=self)

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary."""
        return {
            "context": self.context,
            "model": self.model,
            "path": str(self.base_dir),
            "tools": self.tools,
            "subagents": self.subagents,
            "name": self.name,
            "max_depth": self.max_depth,
        }
