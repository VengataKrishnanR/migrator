"""
Knowledge base search FunctionTool factory.

Each knowledge base in the registry gets its own named FunctionTool so the LLM
can route to the correct Qdrant collection explicitly by tool name.

Usage::

    from ang2react.tools.knowledge import DEFAULT_REGISTRY, build_kb_search_tool

    tools = [build_kb_search_tool(kb) for kb in DEFAULT_REGISTRY.all()]
"""

from __future__ import annotations

import os

import httpx
import google.adk.tools as _adk_tools
import ang2react.components.qdrant.settings as _qdrant_settings_mod
import ang2react.components.llm.settings as _apigee_settings_mod

from .registry import KnowledgeBaseInfo

_DEFAULT_LIMIT = 5


def build_kb_search_tool(
    kb_info: KnowledgeBaseInfo,
    qdrant_settings=None,
    apigee_settings=None,
):
    """Build a named :class:`google.adk.tools.FunctionTool` for the given knowledge base.

    The tool is named ``kb_info.tool_name`` so the LLM can route to it explicitly.

    Args:
        kb_info: Knowledge base definition from the registry.
        qdrant_settings: Optional :class:`~ang2react.components.qdrant.QdrantSettings`.
            Reads from environment if not provided.
        apigee_settings: Optional :class:`~ang2react.components.llm.ApigeeSettings`.
            Reads from environment if not provided.

    Returns:
        :class:`google.adk.tools.FunctionTool` wrapping a named search function.
    """
    fn = _build_kb_search_fn(kb_info, qdrant_settings, apigee_settings)
    return _adk_tools.FunctionTool(fn)


def _build_kb_search_fn(
    kb_info: KnowledgeBaseInfo,
    qdrant_settings=None,
    apigee_settings=None,
):
    """Return the raw callable for a KB search (without FunctionTool wrapper).

    Useful for unit-testing the search logic directly.
    """

    def _search(query: str, limit: int = _DEFAULT_LIMIT) -> str:
        try:
            qdrant_s = qdrant_settings or _qdrant_settings_mod.load_qdrant_settings()
            apigee_s = apigee_settings or _apigee_settings_mod.load_settings()
            embedding = _get_embedding(query, apigee_s)
            hits = _query_collection(embedding, kb_info.collection, qdrant_s, limit, kb_info.vector_name)
            return "\n---\n".join(hits) if hits else "No relevant results found."
        except Exception as exc:  # noqa: BLE001
            return f"[{kb_info.tool_name} error] {exc}"

    _search.__name__ = kb_info.tool_name
    _search.__qualname__ = kb_info.tool_name
    _search.__doc__ = (
        f"Search {kb_info.name}: {kb_info.description}\n\n"
        "Args:\n"
        "    query: Natural-language search query.\n"
        "    limit: Max number of results to return (default 5).\n\n"
        "Returns:\n"
        "    Relevant text chunks joined by separators, or an error message."
    )
    return _search


def _get_embedding(text: str, apigee_settings) -> list[float]:
    """Embed text via the DHL GenAI Gateway (synchronous)."""
    deployment_id = apigee_settings.default_embedding_model or "text-embedding-ada-002-2"
    url = (
        f"{apigee_settings.proxy_url}/openai/deployments/{deployment_id}"
        f"/embeddings?api-version={apigee_settings.azure_api_version}"
    )
    resp = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {apigee_settings.api_key}",
            "Content-Type": "application/json",
        },
        json={"input": text},
        timeout=apigee_settings.timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def _query_collection(
    embedding: list[float],
    collection: str,
    qdrant_settings,
    limit: int,
    vector_name: str | None = None,
) -> list[str]:
    """Query a Qdrant collection and return page content strings.

    Uses the Qdrant Query API (``POST /collections/{name}/points/query``),
    available since Qdrant 1.10.0.

    Args:
        embedding: Query vector.
        collection: Qdrant collection name.
        qdrant_settings: QdrantSettings instance.
        limit: Maximum number of results to return.
        vector_name: Named vector to query (e.g. ``"dense"``). Required when
            the collection uses named vectors. Omit for single-vector collections.
    """
    headers: dict[str, str] = {}
    if qdrant_settings.api_key:
        headers["api-key"] = qdrant_settings.api_key
    # Only include "using" when the collection uses named vectors.
    # Omitting it tells Qdrant to use the collection's default (unnamed) vector.
    # Passing any value — even "dense" — to a single-vector collection returns 400.
    body: dict = {
        "query": embedding,
        "limit": limit,
        "with_payload": True,
        "with_vector": False,
    }
    if vector_name:
        body["using"] = vector_name
    resp = httpx.post(
        f"{qdrant_settings.url}/collections/{collection}/points/query",
        headers=headers,
        json=body,
        timeout=qdrant_settings.timeout_seconds,
    )
    resp.raise_for_status()
    return [
        hit.get("payload", {}).get("content", "").strip()
        for hit in resp.json().get("result", {}).get("points", [])
        if hit.get("payload", {}).get("content", "").strip()
    ]
