"""Analyzer agent — Project-wide Angular structure extraction.

Stage 1: Analyzes Angular project and emits AnalysisReport with components,
services, modules, routes, and project metadata.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

from tools.functions.angular_parser import parse_angular_source

_PROMPT = Path(__file__).parent / "prompts" / "analyzer_agent.md"


def _try_kb_tools(tool_ids: list[str]) -> list:
    """Return KB search FunctionTools for the given IDs, or [] if Qdrant is unavailable."""
    try:
        from tools.knowledge import DEFAULT_REGISTRY, build_kb_search_tool
        return [build_kb_search_tool(DEFAULT_REGISTRY.get(tid)) for tid in tool_ids]
    except Exception:
        return []


def build_analyzer_agent(model):
    """Build analyzer agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for analysis stage
    """
    return Agent(
        model=model,
        name="analyzer_agent_v3",
        description=(
            "Analyzes Angular project structure and extracts components, services, "
            "modules, routes, pipes, guards, directives. Produces comprehensive "
            "AnalysisReport with project metadata and dependency graph."
        ),
        instruction=_PROMPT.read_text(encoding="utf-8"),
        tools=[],  # No tools - agent outputs JSON directly
    )
