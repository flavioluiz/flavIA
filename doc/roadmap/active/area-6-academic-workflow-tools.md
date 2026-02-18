# Area 6: Academic Workflow Tools

**Status**: In Progress (Task 6.1 complete, Task 6.2 pending)

flavIA is designed for research and academic work. Beyond reading and analyzing files, researchers need to compile LaTeX documents (papers, reports, presentations) and run computational scripts (data analysis, simulations, plotting). These tools bridge the gap between the agent's text generation capabilities and actual academic output.

---

### Task 6.1 -- LaTeX Compilation Tool ✓

**Difficulty**: Medium | **Dependencies**: Task 5.1 (agent needs write tools to generate `.tex` files first) | **Status**: Done

Create a `tools/academic/compile_latex.py` tool that compiles LaTeX documents into PDFs.

Functionality:
- Run `pdflatex` (or `latexmk` if available) on a `.tex` file as a subprocess
- Handle multiple compilation passes automatically (for cross-references, table of contents)
- Optionally run `bibtex` or `biber` between passes (for bibliography)
- Return compilation status, output PDF path, and any errors/warnings from the log
- Parse `.log` file to extract meaningful error messages rather than dumping raw output
- Enforce write permissions (output directory must be in write-allowed paths)

Requires `pdflatex`/`latexmk` installed on the system (not a Python dependency). The tool should detect availability at registration time and report clearly if missing.

Configuration in `agents.yaml`:
```yaml
main:
  tools:
    - compile_latex
  latex:
    compiler: "pdflatex"     # or "latexmk", "xelatex", "lualatex"
    passes: 2                # number of compilation passes
    bibtex: true             # run bibtex/biber automatically
    clean_aux: true          # remove auxiliary files after compilation
```

**Key files to modify/create**:
- `tools/academic/compile_latex.py` (new)
- `tools/academic/__init__.py` (new, with `register_tool()` calls)
- `tools/__init__.py` (add `academic` submodule import)

---

### Task 6.2 -- Sandboxed Script Execution (Python/MATLAB)

**Difficulty**: Hard | **Dependencies**: Task 5.1

Create a `tools/academic/run_script.py` tool for executing Python and MATLAB/Octave scripts with a combination safety approach: user confirmation before execution, plus subprocess-level restrictions during execution.

**Safety model -- two layers**:

1. **User confirmation gate**: Before any script runs, the tool presents the full script content to the user and requires explicit approval. The confirmation mechanism is platform-aware:
   - CLI: interactive prompt showing the script and asking `Execute this script? [y/N]`
   - Telegram/WhatsApp: send the script as a message, wait for user reply "yes"/"no"
   - Web API: return script in response, require a separate confirmation API call

2. **Subprocess restrictions** (even after user approval):
   - Timeout limits (configurable, default 60 seconds)
   - Working directory restricted to write-allowed paths
   - For Python: restricted imports (block `os`, `subprocess`, `sys`, `shutil`, `socket`, `http`, `ctypes`, etc.) enforced by pre-scanning the script's AST with Python's `ast` module before execution
   - For MATLAB/Octave: run via `matlab -batch` or `octave --eval` with the same timeout
   - stdout/stderr captured and returned to the agent as the tool result
   - Resource limits where the platform supports them (`ulimit` on Linux/macOS)

Tools to implement:
- `run_python` -- execute a Python script (`.py` file path or inline code string)
- `run_matlab` -- execute a MATLAB/Octave script (`.m` file path or inline code string)

Configuration in `agents.yaml`:
```yaml
main:
  tools:
    - run_python
    - run_matlab
  script_execution:
    timeout: 60
    require_confirmation: true
    blocked_imports:
      - os
      - subprocess
      - sys
      - shutil
      - socket
      - http
      - ctypes
      - importlib
```

**Key files to modify/create**:
- `tools/academic/run_script.py` (new)
- `tools/academic/__init__.py` (update)
- Agent confirmation callback mechanism (new -- needs to work across CLI, Telegram, Web API)

---

**[← Back to Roadmap](../../roadmap.md)**
