"""LaTeX compilation tool for flavIA.

Compiles .tex files into PDFs using pdflatex, xelatex, lualatex, or latexmk.
Handles multiple compilation passes, bibliography processing, log parsing,
and auxiliary file cleanup.
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_read_permission, check_write_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

logger = logging.getLogger(__name__)

# Supported LaTeX compilers
SUPPORTED_COMPILERS = ("pdflatex", "xelatex", "lualatex", "latexmk")

# Auxiliary file extensions produced by LaTeX compilation
AUX_EXTENSIONS = (
    ".aux",
    ".log",
    ".out",
    ".toc",
    ".lof",
    ".lot",
    ".bbl",
    ".blg",
    ".bcf",
    ".run.xml",
    ".fls",
    ".fdb_latexmk",
    ".synctex.gz",
    ".nav",
    ".snm",
    ".vrb",  # beamer-specific
)


@dataclass
class LatexConfig:
    """Configuration for LaTeX compilation."""

    compiler: str = "pdflatex"
    passes: int = 2
    bibtex: bool = True
    clean_aux: bool = True
    shell_escape: bool = False
    continue_on_error: bool = True

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "LatexConfig":
        """Create config from a dictionary (e.g. from agents.yaml)."""
        return cls(
            compiler=config.get("compiler", "pdflatex"),
            passes=_parse_int(config.get("passes", 2), "passes"),
            bibtex=_parse_bool(config.get("bibtex", True), "bibtex"),
            clean_aux=_parse_bool(config.get("clean_aux", True), "clean_aux"),
            shell_escape=_parse_bool(config.get("shell_escape", False), "shell_escape"),
            continue_on_error=_parse_bool(
                config.get("continue_on_error", True),
                "continue_on_error",
            ),
        )

    def validate(self) -> tuple[bool, str]:
        """Validate configuration values."""
        if self.compiler not in SUPPORTED_COMPILERS:
            return False, (
                f"Unsupported compiler '{self.compiler}'. "
                f"Supported: {', '.join(SUPPORTED_COMPILERS)}"
            )
        if self.passes < 1:
            return False, "Number of passes must be at least 1"
        if self.passes > 5:
            return False, "Number of passes cannot exceed 5"
        return True, ""


@dataclass
class LatexError:
    """A parsed error from the LaTeX log."""

    message: str
    file: str = ""
    line: int = 0
    error_type: str = "error"  # "error", "warning", "bad_box"

    def __str__(self) -> str:
        location = ""
        if self.file:
            location = f"{self.file}"
            if self.line:
                location += f":{self.line}"
            location += ": "
        return f"[{self.error_type}] {location}{self.message}"


@dataclass
class CompilationResult:
    """Result of a LaTeX compilation."""

    success: bool
    pdf_path: Optional[Path] = None
    errors: list[LatexError] = field(default_factory=list)
    warnings: list[LatexError] = field(default_factory=list)
    compiler_used: str = ""
    passes_run: int = 0
    bibtex_run: bool = False

    def to_message(self) -> str:
        """Format result as a user-readable message."""
        parts = []

        if self.success:
            parts.append(f"Compilation successful using {self.compiler_used}")
            parts.append(f"Passes: {self.passes_run}")
            if self.bibtex_run:
                parts.append("Bibliography: processed")
            if self.pdf_path:
                parts.append(f"Output PDF: {self.pdf_path}")
        else:
            parts.append(f"Compilation FAILED using {self.compiler_used}")
            parts.append(f"Passes attempted: {self.passes_run}")
            if self.pdf_path:
                parts.append(f"Output PDF generated with errors: {self.pdf_path}")

        if self.errors:
            parts.append(f"\nErrors ({len(self.errors)}):")
            for err in self.errors[:20]:  # limit to 20 errors
                parts.append(f"  {err}")
            if len(self.errors) > 20:
                parts.append(f"  ... and {len(self.errors) - 20} more errors")

        if self.warnings:
            parts.append(f"\nWarnings ({len(self.warnings)}):")
            for warn in self.warnings[:10]:  # limit to 10 warnings
                parts.append(f"  {warn}")
            if len(self.warnings) > 10:
                parts.append(f"  ... and {len(self.warnings) - 10} more warnings")

        return "\n".join(parts)


def detect_compiler(preferred: str = "pdflatex") -> Optional[str]:
    """Detect if the preferred LaTeX compiler is available on the system.

    Args:
        preferred: The preferred compiler to check for.

    Returns:
        The compiler name if found, None otherwise.
    """
    if preferred in SUPPORTED_COMPILERS and shutil.which(preferred):
        return preferred
    return None


def detect_any_compiler() -> Optional[str]:
    """Detect any available LaTeX compiler on the system.

    Returns:
        The first available compiler name, or None if none found.
    """
    for compiler in SUPPORTED_COMPILERS:
        if shutil.which(compiler):
            return compiler
    return None


def detect_bibtex_engine() -> Optional[str]:
    """Detect available bibliography processor.

    Returns:
        'biber' or 'bibtex' if available, None otherwise.
    """
    # Prefer biber (modern, used with biblatex)
    if shutil.which("biber"):
        return "biber"
    if shutil.which("bibtex"):
        return "bibtex"
    return None


def _parse_bool(value: Any, field_name: str) -> bool:
    """Parse a bool from common YAML/JSON/string representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"{field_name} must be a boolean")
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "on", "1"}:
            return True
        if lowered in {"false", "no", "n", "off", "0"}:
            return False
        raise ValueError(f"{field_name} must be a boolean")
    raise ValueError(f"{field_name} must be a boolean")


