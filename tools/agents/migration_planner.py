"""Migration planner agent â€” Chunk-based execution roadmap.

Stage 3: Analyzes AnalysisReport + RiskReport and emits MigrationPlan with
dependency-ordered chunks and parallelization strategy.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

from tools.agents.orchestration_tools import build_migration_chunks

_PROMPT = Path(__file__).parent / "prompts" / "migration_planner_agent.md"


def build_migration_planner_agent(model):
    """Build migration planner agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for planning stage
    """
    return Agent(
        model=model,
        name="migration_planner_agent_v3",
        description=(
            "Creates chunk-based migration plan from AnalysisReport and RiskReport. "
            "Produces MigrationPlan with dependency-ordered execution chunks, "
            "parallelization groups, and token estimates."
        ),
        instruction=_PROMPT.read_text(encoding="utf-8"),
        tools=[],  # No tools - agent outputs JSON directly
    )


