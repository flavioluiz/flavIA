"""Content management tools for flavIA."""

from .analyze_image import AnalyzeImageTool
from .query_catalog import QueryCatalogTool
from .get_summary import GetSummaryTool
from .refresh_catalog import RefreshCatalogTool
from .search_chunks import SearchChunksTool
from .add_online_source import AddOnlineSourceTool
from .fetch_online_source import FetchOnlineSourceTool
from .convert_pdf import ConvertPdfTool
from .convert_office import ConvertOfficeTool
from .transcribe_media import TranscribeMediaTool

from ..registry import register_tool

# Auto-register content tools
register_tool(AnalyzeImageTool())
register_tool(QueryCatalogTool())
register_tool(GetSummaryTool())
register_tool(RefreshCatalogTool())
register_tool(SearchChunksTool())
register_tool(AddOnlineSourceTool())
register_tool(FetchOnlineSourceTool())
register_tool(ConvertPdfTool())
register_tool(ConvertOfficeTool())
register_tool(TranscribeMediaTool())

__all__ = [
    "AnalyzeImageTool",
    "QueryCatalogTool",
    "GetSummaryTool",
    "RefreshCatalogTool",
    "SearchChunksTool",
    "AddOnlineSourceTool",
    "FetchOnlineSourceTool",
    "ConvertPdfTool",
    "ConvertOfficeTool",
    "TranscribeMediaTool",
]
