"""Validator agent V3 â€” Quality gate for converted React code.

Stage 8: Validates RefactoredReactSource for correctness, React best practices,
TypeScript errors, and ESLint violations. Produces ValidationReport with
pass/fail decision.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

from tools.functions.react_validator import validate_react_code

_PROMPT = Path(__file__).parent / "prompts" / "validator_agent.md"
_DUIL  = Path(__file__).parent / "prompts" / "_duil_fragment.md"


def _try_kb_tools(tool_ids: list[str]) -> list:
    """Return KB search FunctionTools for the given IDs, or [] if Qdrant is unavailable."""
    try:
        from tools.knowledge import DEFAULT_REGISTRY, build_kb_search_tool
        return [build_kb_search_tool(DEFAULT_REGISTRY.get(tid)) for tid in tool_ids]
    except Exception:
        return []


def build_validator_agent_v3(model):
    """Build validator agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for validation stage
    """
    return Agent(
        model=model,
        name="validator_agent_v3",
        description=(
            "Quality gate for converted React code. Validates TypeScript compilation, "
            "ESLint rules, React best practices, hooks violations, and accessibility. "
            "Produces ValidationReport with pass/fail and detailed issues."
        ),
        instruction=(
            _PROMPT.read_text(encoding="utf-8") + "\n\n" +
            _DUIL.read_text(encoding="utf-8")
        ),
        tools=[]  # No tools - agent outputs JSON directly
    )


