"""Content management tools for flavIA."""

from .query_catalog import QueryCatalogTool
from .get_summary import GetSummaryTool
from .refresh_catalog import RefreshCatalogTool

from ..registry import register_tool

# Auto-register content tools
register_tool(QueryCatalogTool())
register_tool(GetSummaryTool())
register_tool(RefreshCatalogTool())

__all__ = ["QueryCatalogTool", "GetSummaryTool", "RefreshCatalogTool"]
