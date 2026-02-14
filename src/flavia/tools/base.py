"""Base classes for tools in flavIA."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: Optional[list[str]] = None
    items: Optional[dict[str, Any]] = None  # For array types
    default: Any = None


@dataclass
class ToolSchema:
    """OpenAI-compatible tool schema."""
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    execution_note_param_name: str = "execution_note"
    execution_note_description: str = (
        "Detailed message describing what you are about to do. "
        "This text is shown in the UI before the tool executes."
    )

    def parameters_with_common_fields(self) -> list[ToolParameter]:
        """Return tool parameters including globally supported optional fields."""
        if any(p.name == self.execution_note_param_name for p in self.parameters):
            return list(self.parameters)

        params = list(self.parameters)
        params.append(
            ToolParameter(
                name=self.execution_note_param_name,
                type="string",
                description=self.execution_note_description,
                required=True,
            )
        )
        return params

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI tool format."""
        properties = {}
        required = []

        for param in self.parameters_with_common_fields():
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.items:
                prop["items"] = param.items

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        }


class BaseTool(ABC):
    """Abstract base class for all tools."""

    name: str = ""
    description: str = ""
    category: str = "general"  # 'read', 'write', 'spawn', etc.

    @abstractmethod
    def get_schema(self, **context) -> ToolSchema:
        """Get the tool schema, optionally customized based on context."""
        pass

    @abstractmethod
    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        """Execute the tool with given arguments."""
        pass

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Check if tool is available in current context."""
        return True

    def validate_args(self, args: dict[str, Any]) -> tuple[bool, str]:
        """Validate tool arguments."""
        schema = self.get_schema()
        for param in schema.parameters_with_common_fields():
            if param.required and param.name not in args:
                return False, f"Missing required parameter: {param.name}"
        return True, ""
