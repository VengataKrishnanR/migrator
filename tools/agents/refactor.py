"""Refactor agent â€” React code optimization and anti-pattern removal.

Stage 6: Refines ReactSource to eliminate anti-patterns, apply best practices,
and optimize performance. Produces RefactoredReactSource artifacts.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

from tools.functions.react_validator import validate_react_code

_PROMPT = Path(__file__).parent / "prompts" / "refactor_agent.md"
_DUIL  = Path(__file__).parent / "prompts" / "_duil_fragment.md"


def _try_kb_tools(tool_ids: list[str]) -> list:
    """Return KB search FunctionTools for the given IDs, or [] if Qdrant is unavailable."""
    try:
        from tools.knowledge import DEFAULT_REGISTRY, build_kb_search_tool
        return [build_kb_search_tool(DEFAULT_REGISTRY.get(tid)) for tid in tool_ids]
    except Exception:
        return []


def build_refactor_agent(model):
    """Build refactor agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for React code refactoring
    """
    return Agent(
        model=model,
        name="refactor_agent_v3",
        description=(
            "Refactors converted React code to remove anti-patterns, apply best "
            "practices, optimize performance (memoization, lazy loading), and "
            "improve code quality. Produces RefactoredReactSource artifacts."
        ),
        instruction=(
            _PROMPT.read_text(encoding="utf-8") + "\n\n" +
            _DUIL.read_text(encoding="utf-8")
        ),
        tools=[]  # No tools - agent outputs JSON directly
    )



