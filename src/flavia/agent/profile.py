"""Agent profile dataclass for flavIA."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

CONVERTED_ACCESS_MODES = {"strict", "hybrid", "open"}


@dataclass
class AgentPermissions:
    """Permissions defining read and write access for an agent."""

    read_paths: list[Path] = field(default_factory=list)
    write_paths: list[Path] = field(default_factory=list)
    # True when permissions were explicitly configured (even if empty).
    # This lets the permission checker distinguish:
    # - implicit defaults/backward-compat fallback
    # - explicit "deny all" configs
    explicit: bool = False

    def copy(self) -> "AgentPermissions":
        """Create a shallow copy of permissions paths."""
        return AgentPermissions(
            read_paths=self.read_paths.copy(),
            write_paths=self.write_paths.copy(),
            explicit=self.explicit,
        )

    @classmethod
    def from_config(cls, config: dict, base_dir: Path) -> "AgentPermissions":
        """Parse permissions from YAML config, resolving relative paths."""
        read_paths = []
        write_paths = []

        for path_str in config.get("read", []):
            read_paths.append(cls._resolve_path(path_str, base_dir))

        for path_str in config.get("write", []):
            write_paths.append(cls._resolve_path(path_str, base_dir))

        return cls(read_paths=read_paths, write_paths=write_paths, explicit=True)

    @staticmethod
    def _resolve_path(path_str: str, base_dir: Path) -> Path:
        """Resolve a path string (relative or absolute) to an absolute Path."""
        path = Path(path_str)
        if path.is_absolute():
            return path.resolve()
        return (base_dir / path).resolve()

    def can_read(self, path: Path) -> bool:
        """Check if the path can be read (in read_paths or write_paths)."""
        resolved = path.resolve()
        # Can read if in read_paths OR write_paths (write implies read)
        for allowed in self.read_paths + self.write_paths:
            try:
                resolved.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False

    def can_write(self, path: Path) -> bool:
        """Check if the path can be written to."""
        resolved = path.resolve()
        for allowed in self.write_paths:
            try:
                resolved.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False

    @classmethod
    def default_for_base_dir(cls, base_dir: Path) -> "AgentPermissions":
        """Create default permissions: read and write access to base_dir."""
        resolved = base_dir.resolve()
        return cls(read_paths=[resolved], write_paths=[resolved])

    def to_dict(self, base_dir: Path) -> dict[str, list[str]]:
        """Convert permissions to dictionary for serialization."""
        result = {}
        if self.read_paths:
            result["read"] = [self._path_to_str(p, base_dir) for p in self.read_paths]
        if self.write_paths:
            result["write"] = [self._path_to_str(p, base_dir) for p in self.write_paths]
        return result

    @staticmethod
    def _path_to_str(path: Path, base_dir: Path) -> str:
        """Convert path to string, using relative path if within base_dir."""
        try:
            rel = path.relative_to(base_dir.resolve())
            return f"./{rel}" if str(rel) != "." else "."
        except ValueError:
            return str(path)


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
    compact_threshold: float = 0.9
    compact_threshold_source: str = "default"
    converted_access_mode: str = "hybrid"
    allow_converted_read: bool | None = None
    permissions: AgentPermissions = field(default_factory=lambda: AgentPermissions())

    def __post_init__(self) -> None:
        """Validate compact threshold constraints."""
        self.compact_threshold = self._validate_compact_threshold(self.compact_threshold)
        self.converted_access_mode = self._validate_converted_access_mode(
            self.converted_access_mode
        )
        # Backward compatibility for direct constructor calls still using
        # allow_converted_read.
        if self.allow_converted_read is not None and self.converted_access_mode == "hybrid":
            self.converted_access_mode = "open" if self.allow_converted_read else "strict"
        self.allow_converted_read = self.converted_access_mode == "open"

    @classmethod
    def from_config(
        cls, config: dict[str, Any], parent: Optional["AgentProfile"] = None
    ) -> "AgentProfile":
        """Create profile from configuration dict."""
        if parent:
            base_dir = parent.base_dir
            model = parent.model
            max_depth = parent.max_depth
            compact_threshold = parent.compact_threshold
            compact_threshold_source = parent.compact_threshold_source
            converted_access_mode = parent.converted_access_mode
        else:
            base_dir = Path.cwd()
            model = "hf:moonshotai/Kimi-K2.5"
            max_depth = 3
            compact_threshold = 0.9
            compact_threshold_source = "default"
            converted_access_mode = "hybrid"

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

        if "compact_threshold" in config:
            compact_threshold = cls._validate_compact_threshold(config["compact_threshold"])
            compact_threshold_source = "config"
        if "converted_access_mode" in config:
            converted_access_mode = cls._validate_converted_access_mode(
                config["converted_access_mode"]
            )
        if "allow_converted_read" in config:
            value = config["allow_converted_read"]
            if not isinstance(value, bool):
                raise ValueError("allow_converted_read must be true or false")
            legacy_mode = "open" if value else "strict"
            if "converted_access_mode" in config and converted_access_mode != legacy_mode:
                raise ValueError(
                    "allow_converted_read conflicts with converted_access_mode. "
                    "Use only converted_access_mode or keep both consistent."
                )
            converted_access_mode = legacy_mode

        # Parse permissions with inheritance
        if "permissions" in config:
            permissions = AgentPermissions.from_config(config["permissions"], base_dir)
        elif parent:
            # Inherit from parent if not specified
            permissions = parent.permissions.copy()
        else:
            # Default: full access to base_dir
            permissions = AgentPermissions.default_for_base_dir(base_dir)

        return cls(
            context=config.get("context", ""),
            model=model,
            base_dir=base_dir,
            tools=config.get("tools", []),
            subagents=config.get("subagents", {}),
            name=config.get("name", "agent"),
            max_depth=max_depth,
            compact_threshold=compact_threshold,
            compact_threshold_source=compact_threshold_source,
            converted_access_mode=converted_access_mode,
            permissions=permissions,
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
        result = {
            "context": self.context,
            "model": self.model,
            "path": str(self.base_dir),
            "tools": self.tools,
            "subagents": self.subagents,
            "name": self.name,
            "max_depth": self.max_depth,
            "compact_threshold": self.compact_threshold,
        }
        if self.converted_access_mode != "hybrid":
            result["converted_access_mode"] = self.converted_access_mode
        # Legacy compatibility for existing configs/tools that still read this key.
        if self.allow_converted_read:
            result["allow_converted_read"] = True
        perm_dict = self.permissions.to_dict(self.base_dir)
        if perm_dict:
            result["permissions"] = perm_dict
        return result

    @staticmethod
    def _validate_compact_threshold(value: Any) -> float:
        """Validate and normalize compact threshold to [0.0, 1.0]."""
        try:
            threshold = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("compact_threshold must be a number between 0.0 and 1.0") from exc

        if not (0.0 <= threshold <= 1.0):
            raise ValueError(
                f"compact_threshold must be between 0.0 and 1.0 (got {threshold})"
            )
        return threshold

    @staticmethod
    def _validate_converted_access_mode(value: Any) -> str:
        """Validate converted access mode."""
        if not isinstance(value, str):
            raise ValueError("converted_access_mode must be one of: strict, hybrid, open")

        mode = value.strip().lower()
        if mode not in CONVERTED_ACCESS_MODES:
            raise ValueError(
                f"converted_access_mode must be one of: strict, hybrid, open (got {value!r})"
            )
        return mode
