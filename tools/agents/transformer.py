"""Transformer agent â€” Angular to React code conversion.

Stage 5: Transforms Angular source to React (JSX, hooks, functional components).
Operates on migration chunks, produces ReactSource artifacts.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

from tools.functions.angular_parser import parse_angular_source

_PROMPT = Path(__file__).parent / "prompts" / "transformer_agent.md"
_DUIL  = Path(__file__).parent / "prompts" / "_duil_fragment.md"


def _try_kb_tools(tool_ids: list[str]) -> list:
    """Return KB search FunctionTools for the given IDs, or [] if Qdrant is unavailable."""
    try:
        from tools.knowledge import DEFAULT_REGISTRY, build_kb_search_tool
        return [build_kb_search_tool(DEFAULT_REGISTRY.get(tid)) for tid in tool_ids]
    except Exception:
        return []


def build_transformer_agent(model):
    """Build transformer agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for Angular→React transformation
    """
    return Agent(
        model=model,
        name="transformer_agent_v3",
        description=(
            "Converts Angular source code to React 18+ with functional components, "
            "hooks, JSX, React Router, and React Hook Form. Produces ReactSource "
            "artifacts for each migration chunk."
        ),
        instruction=(
            _PROMPT.read_text(encoding="utf-8") + "\n\n" +
            _DUIL.read_text(encoding="utf-8")
        ),
        tools=[]  # No tools - agent outputs JSON directly
    )


