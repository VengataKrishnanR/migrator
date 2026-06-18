"""Test generation agent â€” Automated test suite creation.

Stage 7: Generates test cases for converted React components using Vitest/
Testing Library. Produces TestSuite artifacts.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

from tools.functions.react_validator import validate_react_code

_PROMPT = Path(__file__).parent / "prompts" / "test_generation_agent.md"
_DUIL  = Path(__file__).parent / "prompts" / "_duil_fragment.md"


def build_test_generation_agent(model):
    """Build test generation agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for test generation
    """
    return Agent(
        model=model,
        name="test_generation_agent_v3",
        description=(
            "Generates automated test suites for converted React components using "
            "Vitest and React Testing Library. Produces TestSuite artifacts with "
            "unit, integration, and interaction tests."
        ),
        instruction=(
            _PROMPT.read_text(encoding="utf-8") + "\n\n" +
            _DUIL.read_text(encoding="utf-8")
        ),
        tools=[],  # No tools - agent outputs JSON directly
    )


