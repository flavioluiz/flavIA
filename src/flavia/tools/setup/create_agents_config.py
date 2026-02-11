"""Tool for creating agents.yaml configuration."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ..base import BaseTool, ToolSchema, ToolParameter
from ..permissions import check_write_permission
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class CreateAgentsConfigTool(BaseTool):
    """Tool for creating agents.yaml configuration file."""

    name = "create_agents_config"
    description = "Create the agents.yaml configuration file with the suggested agent setup"
    category = "setup"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="main_context",
                    type="string",
                    description="System prompt/context for the main agent. Describe what this agent does and how it should behave.",
                    required=True,
                ),
                ToolParameter(
                    name="main_tools",
                    type="array",
                    description=(
                        "List of tools for the main agent. Available: "
                        "read_file, list_files, search_files, get_file_info, "
                        "query_catalog, get_catalog_summary, refresh_catalog, "
                        "write_file, edit_file, insert_text, append_file, delete_file, "
                        "create_directory, remove_directory, "
                        "spawn_agent, spawn_predefined_agent"
                    ),
                    required=True,
                    items={"type": "string"},
                ),
                ToolParameter(
                    name="permissions",
                    type="object",
                    description="Access permissions for the main agent. Object with 'read' array (paths with read access) and 'write' array (paths with write access, also grants read). Paths can be relative to base_dir or absolute.",
                    required=False,
                ),
                ToolParameter(
                    name="subagents",
                    type="array",
                    description="List of subagent configurations. Each subagent has: name, context, tools (array), optional model, and optional permissions",
                    required=False,
                    items={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Subagent name (lowercase, no spaces)"},
                            "context": {"type": "string", "description": "Subagent system prompt"},
                            "tools": {"type": "array", "items": {"type": "string"}, "description": "Subagent tools"},
                            "model": {"type": "string", "description": "Optional model reference (provider:model_id or model_id)"},
                            "permissions": {"type": "object", "description": "Optional permissions (inherits from parent if not specified)"},
                        },
                    },
                ),
                ToolParameter(
                    name="project_description",
                    type="string",
                    description="Brief description of the project (for documentation in the yaml)",
                    required=False,
                ),
            ]
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        main_context = args.get("main_context", "")
        main_tools = args.get("main_tools", [])
        permissions = args.get("permissions", None)
        subagents = args.get("subagents", [])
        project_description = args.get("project_description", "")

        if not main_context:
            return "Error: main_context is required"
        if not main_tools:
            return "Error: main_tools is required"

        # Build the config structure
        config = {
            "main": {
                "context": main_context,
                "tools": main_tools,
            }
        }

        # Add permissions if provided
        if permissions:
            config["main"]["permissions"] = permissions

        # Add subagents if provided
        if subagents:
            config["main"]["subagents"] = {}
            for sub in subagents:
                name = sub.get("name", "").lower().replace(" ", "_")
                if not name:
                    continue
                config["main"]["subagents"][name] = {
                    "context": sub.get("context", ""),
                    "tools": sub.get("tools", ["read_file"]),
                }
                if sub.get("model"):
                    config["main"]["subagents"][name]["model"] = sub["model"]
                if sub.get("permissions"):
                    config["main"]["subagents"][name]["permissions"] = sub["permissions"]

        # Determine output path
        config_dir = agent_context.base_dir / ".flavia"
        config_file = config_dir / "agents.yaml"

        can_write, write_error = check_write_permission(config_file, agent_context)
        if not can_write:
            return f"Error: {write_error}"

        # Build YAML content with comments
        yaml_content = self._build_yaml_with_comments(config, project_description)

        try:
            # Ensure directory exists
            config_dir.mkdir(parents=True, exist_ok=True)

            # Write the file
            config_file.write_text(yaml_content, encoding="utf-8")

            return f"Successfully created agents.yaml at {config_file}\n\nConfiguration:\n{yaml_content}"

        except Exception as e:
            return f"Error creating agents.yaml: {e}"

    def _build_yaml_with_comments(self, config: dict, project_description: str) -> str:
        """Build YAML content with helpful comments."""
        lines = []

        # Header comment
        lines.append("# flavIA Agent Configuration")
        if project_description:
            lines.append(f"# Project: {project_description}")
        lines.append("#")
        lines.append("# This file defines the agents available for this project.")
        lines.append("# The 'main' agent is used by default when running 'flavia'.")
        lines.append("")

        # Main agent
        lines.append("main:")

        # Context (multiline)
        main_ctx = config["main"]["context"]
        lines.append("  context: |")
        for ctx_line in main_ctx.strip().split("\n"):
            lines.append(f"    {ctx_line}")
        lines.append("")

        # Permissions
        if "permissions" in config["main"]:
            lines.append("  # Access permissions (write implies read)")
            lines.append("  permissions:")
            perm = config["main"]["permissions"]
            if perm.get("read"):
                lines.append("    read:")
                for p in perm["read"]:
                    lines.append(f"      - \"{p}\"")
            if perm.get("write"):
                lines.append("    write:")
                for p in perm["write"]:
                    lines.append(f"      - \"{p}\"")
            lines.append("")

        # Tools
        lines.append("  # Available tools for this agent")
        lines.append("  tools:")
        for tool in config["main"]["tools"]:
            lines.append(f"    - {tool}")
        lines.append("")

        # Subagents
        if "subagents" in config["main"]:
            lines.append("  # Specialist sub-agents (use with spawn_predefined_agent)")
            lines.append("  subagents:")

            for name, sub_config in config["main"]["subagents"].items():
                lines.append(f"    {name}:")
                if sub_config.get("model"):
                    lines.append(f"      model: \"{sub_config['model']}\"")
                lines.append("      context: |")
                for ctx_line in sub_config["context"].strip().split("\n"):
                    lines.append(f"        {ctx_line}")
                # Subagent permissions
                if sub_config.get("permissions"):
                    lines.append("      permissions:")
                    perm = sub_config["permissions"]
                    if perm.get("read"):
                        lines.append("        read:")
                        for p in perm["read"]:
                            lines.append(f"          - \"{p}\"")
                    if perm.get("write"):
                        lines.append("        write:")
                        for p in perm["write"]:
                            lines.append(f"          - \"{p}\"")
                lines.append("      tools:")
                for tool in sub_config["tools"]:
                    lines.append(f"        - {tool}")
                lines.append("")

        return "\n".join(lines)

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Only available in setup mode."""
        # Check if we're in setup mode via a flag in the context
        return getattr(agent_context, 'setup_mode', False)


# Don't auto-register - this tool is registered manually during setup
# register_tool(CreateAgentsConfigTool())