def _parse_int(value: Any, field_name: str) -> int:
    """Parse an int from common YAML/JSON/string representations."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must be an integer")
        try:
            return int(stripped)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an integer") from exc
    raise ValueError(f"{field_name} must be an integer")


def _has_bibliography(tex_path: Path) -> bool:
    """Check if a .tex file uses bibliography commands.

    Looks for \\bibliography{}, \\addbibresource{}, or \\printbibliography.
    """
    try:
        content = tex_path.read_text(encoding="utf-8", errors="replace")
        return bool(
            re.search(
                r"\\(?:bibliography\{|addbibresource\{|printbibliography)",
                content,
            )
        )
    except OSError:
        return False


def _needs_biber(tex_path: Path) -> bool:
    """Check if the .tex file uses biblatex (which needs biber)."""
    try:
        content = tex_path.read_text(encoding="utf-8", errors="replace")
        return bool(re.search(r"\\usepackage(?:\[.*?\])?\{biblatex\}", content))
    except OSError:
        return False


def parse_latex_log(log_path: Path) -> tuple[list[LatexError], list[LatexError]]:
    """Parse a LaTeX .log file to extract errors and warnings.

    Args:
        log_path: Path to the .log file.

    Returns:
        Tuple of (errors, warnings).
    """
    errors: list[LatexError] = []
    warnings: list[LatexError] = []

    if not log_path.exists():
        return errors, warnings

    try:
        log_content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return errors, warnings

    # Track current file context from the log's parenthesis-based file tracking
    current_file = ""

    for line in log_content.splitlines():
        # LaTeX errors: "! <message>" pattern
        error_match = re.match(r"^!\s+(.+)$", line)
        if error_match:
            errors.append(
                LatexError(
                    message=error_match.group(1).strip(),
                    file=current_file,
                    error_type="error",
                )
            )
            continue

        # Line-specific errors: "l.<number> <context>"
        line_match = re.match(r"^l\.(\d+)\s+(.*)$", line)
        if line_match and errors:
            # Attach line number to the most recent error
            errors[-1].line = int(line_match.group(1))
            continue

        # LaTeX warnings
        warn_match = re.match(r"^(?:LaTeX|Package|Class)\s+(?:\w+\s+)?Warning:\s*(.+)$", line)
        if warn_match:
            warnings.append(
                LatexError(
                    message=warn_match.group(1).strip(),
                    file=current_file,
                    error_type="warning",
                )
            )
            continue

        # Overfull/Underfull box warnings
        box_match = re.match(r"^((?:Over|Under)full\s+\\[hv]box\s+.+)$", line)
        if box_match:
            warnings.append(
                LatexError(
                    message=box_match.group(1).strip(),
                    file=current_file,
                    error_type="bad_box",
                )
            )
            continue

        # Track file context: "(./filename.tex" pattern
        file_match = re.match(r"^\((.+\.tex)\b", line)
        if file_match:
            current_file = file_match.group(1)

        # Undefined reference warnings
        undef_match = re.search(
            r"Warning:.*Reference\s+[`'](.+?)'?\s+on page\s+\d+\s+undefined",
            line,
        )
        if undef_match:
            warnings.append(
                LatexError(
                    message=f"Undefined reference '{undef_match.group(1)}'",
                    file=current_file,
                    error_type="warning",
                )
            )
            continue

        # Citation undefined warnings
        cite_match = re.search(
            r"Warning:.*Citation\s+[`'](.+?)'?\s+.*undefined",
            line,
        )
        if cite_match:
            warnings.append(
                LatexError(
                    message=f"Undefined citation '{cite_match.group(1)}'",
                    file=current_file,
                    error_type="warning",
                )
            )
            continue

    return errors, warnings


def _run_command(
    cmd: list[str],
    cwd: Path,
    timeout: int = 120,
) -> tuple[int, str, str]:
    """Run a subprocess command with timeout.

    Returns:
        Tuple of (return_code, stdout, stderr).
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            # Prevent interactive prompts from halting the process
            stdin=subprocess.DEVNULL,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except OSError as e:
        return -1, "", f"Error running command: {e}"


