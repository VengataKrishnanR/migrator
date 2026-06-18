"""Risk detection agent â€” Migration risk analysis and scoring.

Stage 2: Analyzes AnalysisReport and emits RiskReport with severity-scored
risks, blockers, and recommended migration approach.
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

_PROMPT = Path(__file__).parent / "prompts" / "risk_detection_agent.md"


def detect_risk_patterns(analysis_data: dict) -> list[dict]:
    """Deterministic risk pattern detection helper.

    Args:
        analysis_data: Serialized AnalysisReport

    Returns:
        List of detected risk patterns
    """
    risks = []

    # Check for complex forms
    forms_count = sum(1 for c in analysis_data.get("components", []) if c.get("has_forms"))
    if forms_count > 5:
        risks.append({
            "severity": "high",
            "category": "complexity",
            "description": f"{forms_count} components use Angular forms (complex migration to React Hook Form)",
            "affected_files": [c["path"] for c in analysis_data.get("components", []) if c.get("has_forms")],
        })

    # Check for lazy loading
    lazy_routes = sum(1 for r in analysis_data.get("routes", []) if r.get("lazy_loaded"))
    if lazy_routes > 0:
        risks.append({
            "severity": "medium",
            "category": "complexity",
            "description": f"{lazy_routes} lazy-loaded routes require React.lazy() + Suspense migration",
            "affected_files": [],
        })

    # Check for custom directives
    directives = len(analysis_data.get("directives", []))
    if directives > 0:
        risks.append({
            "severity": "high",
            "category": "compatibility",
            "description": f"{directives} custom directives need manual rewrite (no direct React equivalent)",
            "affected_files": [d.get("path", "") for d in analysis_data.get("directives", [])],
        })

    # Check project size
    total_files = analysis_data.get("total_files", 0)
    if total_files > 100:
        risks.append({
            "severity": "medium",
            "category": "complexity",
            "description": f"Large project ({total_files} files) â€” recommend incremental migration",
            "affected_files": [],
        })

    return risks


def build_risk_detection_agent(model):
    """Build risk detection agent for V3 pipeline.

    Args:
        model: Shared LLM instance

    Returns:
        Configured Agent for risk analysis stage
    """
    return Agent(
        model=model,
        name="risk_detection_agent_v3",
        description=(
            "Analyzes AnalysisReport and identifies migration risks (complexity, "
            "compatibility, data-loss, performance). Produces RiskReport with "
            "severity-scored risks and recommended migration approach."
        ),
        instruction=_PROMPT.read_text(encoding="utf-8"),
        tools=[],  # No tools - agent outputs JSON directly
    )

