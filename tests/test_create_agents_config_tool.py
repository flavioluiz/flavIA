"""Tests for create_agents_config setup tool."""

import yaml

from flavia.tools.setup.create_agents_config import CreateAgentsConfigTool


class _FakeContext:
    def __init__(self, base_dir):
        self.base_dir = base_dir


def test_create_agents_config_writes_optional_subagent_model(tmp_path):
    tool = CreateAgentsConfigTool()
    ctx = _FakeContext(tmp_path)

    result = tool.execute(
        {
            "main_context": "Main context",
            "main_tools": ["read_file"],
            "subagents": [
                {
                    "name": "summarizer",
                    "model": "openai:gpt-4o-mini",
                    "context": "Summarizer context",
                    "tools": ["read_file"],
                }
            ],
        },
        ctx,
    )

    assert "Successfully created agents.yaml" in result

    data = yaml.safe_load((tmp_path / ".flavia" / "agents.yaml").read_text(encoding="utf-8"))
    assert data["main"]["subagents"]["summarizer"]["model"] == "openai:gpt-4o-mini"