def compile_latex(
    tex_path: Path,
    config: LatexConfig,
    timeout: int = 120,
) -> CompilationResult:
    """Compile a LaTeX document to PDF.

    Args:
        tex_path: Path to the .tex file.
        config: LaTeX compilation configuration.
        timeout: Timeout in seconds for each subprocess call.

    Returns:
        CompilationResult with status, PDF path, and parsed errors/warnings.
    """
    result = CompilationResult(
        success=False,
        compiler_used=config.compiler,
    )

    tex_dir = tex_path.parent
    tex_stem = tex_path.stem
    log_path = tex_dir / f"{tex_stem}.log"
    pdf_path = tex_dir / f"{tex_stem}.pdf"
    aux_path = tex_dir / f"{tex_stem}.aux"

    # Determine if we need bibliography processing
    run_bib = config.bibtex and _has_bibliography(tex_path)
    use_biber = _needs_biber(tex_path) if run_bib else False

    if config.compiler == "latexmk":
        # latexmk handles everything automatically
        cmd = [
            "latexmk",
            "-pdf",
            "-shell-escape" if config.shell_escape else "-no-shell-escape",
            "-interaction=nonstopmode",
            "-f" if config.continue_on_error else "-halt-on-error",
            str(tex_path.name),
        ]
        returncode, stdout, stderr = _run_command(cmd, tex_dir, timeout=timeout)
        result.passes_run = 1  # latexmk manages passes internally
        result.bibtex_run = run_bib

        # Parse log for errors/warnings
        errors, warnings = parse_latex_log(log_path)
        result.errors = errors
        result.warnings = warnings

        if pdf_path.exists():
            result.pdf_path = pdf_path

        if returncode == 0 and pdf_path.exists():
            result.success = True
        elif not errors:
            # If no parsed errors but command failed, capture subprocess output
            failure_output = (stderr or stdout).strip()
            if failure_output:
                result.errors.append(
                    LatexError(
                        message=failure_output[:500],
                        error_type="error",
                    )
                )
    else:
        # Manual multi-pass compilation for pdflatex/xelatex/lualatex
        base_cmd = [
            config.compiler,
            "-shell-escape" if config.shell_escape else "-no-shell-escape",
            "-interaction=nonstopmode",
            *([] if config.continue_on_error else ["-halt-on-error"]),
            str(tex_path.name),
        ]
        had_nonzero_exit = False

        for pass_num in range(1, config.passes + 1):
            returncode, stdout, stderr = _run_command(base_cmd, tex_dir, timeout=timeout)
            result.passes_run = pass_num

            if returncode != 0:
                had_nonzero_exit = True
                errors, warnings = parse_latex_log(log_path)
                result.errors.extend(errors)
                result.warnings.extend(warnings)

                failure_output = (stderr or stdout).strip()
                if not errors and failure_output:
                    result.errors.append(
                        LatexError(
                            message=failure_output[:500],
                            error_type="error",
                        )
                    )

                if not config.continue_on_error:
                    if pdf_path.exists():
                        result.pdf_path = pdf_path
                    return result

            # Run bibliography after the first pass (if needed and .aux exists)
            if pass_num == 1 and run_bib and aux_path.exists():
                bib_engine = "biber" if use_biber else "bibtex"
                detected = detect_bibtex_engine()
                if detected:
                    # Use detected engine, preferring what the document needs
                    if use_biber and shutil.which("biber"):
                        bib_cmd = ["biber", tex_stem]
                    elif not use_biber and shutil.which("bibtex"):
                        bib_cmd = ["bibtex", tex_stem]
                    else:
                        bib_cmd = [detected, tex_stem]

                    bib_rc, bib_out, bib_err = _run_command(bib_cmd, tex_dir, timeout=timeout)
                    result.bibtex_run = True

                    if bib_rc != 0:
                        result.warnings.append(
                            LatexError(
                                message=(
                                    f"Bibliography processing ({bib_cmd[0]}) "
                                    f"returned non-zero exit code. "
                                    f"Output: {(bib_err or bib_out)[:300]}"
                                ),
                                error_type="warning",
                            )
                        )

        # Parse log after final pass
        errors, warnings = parse_latex_log(log_path)
        result.errors.extend(errors)
        result.warnings.extend(warnings)

        if pdf_path.exists():
            result.pdf_path = pdf_path
            result.success = not had_nonzero_exit

    # Clean auxiliary files if requested and compilation succeeded
    if config.clean_aux and result.success:
        _clean_aux_files(tex_dir, tex_stem)

    return result


