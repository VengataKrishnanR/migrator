"""State migration agent â€” Angular state to React state mapping.

Stage 4: Analyzes state management patterns and emits StateMigrationPlan with
conversion strategy (Context, Redux, Zustand, or custom hooks).
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

from tools.functions.angular_parser import parse_angular_source

_PROMPT = Path(__file__).parent / "prompts" / "state_migration_agent.md"


def build_state_migration_agent(model):
    """Build state migration agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for state migration planning
    """
    return Agent(
        model=model,
        name="state_migration_agent_v3",
        description=(
            "Analyzes Angular state management patterns (services, component props, "
            "template variables) and produces StateMigrationPlan with React state "
            "strategy (Context API, custom hooks, or state library)."
        ),
        instruction=_PROMPT.read_text(encoding="utf-8"),
        tools=[],  # No tools - agent outputs JSON directly
    )


