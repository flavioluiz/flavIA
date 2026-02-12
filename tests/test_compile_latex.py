"""Tests for the LaTeX compilation tool."""

import shutil
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions
from flavia.tools.academic.compile_latex import (
    AUX_EXTENSIONS,
    SUPPORTED_COMPILERS,
    CompilationResult,
    CompileLatexTool,
    LatexConfig,
    LatexError,
    _clean_aux_files,
    _has_bibliography,
    _needs_biber,
    compile_latex,
    detect_any_compiler,
    detect_bibtex_engine,
    detect_compiler,
    parse_latex_log,
)


def _make_context(
    base_dir: Path,
    permissions: AgentPermissions | None = None,
    dry_run: bool = False,
    agent_id: str = "test",
) -> AgentContext:
    """Create a test AgentContext."""
    return AgentContext(
        agent_id=agent_id,
        name="test",
        current_depth=0,
        max_depth=3,
        parent_id=None,
        base_dir=base_dir,
        available_tools=["compile_latex"],
        subagents={},
        model_id="test-model",
        messages=[],
        permissions=permissions or AgentPermissions(),
        write_confirmation=None,
        dry_run=dry_run,
    )


# ──────────────────────────────────────────────
#  LatexConfig
# ──────────────────────────────────────────────


class TestLatexConfig:
    def test_defaults(self):
        config = LatexConfig()
        assert config.compiler == "pdflatex"
        assert config.passes == 2
        assert config.bibtex is True
        assert config.clean_aux is True
        assert config.shell_escape is False
        assert config.continue_on_error is True

    def test_from_dict(self):
        config = LatexConfig.from_dict(
            {
                "compiler": "xelatex",
                "passes": 3,
                "bibtex": False,
                "clean_aux": False,
            }
        )
        assert config.compiler == "xelatex"
        assert config.passes == 3
        assert config.bibtex is False
        assert config.clean_aux is False

    def test_from_dict_partial(self):
        config = LatexConfig.from_dict({"compiler": "lualatex"})
        assert config.compiler == "lualatex"
        assert config.passes == 2  # default
        assert config.bibtex is True  # default
        assert config.shell_escape is False
        assert config.continue_on_error is True

    def test_from_dict_empty(self):
        config = LatexConfig.from_dict({})
        assert config.compiler == "pdflatex"
        assert config.shell_escape is False
        assert config.continue_on_error is True

    def test_from_dict_string_values(self):
        config = LatexConfig.from_dict(
            {
                "passes": "3",
                "bibtex": "false",
                "clean_aux": "yes",
                "shell_escape": "1",
                "continue_on_error": "off",
            }
        )
        assert config.passes == 3
        assert config.bibtex is False
        assert config.clean_aux is True
        assert config.shell_escape is True
        assert config.continue_on_error is False

    def test_from_dict_invalid_passes_raises(self):
        with pytest.raises(ValueError, match="passes must be an integer"):
            LatexConfig.from_dict({"passes": "abc"})

    def test_from_dict_invalid_bool_raises(self):
        with pytest.raises(ValueError, match="bibtex must be a boolean"):
            LatexConfig.from_dict({"bibtex": "maybe"})

    def test_validate_valid(self):
        for compiler in SUPPORTED_COMPILERS:
            config = LatexConfig(compiler=compiler)
            valid, msg = config.validate()
            assert valid, f"Expected {compiler} to be valid"
            assert msg == ""

    def test_validate_invalid_compiler(self):
        config = LatexConfig(compiler="pdftex")
        valid, msg = config.validate()
        assert not valid
        assert "Unsupported compiler" in msg
        assert "pdftex" in msg

    def test_validate_passes_too_low(self):
        config = LatexConfig(passes=0)
        valid, msg = config.validate()
        assert not valid
        assert "at least 1" in msg

    def test_validate_passes_too_high(self):
        config = LatexConfig(passes=10)
        valid, msg = config.validate()
        assert not valid
        assert "cannot exceed 5" in msg


# ──────────────────────────────────────────────
#  LatexError & CompilationResult
# ──────────────────────────────────────────────


