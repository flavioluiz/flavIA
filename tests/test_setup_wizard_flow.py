"""Tests for setup wizard AI flow."""

from pathlib import Path

from flavia.setup_wizard import create_setup_agent, _run_ai_setup


def test_create_setup_agent_exposes_setup_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNTHETIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    agent, error = create_setup_agent(
        base_dir=tmp_path,
        include_pdf_tool=True,
        pdf_files=["paper.pdf"],
    )

    assert error is None
    tool_names = {schema["function"]["name"] for schema in agent.tool_schemas}
    assert "create_agents_config" in tool_names
    assert "convert_pdfs" in tool_names


def test_run_ai_setup_forces_pdf_conversion_before_analysis(monkeypatch, tmp_path):
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    calls: list[tuple[str, dict]] = []

    class FakeAgent:
        def _execute_tool(self, name, args):
            calls.append((name, args))
            converted_dir = target_dir / "converted"
            converted_dir.mkdir(exist_ok=True)
            (converted_dir / "paper.md").write_text("# paper", encoding="utf-8")
            return "Successfully converted 1 file(s)"

        def run(self, task):
            calls.append(("run", {"task": task}))
            (config_dir / "agents.yaml").write_text(
                "main:\n  context: test\n  tools:\n    - read_file\n",
                encoding="utf-8",
            )
            return "done"

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )

    success = _run_ai_setup(
        target_dir=target_dir,
        config_dir=config_dir,
        convert_pdfs=True,
        pdf_files=["paper.pdf"],
    )

    assert success is True
    assert calls[0][0] == "convert_pdfs"
    assert calls[0][1]["pdf_files"] == ["paper.pdf"]
    assert calls[1][0] == "run"
    assert "converted/" in calls[1][1]["task"]
