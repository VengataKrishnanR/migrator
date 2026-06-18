"""Knowledge base FunctionTools — one tool per registered Qdrant collection.

Usage::

    from ang2react.tools.knowledge import DEFAULT_REGISTRY, build_kb_search_tool

    # Wire all enabled KBs into an agent:
    tools = [build_kb_search_tool(kb) for kb in DEFAULT_REGISTRY.all()]

    # Wire a specific KB:
    tools = [build_kb_search_tool(DEFAULT_REGISTRY.get("coding_standards"))]
"""

from .registry import DEFAULT_REGISTRY, KnowledgeBaseInfo, KnowledgeBaseRegistry
from .search import build_kb_search_tool

__all__ = [
    "DEFAULT_REGISTRY",
    "KnowledgeBaseInfo",
    "KnowledgeBaseRegistry",
    "build_kb_search_tool",
]
