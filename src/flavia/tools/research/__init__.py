"""Research tools for flavIA.

Provides tools for web search and information retrieval.
Tools are auto-registered on import via register_tool() calls in
each tool module.
"""

from .web_search import WebSearchTool

__all__ = ["WebSearchTool"]
