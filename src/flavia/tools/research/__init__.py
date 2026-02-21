"""Research tools for flavIA.

Provides tools for web search, academic search, and information retrieval.
Tools are auto-registered on import via register_tool() calls in
each tool module.
"""

from .academic_search import (
    FindSimilarPapersTool,
    GetCitationsTool,
    GetPaperDetailsTool,
    GetReferencesTool,
    SearchPapersTool,
)
from .doi_resolver import ResolveDOITool
from .web_search import WebSearchTool

__all__ = [
    "WebSearchTool",
    "SearchPapersTool",
    "GetPaperDetailsTool",
    "GetCitationsTool",
    "GetReferencesTool",
    "FindSimilarPapersTool",
    "ResolveDOITool",
]
