"""Test planner agent â€” testing strategy and coverage plan (V3, Phase 3 stage 3.1).

NEW in V3. Runs before test code generation: consumes the AnalysisReport,
MigrationPlan, and migrated-file manifest, and emits a TestPlan (strategy, test
matrix, mocking approach, manual checklist). The downstream test_generation agent
executes against this plan.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent

_PROMPT = Path(__file__).parent / "prompts" / "test_planner_agent.md"


def build_test_planner_agent(model):
    """Build the test planner agent for the V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for test planning (stage 3.1)
    """
    return Agent(
        model=model,
        name="test_planner_agent_v3",
        description=(
            "Produces a TestPlan for the migrated React app â€” testing strategy, a "
            "per-target test matrix (unit/integration/e2e), mocking strategy, coverage "
            "targets, and a manual-testing checklist. Runs before test generation."
        ),
        instruction=_PROMPT.read_text(encoding="utf-8"),
        tools=[],
    )