class TestLatexError:
    def test_str_simple(self):
        err = LatexError(message="Undefined control sequence", error_type="error")
        assert str(err) == "[error] Undefined control sequence"

    def test_str_with_file(self):
        err = LatexError(
            message="Missing $ inserted",
            file="./main.tex",
            error_type="error",
        )
        assert str(err) == "[error] ./main.tex: Missing $ inserted"

    def test_str_with_file_and_line(self):
        err = LatexError(
            message="Missing $ inserted",
            file="./main.tex",
            line=42,
            error_type="error",
        )
        assert str(err) == "[error] ./main.tex:42: Missing $ inserted"

    def test_str_warning(self):
        err = LatexError(message="Overfull hbox", error_type="warning")
        assert str(err) == "[warning] Overfull hbox"


class TestCompilationResult:
    def test_success_message(self):
        result = CompilationResult(
            success=True,
            pdf_path=Path("output.pdf"),
            compiler_used="pdflatex",
            passes_run=2,
            bibtex_run=True,
        )
        msg = result.to_message()
        assert "successful" in msg.lower()
        assert "pdflatex" in msg
        assert "2" in msg
        assert "Bibliography" in msg
        assert "output.pdf" in msg

    def test_failure_message(self):
        result = CompilationResult(
            success=False,
            compiler_used="xelatex",
            passes_run=1,
            errors=[
                LatexError(
                    message="Undefined control sequence",
                    file="main.tex",
                    line=10,
                    error_type="error",
                )
            ],
        )
        msg = result.to_message()
        assert "FAILED" in msg
        assert "Undefined control sequence" in msg

    def test_warnings_in_message(self):
        result = CompilationResult(
            success=True,
            pdf_path=Path("test.pdf"),
            compiler_used="pdflatex",
            passes_run=2,
            warnings=[
                LatexError(message="Overfull hbox", error_type="bad_box"),
            ],
        )
        msg = result.to_message()
        assert "Warnings (1)" in msg
        assert "Overfull hbox" in msg

    def test_error_truncation(self):
        """Many errors should be truncated to 20."""
        errors = [LatexError(message=f"Error {i}", error_type="error") for i in range(30)]
        result = CompilationResult(
            success=False,
            compiler_used="pdflatex",
            passes_run=1,
            errors=errors,
        )
        msg = result.to_message()
        assert "10 more errors" in msg


# ──────────────────────────────────────────────
#  Detection functions
# ──────────────────────────────────────────────


class TestDetection:
    @patch("shutil.which")
    def test_detect_compiler_found(self, mock_which):
        mock_which.return_value = "/usr/bin/pdflatex"
        assert detect_compiler("pdflatex") == "pdflatex"

    @patch("shutil.which")
    def test_detect_compiler_not_found(self, mock_which):
        mock_which.return_value = None
        assert detect_compiler("pdflatex") is None

    @patch("shutil.which")
    def test_detect_compiler_unsupported(self, mock_which):
        mock_which.return_value = "/usr/bin/something"
        assert detect_compiler("pdftex") is None

    @patch("shutil.which")
    def test_detect_any_compiler_first_available(self, mock_which):
        def side_effect(name):
            return "/usr/bin/latexmk" if name == "latexmk" else None

        mock_which.side_effect = side_effect
        # pdflatex is checked first but not found, then xelatex, lualatex, latexmk
        assert detect_any_compiler() == "latexmk"

    @patch("shutil.which")
    def test_detect_any_compiler_none(self, mock_which):
        mock_which.return_value = None
        assert detect_any_compiler() is None

    @patch("shutil.which")
    def test_detect_bibtex_engine_biber(self, mock_which):
        mock_which.side_effect = lambda name: "/usr/bin/biber" if name == "biber" else None
        assert detect_bibtex_engine() == "biber"

    @patch("shutil.which")
    def test_detect_bibtex_engine_bibtex(self, mock_which):
        def side_effect(name):
            if name == "biber":
                return None
            if name == "bibtex":
                return "/usr/bin/bibtex"
            return None

        mock_which.side_effect = side_effect
        assert detect_bibtex_engine() == "bibtex"

    @patch("shutil.which")
    def test_detect_bibtex_engine_none(self, mock_which):
        mock_which.return_value = None
        assert detect_bibtex_engine() is None