def _clean_aux_files(directory: Path, stem: str) -> None:
    """Remove auxiliary files produced by LaTeX compilation."""
    for ext in AUX_EXTENSIONS:
        aux_file = directory / f"{stem}{ext}"
        try:
            if aux_file.exists():
                aux_file.unlink()
        except OSError:
            pass  # best-effort cleanup


def _get_latex_config_from_agents(agent_context: "AgentContext") -> dict[str, Any]:
    """Try to load latex config from agents.yaml.

    The config lives under the agent's section in agents.yaml:
        main:
          latex:
            compiler: pdflatex
            ...

    We load the agents.yaml file from the .flavia directory under
    the agent's base_dir (or parent directories), using the same
    discovery logic as the config loader.
    """
    try:
        from flavia.config.settings import load_agents_config

        # Try local .flavia/agents.yaml first, then parent directories
        candidates = [
            agent_context.base_dir / ".flavia" / "agents.yaml",
            Path.home() / ".config" / "flavia" / "agents.yaml",
        ]
        for agents_file in candidates:
            if agents_file.exists():
                agents_config = load_agents_config(agents_file)
                agent_id = agent_context.agent_id
                agent_config = agents_config.get(agent_id, {})
                if isinstance(agent_config, dict):
                    return agent_config.get("latex", {})
                break
    except Exception:
        pass
    return {}


