"""Report agent â€” Final migration summary and documentation.

Stage 9: Aggregates all artifacts and produces MigrationReport with metrics,
next steps, warnings, and output files.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent

_PROMPT = Path(__file__).parent / "prompts" / "report_agent.md"


def build_report_agent(model):
    """Build report agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for final report generation
    """
    return Agent(
        model=model,
        name="report_agent_v3",
        description=(
            "ONLY call this after completing ALL Phase 1 analysis stages AND ALL "
            "Phase 2 chunk transformations for a full Angular project migration. "
            "Generates the final MigrationReport aggregating analysis, risk, plan, "
            "state, conversion, test, and validation artifacts. "
            "Do NOT call for greetings, questions, or single-component conversions."
        ),
        instruction=_PROMPT.read_text(encoding="utf-8"),
        tools=[],
    )