# ──────────────────────────────────────────────
#  Bibliography detection
# ──────────────────────────────────────────────


class TestBibliographyDetection:
    def test_has_bibliography_with_bibliography_cmd(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\bibliography{refs}")
        assert _has_bibliography(tex) is True

    def test_has_bibliography_with_addbibresource(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\addbibresource{refs.bib}")
        assert _has_bibliography(tex) is True

    def test_has_bibliography_with_printbibliography(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\printbibliography")
        assert _has_bibliography(tex) is True

    def test_has_bibliography_without(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
        assert _has_bibliography(tex) is False

    def test_has_bibliography_nonexistent(self, tmp_path):
        tex = tmp_path / "missing.tex"
        assert _has_bibliography(tex) is False

    def test_needs_biber_with_biblatex(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\usepackage{biblatex}")
        assert _needs_biber(tex) is True

    def test_needs_biber_with_biblatex_options(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\usepackage[backend=biber]{biblatex}")
        assert _needs_biber(tex) is True

    def test_needs_biber_without_biblatex(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\usepackage{natbib}")
        assert _needs_biber(tex) is False


# ──────────────────────────────────────────────
#  Log parsing
# ──────────────────────────────────────────────


class TestParseLatexLog:
    def test_parse_errors(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            textwrap.dedent("""\
            (./main.tex
            ! Undefined control sequence.
            l.15 \\badcommand
            """)
        )
        errors, warnings = parse_latex_log(log)
        assert len(errors) == 1
        assert errors[0].message == "Undefined control sequence."
        assert errors[0].line == 15
        assert errors[0].file == "./main.tex"

    def test_parse_warnings(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            textwrap.dedent("""\
            LaTeX Warning: Reference `fig:test' on page 1 undefined on input line 20.
            """)
        )
        errors, warnings = parse_latex_log(log)
        assert len(errors) == 0
        assert len(warnings) >= 1

    def test_parse_undefined_reference(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            textwrap.dedent("""\
            LaTeX Warning: Reference `fig:missing' on page 3 undefined on input line 42.
            """)
        )
        errors, warnings = parse_latex_log(log)
        assert any("fig:missing" in w.message for w in warnings)

    def test_parse_undefined_citation(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            textwrap.dedent("""\
            LaTeX Warning: Citation `smith2020' on page 1 undefined on input line 10.
            """)
        )
        errors, warnings = parse_latex_log(log)
        assert any("smith2020" in w.message for w in warnings)

    def test_parse_overfull_hbox(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            textwrap.dedent("""\
            Overfull \\hbox (10.0pt too wide) in paragraph at lines 5--10
            """)
        )
        errors, warnings = parse_latex_log(log)
        assert len(warnings) == 1
        assert warnings[0].error_type == "bad_box"

    def test_parse_underfull_hbox(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            textwrap.dedent("""\
            Underfull \\hbox (badness 10000) in paragraph at lines 5--10
            """)
        )
        errors, warnings = parse_latex_log(log)
        assert len(warnings) == 1
        assert warnings[0].error_type == "bad_box"

    def test_parse_package_warning(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            textwrap.dedent("""\
            Package hyperref Warning: Token not allowed in a PDF string.
            """)
        )
        errors, warnings = parse_latex_log(log)
        assert len(warnings) == 1
        assert "Token not allowed" in warnings[0].message

    def test_parse_nonexistent_log(self, tmp_path):
        log = tmp_path / "nonexistent.log"
        errors, warnings = parse_latex_log(log)
        assert errors == []
        assert warnings == []

    def test_parse_empty_log(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("")
        errors, warnings = parse_latex_log(log)
        assert errors == []
        assert warnings == []

    def test_parse_multiple_errors(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            textwrap.dedent("""\
            ! Missing $ inserted.
            l.10 x^2
            ! Undefined control sequence.
            l.20 \\badcmd
            """)
        )
        errors, warnings = parse_latex_log(log)
        assert len(errors) == 2
        assert errors[0].message == "Missing $ inserted."
        assert errors[0].line == 10
        assert errors[1].message == "Undefined control sequence."
        assert errors[1].line == 20


# ──────────────────────────────────────────────
#  Auxiliary file cleanup
# ──────────────────────────────────────────────


class TestCleanAuxFiles:
    def test_clean_existing_aux_files(self, tmp_path):
        stem = "test"
        for ext in (".aux", ".log", ".out", ".toc"):
            (tmp_path / f"{stem}{ext}").write_text("content")
        # Also create the PDF which should NOT be removed
        (tmp_path / f"{stem}.pdf").write_text("pdf content")

        _clean_aux_files(tmp_path, stem)

        for ext in (".aux", ".log", ".out", ".toc"):
            assert not (tmp_path / f"{stem}{ext}").exists()
        # PDF should still exist
        assert (tmp_path / f"{stem}.pdf").exists()

    def test_clean_nonexistent_files(self, tmp_path):
        # Should not raise
        _clean_aux_files(tmp_path, "nonexistent")


# ──────────────────────────────────────────────
#  compile_latex function (with mocked subprocess)
# ──────────────────────────────────────────────


class TestCompileLatex:
    def _create_tex_file(self, tmp_path: Path, name: str = "test.tex") -> Path:
        tex = tmp_path / name
        tex.write_text(
            textwrap.dedent(r"""\
            \documentclass{article}
            \begin{document}
            Hello, world!
            \end{document}
        """)
        )
        return tex

    def _create_tex_with_bib(self, tmp_path: Path) -> Path:
        tex = tmp_path / "test.tex"
        tex.write_text(
            textwrap.dedent(r"""\
            \documentclass{article}
            \begin{document}
            Hello \cite{smith2020}.
            \bibliography{refs}
            \end{document}
        """)
        )
        return tex

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_successful_compilation(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)
        pdf_path = tmp_path / "test.pdf"

        def side_effect(cmd, cwd, timeout=120):
            assert "-no-shell-escape" in cmd
            # Create the PDF on the first call
            pdf_path.write_text("PDF content")
            # Create a log file
            (tmp_path / "test.log").write_text("This is pdfTeX\nOutput written on test.pdf")
            return 0, "", ""

        mock_run.side_effect = side_effect
        config = LatexConfig(compiler="pdflatex", passes=2, bibtex=False, clean_aux=False)
        result = compile_latex(tex, config)

        assert result.success is True
        assert result.pdf_path == pdf_path
        assert result.passes_run == 2
        assert result.compiler_used == "pdflatex"

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_compilation_failure(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)

        def side_effect(cmd, cwd, timeout=120):
            assert "-halt-on-error" in cmd
            (tmp_path / "test.log").write_text("! Undefined control sequence.\nl.5 \\badcmd\n")
            return 1, "", "Fatal error"

        mock_run.side_effect = side_effect
        config = LatexConfig(
            compiler="pdflatex",
            passes=2,
            bibtex=False,
            clean_aux=False,
            continue_on_error=False,
        )
        result = compile_latex(tex, config)

        assert result.success is False
        assert result.passes_run == 1
        assert len(result.errors) >= 1

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_continue_on_error_runs_all_passes(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)

        def side_effect(cmd, cwd, timeout=120):
            assert "-halt-on-error" not in cmd
            (tmp_path / "test.log").write_text("! Undefined control sequence.\nl.5 \\badcmd\n")
            return 1, "", "Fatal error"

        mock_run.side_effect = side_effect
        config = LatexConfig(
            compiler="pdflatex",
            passes=2,
            bibtex=False,
            clean_aux=False,
            continue_on_error=True,
        )
        result = compile_latex(tex, config)

        assert result.success is False
        assert result.passes_run == 2
        assert mock_run.call_count == 2

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_continue_on_error_keeps_generated_pdf(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)
        pdf_path = tmp_path / "test.pdf"
        call_count = 0

        def side_effect(cmd, cwd, timeout=120):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                pdf_path.write_text("partial pdf")
            (tmp_path / "test.log").write_text("! Undefined control sequence.\nl.5 \\badcmd\n")
            return 1, "", "Fatal error"

        mock_run.side_effect = side_effect
        config = LatexConfig(
            compiler="pdflatex",
            passes=2,
            bibtex=False,
            clean_aux=False,
            continue_on_error=True,
        )
        result = compile_latex(tex, config)

        assert result.success is False
        assert result.pdf_path == pdf_path

    @patch("flavia.tools.academic.compile_latex.shutil.which")
    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_bibtex_processing(self, mock_run, mock_which, tmp_path):
        tex = self._create_tex_with_bib(tmp_path)
        pdf_path = tmp_path / "test.pdf"
        aux_path = tmp_path / "test.aux"

        call_count = 0

        def run_side_effect(cmd, cwd, timeout=120):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First pdflatex pass - create aux
                aux_path.write_text(r"\citation{smith2020}")
                (tmp_path / "test.log").write_text("")
                return 0, "", ""
            elif cmd[0] == "bibtex":
                # bibtex run
                return 0, "Database file: refs.bib", ""
            else:
                # Second pdflatex pass - create PDF
                pdf_path.write_text("PDF content")
                (tmp_path / "test.log").write_text("")
                return 0, "", ""

        mock_run.side_effect = run_side_effect
        mock_which.return_value = "/usr/bin/bibtex"

        config = LatexConfig(compiler="pdflatex", passes=2, bibtex=True, clean_aux=False)
        result = compile_latex(tex, config)

        assert result.success is True
        assert result.bibtex_run is True

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_latexmk_compilation(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)
        pdf_path = tmp_path / "test.pdf"

        def side_effect(cmd, cwd, timeout=120):
            assert cmd[0] == "latexmk"
            assert "-pdf" in cmd
            assert "-no-shell-escape" in cmd
            pdf_path.write_text("PDF content")
            (tmp_path / "test.log").write_text("")
            return 0, "", ""

        mock_run.side_effect = side_effect
        config = LatexConfig(compiler="latexmk", passes=1, bibtex=False, clean_aux=False)
        result = compile_latex(tex, config)

        assert result.success is True
        assert result.compiler_used == "latexmk"

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_latexmk_halt_on_error_flag(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)

        def side_effect(cmd, cwd, timeout=120):
            assert "-halt-on-error" in cmd
            assert "-f" not in cmd
            (tmp_path / "test.log").write_text("! Undefined control sequence.\nl.5 \\badcmd\n")
            return 1, "", "Fatal error"

        mock_run.side_effect = side_effect
        config = LatexConfig(
            compiler="latexmk",
            passes=1,
            bibtex=False,
            clean_aux=False,
            continue_on_error=False,
        )
        result = compile_latex(tex, config)

        assert result.success is False

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_clean_aux_after_success(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)
        pdf_path = tmp_path / "test.pdf"

        def side_effect(cmd, cwd, timeout=120):
            pdf_path.write_text("PDF content")
            (tmp_path / "test.log").write_text("")
            (tmp_path / "test.aux").write_text("aux")
            (tmp_path / "test.out").write_text("out")
            (tmp_path / "test.toc").write_text("toc")
            return 0, "", ""

        mock_run.side_effect = side_effect
        config = LatexConfig(compiler="pdflatex", passes=1, bibtex=False, clean_aux=True)
        result = compile_latex(tex, config)

        assert result.success is True
        # Aux files should be cleaned
        assert not (tmp_path / "test.aux").exists()
        assert not (tmp_path / "test.out").exists()
        assert not (tmp_path / "test.toc").exists()
        # Log is also cleaned as it's in AUX_EXTENSIONS
        # PDF should remain
        assert pdf_path.exists()

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_no_clean_aux_on_failure(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)

        def side_effect(cmd, cwd, timeout=120):
            (tmp_path / "test.log").write_text("! error\n")
            (tmp_path / "test.aux").write_text("aux")
            return 1, "", ""

        mock_run.side_effect = side_effect
        config = LatexConfig(compiler="pdflatex", passes=1, bibtex=False, clean_aux=True)
        result = compile_latex(tex, config)

        assert result.success is False
        # Aux files should NOT be cleaned on failure
        assert (tmp_path / "test.aux").exists()

    @patch("flavia.tools.academic.compile_latex._run_command")
    def test_shell_escape_enabled(self, mock_run, tmp_path):
        tex = self._create_tex_file(tmp_path)
        pdf_path = tmp_path / "test.pdf"

        def side_effect(cmd, cwd, timeout=120):
            assert "-shell-escape" in cmd
            assert "-no-shell-escape" not in cmd
            pdf_path.write_text("PDF content")
            (tmp_path / "test.log").write_text("")
            return 0, "", ""

        mock_run.side_effect = side_effect
        config = LatexConfig(
            compiler="pdflatex",
            passes=1,
            bibtex=False,
            clean_aux=False,
            shell_escape=True,
        )
        result = compile_latex(tex, config)

        assert result.success is True


# ──────────────────────────────────────────────
#  CompileLatexTool.execute (integration with AgentContext)
# ──────────────────────────────────────────────


class TestCompileLatexTool:
    @patch("flavia.tools.academic.compile_latex.detect_any_compiler")
    def test_no_compiler_available(self, mock_detect, tmp_path):
        mock_detect.return_value = None
        tool = CompileLatexTool()
        tool._available_compiler = None

        ctx = _make_context(tmp_path)
        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        result = tool.execute({"path": "test.tex"}, ctx)
        assert "No LaTeX compiler found" in result

    def test_missing_path(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"  # pretend available
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": ""}, ctx)
        assert "Error" in result

    def test_non_tex_extension(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"
        ctx = _make_context(tmp_path)
        (tmp_path / "test.txt").write_text("content")
        result = tool.execute({"path": "test.txt"}, ctx)
        assert ".tex" in result

    def test_file_not_found(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "missing.tex"}, ctx)
        assert "not found" in result

    def test_write_permission_denied(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"

        # Create tex file in a directory we allow reading but not writing
        read_dir = tmp_path / "readonly"
        read_dir.mkdir()
        tex = read_dir / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        write_dir = tmp_path / "output"
        write_dir.mkdir()

        permissions = AgentPermissions(
            read_paths=[read_dir],
            write_paths=[write_dir],
            explicit=True,
        )
        ctx = _make_context(tmp_path, permissions=permissions)

        result = tool.execute({"path": str(tex)}, ctx)
        assert "denied" in result.lower() or "access" in result.lower()

    def test_dry_run(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"
        ctx = _make_context(tmp_path, dry_run=True)

        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        result = tool.execute({"path": "test.tex"}, ctx)
        assert "[DRY-RUN]" in result
        assert "pdflatex" in result

    def test_dry_run_custom_compiler(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "xelatex"
        ctx = _make_context(tmp_path, dry_run=True)

        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        with patch("flavia.tools.academic.compile_latex.detect_compiler", return_value="xelatex"):
            result = tool.execute({"path": "test.tex", "compiler": "xelatex"}, ctx)
        assert "[DRY-RUN]" in result
        assert "xelatex" in result
        assert "Continue on error:" in result

    def test_invalid_compiler_in_args(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"
        ctx = _make_context(tmp_path)

        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        result = tool.execute({"path": "test.tex", "compiler": "badcompiler"}, ctx)
        assert "Unsupported compiler" in result

    def test_invalid_passes_in_args(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"
        ctx = _make_context(tmp_path)

        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        result = tool.execute({"path": "test.tex", "passes": "abc"}, ctx)
        assert "Invalid LaTeX configuration" in result

    def test_invalid_bool_in_args(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"
        ctx = _make_context(tmp_path)

        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        result = tool.execute({"path": "test.tex", "bibtex": "sometimes"}, ctx)
        assert "Invalid LaTeX configuration" in result

    def test_invalid_continue_on_error_in_args(self, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"
        ctx = _make_context(tmp_path)

        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        result = tool.execute({"path": "test.tex", "continue_on_error": "sometimes"}, ctx)
        assert "Invalid LaTeX configuration" in result

    @patch("flavia.tools.academic.compile_latex.compile_latex")
    @patch("flavia.tools.academic.compile_latex.detect_compiler")
    def test_successful_execution(self, mock_detect, mock_compile, tmp_path):
        tool = CompileLatexTool()
        tool._available_compiler = "pdflatex"

        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        mock_detect.return_value = "pdflatex"
        mock_compile.return_value = CompilationResult(
            success=True,
            pdf_path=tmp_path / "test.pdf",
            compiler_used="pdflatex",
            passes_run=2,
        )

        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "test.tex"}, ctx)

        assert "successful" in result.lower()
        mock_compile.assert_called_once()

    @patch("flavia.tools.academic.compile_latex.detect_compiler")
    @patch("flavia.tools.academic.compile_latex.detect_any_compiler")
    def test_compiler_fallback(self, mock_any, mock_detect, tmp_path):
        """If the preferred compiler isn't found, fall back to any available one."""
        tool = CompileLatexTool()
        tool._available_compiler = "xelatex"

        tex = tmp_path / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")

        mock_detect.return_value = None  # preferred not found
        mock_any.return_value = "xelatex"  # fallback

        ctx = _make_context(tmp_path, dry_run=True)
        result = tool.execute({"path": "test.tex", "compiler": "pdflatex"}, ctx)

        assert "[DRY-RUN]" in result
        assert "xelatex" in result

    def test_schema(self):
        tool = CompileLatexTool()
        schema = tool.get_schema()
        assert schema.name == "compile_latex"
        param_names = [p.name for p in schema.parameters]
        assert "path" in param_names
        assert "compiler" in param_names
        assert "passes" in param_names
        assert "bibtex" in param_names
        assert "clean_aux" in param_names
        assert "shell_escape" in param_names
        assert "continue_on_error" in param_names

    def test_schema_openai_format(self):
        tool = CompileLatexTool()
        schema = tool.get_schema()
        openai_schema = schema.to_openai_schema()
        assert openai_schema["type"] == "function"
        assert openai_schema["function"]["name"] == "compile_latex"
        params = openai_schema["function"]["parameters"]
        assert "path" in params["properties"]
        assert "path" in params["required"]
        # Optional params should NOT be in required
        assert "compiler" not in params["required"]
        assert "passes" not in params["required"]
        assert "shell_escape" not in params["required"]
        assert "continue_on_error" not in params["required"]

    def test_is_available_always_true(self, tmp_path):
        tool = CompileLatexTool()
        ctx = _make_context(tmp_path)
        assert tool.is_available(ctx) is True


# ──────────────────────────────────────────────
#  Tool registration
# ──────────────────────────────────────────────


class TestToolRegistration:
    def test_compile_latex_registered(self):
        from flavia.tools.registry import registry

        tool = registry.get("compile_latex")
        assert tool is not None
        assert isinstance(tool, CompileLatexTool)
        assert tool.name == "compile_latex"
        assert tool.category == "academic"

    def test_compile_latex_in_list(self):
        from flavia.tools.registry import registry

        names = registry.list_tools()
        assert "compile_latex" in names


# ──────────────────────────────────────────────
#  Config from agents.yaml
# ──────────────────────────────────────────────


class TestLatexConfigFromAgents:
    @patch("flavia.config.settings.load_agents_config")
    def test_loads_config_from_yaml(self, mock_load, tmp_path):
        from flavia.tools.academic.compile_latex import _get_latex_config_from_agents

        agents_dir = tmp_path / ".flavia"
        agents_dir.mkdir()
        agents_yaml = agents_dir / "agents.yaml"
        agents_yaml.write_text("")

        mock_load.return_value = {
            "test": {
                "latex": {
                    "compiler": "xelatex",
                    "passes": 3,
                }
            }
        }

        ctx = _make_context(tmp_path, agent_id="test")
        config = _get_latex_config_from_agents(ctx)
        assert config == {"compiler": "xelatex", "passes": 3}

    def test_returns_empty_when_no_config(self, tmp_path):
        from flavia.tools.academic.compile_latex import _get_latex_config_from_agents

        ctx = _make_context(tmp_path, agent_id="test")
        config = _get_latex_config_from_agents(ctx)
        assert config == {}