class CompileLatexTool(BaseTool):
    """Tool for compiling LaTeX documents into PDFs."""

    name = "compile_latex"
    description = (
        "Compile a LaTeX .tex file into a PDF document. "
        "Handles multiple compilation passes, bibliography processing, "
        "and extracts meaningful error messages from the log."
    )
    category = "academic"

    def __init__(self) -> None:
        super().__init__()
        # Detect compiler availability at registration time
        self._available_compiler = detect_any_compiler()
        if self._available_compiler:
            logger.info("LaTeX compiler detected: %s", self._available_compiler)
        else:
            logger.warning(
                "No LaTeX compiler found on system. "
                "compile_latex tool will report an error when invoked. "
                "Install pdflatex, xelatex, lualatex, or latexmk."
            )

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description=(
                        "Path to the .tex file to compile (relative to base directory or absolute)"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="compiler",
                    type="string",
                    description=(
                        "LaTeX compiler to use. Defaults to value from agents.yaml or 'pdflatex'."
                    ),
                    required=False,
                    enum=list(SUPPORTED_COMPILERS),
                ),
                ToolParameter(
                    name="passes",
                    type="integer",
                    description=(
                        "Number of compilation passes (1-5). "
                        "Defaults to value from agents.yaml or 2."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="bibtex",
                    type="boolean",
                    description=(
                        "Whether to run bibtex/biber for bibliography. "
                        "Defaults to value from agents.yaml or true."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="clean_aux",
                    type="boolean",
                    description=(
                        "Whether to remove auxiliary files after compilation. "
                        "Defaults to value from agents.yaml or true."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="shell_escape",
                    type="boolean",
                    description=(
                        "Allow LaTeX shell-escape. "
                        "Defaults to value from agents.yaml or false."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="continue_on_error",
                    type="boolean",
                    description=(
                        "Continue compilation and collect log errors instead of stopping "
                        "at first LaTeX error. Defaults to value from agents.yaml or true."
                    ),
                    required=False,
                ),
            ],
        )

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Tool is always registered, but reports unavailability clearly."""
        return True

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")

        if not path:
            return "Error: path is required"

        # Check system availability first
        if not self._available_compiler:
            return (
                "Error: No LaTeX compiler found on this system. "
                "Please install one of: pdflatex, xelatex, lualatex, or latexmk. "
                "On macOS: 'brew install --cask mactex' or 'brew install basictex'. "
                "On Ubuntu/Debian: 'sudo apt install texlive-latex-base'. "
                "On Fedora: 'sudo dnf install texlive-scheme-basic'."
            )

        full_path = resolve_path(path, agent_context.base_dir)

        # Validate .tex file
        if not full_path.suffix == ".tex":
            return f"Error: file must have .tex extension, got '{full_path.suffix}'"

        if not full_path.exists():
            return f"Error: file not found: {full_path}"

        if not full_path.is_file():
            return f"Error: path is not a file: {full_path}"

        # Check read permission on the .tex file
        allowed, error_msg = check_read_permission(full_path, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        # Check write permission on the output directory (where PDF will go)
        output_dir = full_path.parent
        allowed, error_msg = check_write_permission(output_dir, agent_context)
        if not allowed:
            return f"Error: {error_msg} (output directory: {output_dir})"

        # Build configuration: agents.yaml defaults < tool parameters
        yaml_config = _get_latex_config_from_agents(agent_context)
        config_dict: dict[str, Any] = {}

        # Start with agents.yaml values
        if yaml_config:
            config_dict.update(yaml_config)

        # Override with explicit tool arguments
        if "compiler" in args:
            config_dict["compiler"] = args["compiler"]
        if "passes" in args:
            config_dict["passes"] = args["passes"]
        if "bibtex" in args:
            config_dict["bibtex"] = args["bibtex"]
        if "clean_aux" in args:
            config_dict["clean_aux"] = args["clean_aux"]
        if "shell_escape" in args:
            config_dict["shell_escape"] = args["shell_escape"]
        if "continue_on_error" in args:
            config_dict["continue_on_error"] = args["continue_on_error"]

        try:
            config = LatexConfig.from_dict(config_dict)
        except ValueError as e:
            return f"Error: Invalid LaTeX configuration: {e}"

        # Validate config
        valid, error_msg = config.validate()
        if not valid:
            return f"Error: {error_msg}"

        # Verify the chosen compiler is actually available
        chosen_compiler = detect_compiler(config.compiler)
        if not chosen_compiler:
            # Fall back to any available compiler
            fallback = detect_any_compiler()
            if fallback:
                logger.info(
                    "Preferred compiler '%s' not found, falling back to '%s'",
                    config.compiler,
                    fallback,
                )
                config.compiler = fallback
            else:
                return (
                    f"Error: Compiler '{config.compiler}' not found on system "
                    f"and no fallback available."
                )

        # Dry-run check
        if agent_context.dry_run:
            return (
                f"[DRY-RUN] Would compile: {full_path}\n"
                f"  Compiler: {config.compiler}\n"
                f"  Passes: {config.passes}\n"
                f"  Bibliography: {'yes' if config.bibtex else 'no'}\n"
                f"  Clean auxiliary files: {'yes' if config.clean_aux else 'no'}\n"
                f"  Shell escape: {'yes' if config.shell_escape else 'no'}\n"
                f"  Continue on error: {'yes' if config.continue_on_error else 'no'}"
            )

        # Compile
        try:
            rel_path = full_path.relative_to(agent_context.base_dir)
        except ValueError:
            rel_path = full_path

        logger.info("Compiling LaTeX: %s with %s", rel_path, config.compiler)

        compilation = compile_latex(full_path, config)

        # Convert PDF path to relative for display
        if compilation.pdf_path:
            try:
                compilation.pdf_path = compilation.pdf_path.relative_to(agent_context.base_dir)
            except ValueError:
                pass  # keep absolute if outside base_dir

        return compilation.to_message()


register_tool(CompileLatexTool())
