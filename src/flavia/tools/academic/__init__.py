"""Academic workflow tools for flavIA.

Provides tools for academic document compilation and processing.
Tools are auto-registered on import via register_tool() calls in
each tool module.
"""

from .compile_latex import CompileLatexTool

__all__ = ["CompileLatexTool"]
