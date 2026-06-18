"""
Knowledge Base Registry.

Loads knowledge base definitions from ``knowledge_bases.yaml`` and provides
a typed registry consumed by :func:`~ang2react.tools.knowledge.search.build_kb_search_tool`.

Usage::

    from ang2react.tools.knowledge.registry import DEFAULT_REGISTRY

    for kb in DEFAULT_REGISTRY.all():
        print(kb.tool_name, kb.collection)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_REGISTRY_PATH = Path(__file__).parent / "knowledge_bases.yaml"


@dataclass(frozen=True)
class KnowledgeBaseInfo:
    """Metadata for a single Qdrant knowledge base."""

    id: str
    """Unique snake_case identifier."""

    name: str
    """Human-readable display name."""

    collection: str
    """Exact Qdrant collection name."""

    description: str
    """What this KB contains. Used as the FunctionTool docstring — be precise."""

    tool_name: str
    """Python function name exposed to the LLM (convention: ``search_<id>``)."""

    enabled: bool = True
    """Whether this KB is active. Disabled KBs are excluded from agent tools."""

    vector_name: str | None = None
    """Named vector to query. Required when the Qdrant collection uses named vectors.
    Leave ``None`` for collections with a single unnamed (default) vector."""


class KnowledgeBaseRegistry:
    """Registry of available Qdrant knowledge bases, loaded from YAML.

    Example::

        registry = KnowledgeBaseRegistry(path)
        tools = [build_kb_search_tool(kb) for kb in registry.all()]
    """

    def __init__(self, path: Path | str) -> None:
        with Path(path).open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        self._kbs: dict[str, KnowledgeBaseInfo] = {
            entry["id"]: KnowledgeBaseInfo(
                id=entry["id"],
                name=entry["name"],
                collection=entry["collection"],
                description=entry["description"],
                tool_name=entry["tool_name"],
                enabled=entry.get("enabled", True),
                vector_name=entry.get("vector_name", None),
            )
            for entry in data["knowledge_bases"]
        }

    def all(self) -> list[KnowledgeBaseInfo]:
        """Return all *enabled* knowledge bases in definition order."""
        return [kb for kb in self._kbs.values() if kb.enabled]

    def get(self, id: str) -> KnowledgeBaseInfo:
        """Return a knowledge base by ID.

        Raises:
            KeyError: If the ID is not found in the registry.
        """
        try:
            return self._kbs[id]
        except KeyError:
            available = ", ".join(sorted(self._kbs))
            raise KeyError(
                f"Unknown knowledge base ID '{id}'. Available: {available}"
            ) from None


# Loaded once at import time — the default registry used by build_rag_agent.
DEFAULT_REGISTRY: KnowledgeBaseRegistry = KnowledgeBaseRegistry(_REGISTRY_PATH)
