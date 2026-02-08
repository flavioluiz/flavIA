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
        interactive_review=False,
    )

    assert success is True
    assert calls[0][0] == "convert_pdfs"
    assert calls[0][1]["pdf_files"] == ["paper.pdf"]
    assert calls[1][0] == "run"
    assert "converted/" in calls[1][1]["task"]


def test_run_ai_setup_allows_user_revision_and_regenerates(monkeypatch, tmp_path):
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    run_tasks: list[str] = []

    class FakeAgent:
        def __init__(self):
            self.calls = 0

        def run(self, task):
            self.calls += 1
            run_tasks.append(task)
            if self.calls == 1:
                (config_dir / "agents.yaml").write_text(
                    "main:\n  context: first draft\n  tools:\n    - read_file\n",
                    encoding="utf-8",
                )
            else:
                (config_dir / "agents.yaml").write_text(
                    "main:\n  context: revised draft\n  tools:\n    - read_file\n    - search_files\n",
                    encoding="utf-8",
                )
            return "proposal ready"

    confirm_answers = iter([False, False, True])  # reject, don't use default, then accept
    prompt_answers = iter(["Inclua um subagente de resumos e citações"])

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )
    monkeypatch.setattr("flavia.setup_wizard.Confirm.ask", lambda *args, **kwargs: next(confirm_answers))
    monkeypatch.setattr("flavia.setup_wizard.Prompt.ask", lambda *args, **kwargs: next(prompt_answers))

    success = _run_ai_setup(
        target_dir=target_dir,
        config_dir=config_dir,
        convert_pdfs=False,
        user_guidance="Foco em análise para alunos de graduação.",
        interactive_review=True,
    )

    assert success is True
    assert len(run_tasks) == 2
    assert "User guidance" in run_tasks[0]
    assert "Revision feedback from user" in run_tasks[1]
    assert "Inclua um subagente de resumos e citações" in run_tasks[1]
