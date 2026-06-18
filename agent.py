"""ADK entry point — NgReact Angular-to-React migration agent.

V3 architecture: 9-agent artifact-driven pipeline with programmatic orchestration,
hierarchical context management, chunk-based execution, and artifact registry.

The root agent orchestrates via two layers of tools:
  - 9 AgentTools: specialized LLM sub-agents for each pipeline stage
  - Orchestration FunctionTools: programmatic wrappers for context projection,
    chunk iteration, and artifact registry (backed by MigrationOrchestrator)
  - 3 Helper FunctionTools: deterministic project analysis utilities
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.tools import AgentTool, FunctionTool

from components.llm import build_model_for_env
from components.logging import configure_logging
from components.tracing import apply_tracing_patch
from tools.agents import (
    build_analyzer_agent,
    build_risk_detection_agent,
    build_migration_planner_agent,
    build_state_migration_agent,
    build_transformer_agent,
    build_refactor_agent,
    build_test_generation_agent,
    build_validator_agent_v3,
    build_report_agent,
)
from tools.agents.orchestration_tools import (
    initialize_pipeline,
    build_migration_chunks,
    get_context_for_stage,
    escalate_context,
    store_artifact,
    get_artifact,
    get_next_chunk,
    mark_chunk_done,
    get_pipeline_status,
)
from tools.functions.pipeline_tools import (
    analyze_project_structure,
    estimate_migration_complexity,
    validate_chunk_dependencies,
    read_angular_file,
    ingest_zip,
    clone_git_repo,
)

configure_logging()
apply_tracing_patch()

_PROMPT = Path(__file__).parent / "prompts" / "root_agent_v3.md"

# Model — selected by NGREACT_LLM_MODE env var (stub | google-ai | apigee).
model = build_model_for_env()

# ---------------------------------------------------------------------------
# Sub-agents (9-stage artifact-driven pipeline)
# ---------------------------------------------------------------------------

# Phase 1: Analysis & Planning
analyzer_agent = build_analyzer_agent(model)
risk_detection_agent = build_risk_detection_agent(model)
migration_planner_agent = build_migration_planner_agent(model)
state_migration_agent = build_state_migration_agent(model)

# Phase 2: Transformation (per-chunk)
transformer_agent = build_transformer_agent(model)
refactor_agent = build_refactor_agent(model)
test_generation_agent = build_test_generation_agent(model)

# Phase 3: Validation & Reporting
validator_agent_v3 = build_validator_agent_v3(model)
report_agent = build_report_agent(model)

# ---------------------------------------------------------------------------
# Root orchestrator
# ---------------------------------------------------------------------------

root_agent = Agent(
    model=model,
    name="ngreact_v3",
    description=(
        "NgReact V3 — Artifact-driven Angular-to-React migration agent with "
        "9-stage pipeline, hierarchical context management, chunk-based execution, "
        "and full artifact registry."
    ),
    instruction=_PROMPT.read_text(encoding="utf-8").replace("{", "｛").replace("}", "｝"),
    tools=[
        # ── Phase 1: Analysis & Planning sub-agents ──────────────────────────
        AgentTool(analyzer_agent),
        AgentTool(risk_detection_agent),
        AgentTool(migration_planner_agent),
        AgentTool(state_migration_agent),

        # ── Phase 2: Transformation sub-agents ───────────────────────────────
        AgentTool(transformer_agent),
        AgentTool(refactor_agent),
        AgentTool(test_generation_agent),

        # ── Phase 3: Validation & Reporting sub-agents ───────────────────────
        AgentTool(validator_agent_v3),
        AgentTool(report_agent),

        # ── Orchestration tools (context, chunks, artifact registry) ─────────
        FunctionTool(initialize_pipeline),
        FunctionTool(build_migration_chunks),
        FunctionTool(get_context_for_stage),
        FunctionTool(escalate_context),
        FunctionTool(store_artifact),
        FunctionTool(get_artifact),
        FunctionTool(get_next_chunk),
        FunctionTool(mark_chunk_done),
        FunctionTool(get_pipeline_status),

        # ── Deterministic project analysis helpers ────────────────────────────
        FunctionTool(analyze_project_structure),
        FunctionTool(estimate_migration_complexity),
        FunctionTool(validate_chunk_dependencies),
        FunctionTool(read_angular_file),
        FunctionTool(ingest_zip),
        FunctionTool(clone_git_repo),
    ],
)
