"""Programmatic orchestration FunctionTools for the V2 migration pipeline.

These tools bridge the root LLM and the infrastructure layer
(MigrationOrchestrator, ContextEngine, MigrationChunker, MigrationCache).

The root agent calls these tools to:
  - initialize_pipeline         Set up MigrationContext at Level 1
  - build_migration_chunks      Produce dependency-ordered MigrationPlan via MigrationChunker
  - get_context_for_stage       Project context to the correct level for each sub-agent
  - escalate_context            Request context level escalation
  - store_artifact              Register a typed artifact in the artifact registry
  - get_artifact                Retrieve a registered artifact
  - get_next_chunk              Return the next unprocessed chunk (for Phase 2 loop)
  - mark_chunk_done             Mark a chunk complete and store its result
  - get_pipeline_status         Return pipeline execution summary

Single-process / single-session design (standard for ADK web deployments).
For multi-session use replace the module-level state with a session-keyed dict.
"""
from __future__ import annotations

import json
import time
from typing import Any

from tools.pipeline.cache import get_cache
from tools.pipeline.context_engine import ContextEscalationPolicy, ContextEngine, EscalationTrigger
from tools.pipeline.models import (
    AnalysisReport,
    Component,
    ContextLevel,
    MigrationContext,
    MigrationPlan,
    Route,
    Service,
)
from tools.pipeline.orchestrator import MigrationOrchestrator, OrchestrationState

# ---------------------------------------------------------------------------
# Module-level pipeline state (one active pipeline per process)
# ---------------------------------------------------------------------------

_orchestrator = MigrationOrchestrator()
_pipeline_state: OrchestrationState | None = None
_tool_call_count = 0
_MAX_TOOL_CALLS = 200  # Safety limit to prevent infinite loops (Phase 2 chunk loop max)


def _check_loop_limit() -> dict[str, Any] | None:
    """Check if tool call limit exceeded (prevents infinite loops)."""
    global _tool_call_count
    _tool_call_count += 1
    if _tool_call_count > _MAX_TOOL_CALLS:
        return {
            "error": f"⚠️ SAFETY LIMIT REACHED: Tool called {_tool_call_count} times (max {_MAX_TOOL_CALLS}). "
            "This usually means the agent is stuck in a loop. "
            "Possible causes: Phase 2 chunk loop not terminating, or agent calling tools repeatedly. "
            "STOPPING to prevent runaway execution. Please restart and check your Angular project."
        }
    return None


def _reset_loop_count() -> None:
    """Reset loop counter (called when pipeline initializes)."""
    global _tool_call_count
    _tool_call_count = 0


def _require_state() -> dict[str, Any] | None:
    """Return an error dict when the pipeline has not been initialized."""
    if _pipeline_state is None:
        return {
            "error": (
                "Pipeline not initialized. "
                "Call initialize_pipeline(project_path) first for full-project migration, "
                "or call store_artifact('source_code', ...) directly for single-file mode."
            )
        }
    return None


# ---------------------------------------------------------------------------
# Tool 1 — Initialize pipeline
# ---------------------------------------------------------------------------

def initialize_pipeline(project_path: str) -> dict[str, Any]:
    """Initialize the V3 migration pipeline for an Angular project.

    MUST be called first (before any other pipeline tools) when migrating a
    full project. Builds a fresh MigrationContext at Level 1 (metadata only)
    and sets up the ContextEngine, artifact registry, and cache.

    Args:
        project_path: Absolute path to the Angular project root directory.

    Returns:
        Dict with 'status', 'context_level', and 'project_summary'.
    """
    global _pipeline_state

    # Reset loop counter on new pipeline initialization
    _reset_loop_count()

    context, engine = _orchestrator.initialize_context(project_path)
    _pipeline_state = OrchestrationState(
        context=context,
        context_engine=engine,
        start_time=time.time(),
    )
    return {
        "status": "initialized",
        "context_level": engine.current_level.name,
        "project_summary": context.project_summary,
    }


# ---------------------------------------------------------------------------
# Tool 2 — Build migration chunks
# ---------------------------------------------------------------------------

def build_migration_chunks(analysis_json: str) -> dict[str, Any]:
    """Build dependency-ordered migration chunks from an AnalysisReport.

    Wraps MigrationChunker to produce a MigrationPlan with topological sort
    and parallelization groups. Caches the plan for reuse.

    Includes loop limit check to prevent infinite loops.

    Call this after analyzer_agent produces its AnalysisReport JSON.

    Args:
        analysis_json: JSON string of the AnalysisReport from analyzer_agent.
                       Must contain 'components', 'services', 'routes' arrays.

    Returns:
        MigrationPlan dict with 'chunks', 'execution_order', 'parallel_groups',
        'total_chunks', and 'total_estimated_tokens'.
    """
    try:
        data = json.loads(analysis_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid AnalysisReport JSON: {e}"}

    try:
        analysis = AnalysisReport(
            components=[
                Component(
                    name=c.get("name", ""),
                    path=c.get("path", ""),
                    selector=c.get("selector", ""),
                    inputs=c.get("inputs", []),
                    outputs=c.get("outputs", []),
                    lifecycle_hooks=c.get("lifecycle_hooks", []),
                    template_type=c.get("template_type", "inline"),
                    has_forms=bool(c.get("has_forms", False)),
                    has_router=bool(c.get("has_router", False)),
                    dependencies=c.get("dependencies", []),
                )
                for c in data.get("components", [])
            ],
            services=[
                Service(
                    name=s.get("name", ""),
                    path=s.get("path", ""),
                    injectable=bool(s.get("injectable", True)),
                    dependencies=s.get("dependencies", []),
                    http_calls=s.get("http_calls", []),
                )
                for s in data.get("services", [])
            ],
            modules=data.get("modules", []),
            routes=[
                Route(
                    path=r.get("path", ""),
                    component=r.get("component"),
                    lazy_loaded=bool(r.get("lazy_loaded", False)),
                    guards=r.get("guards", []),
                )
                for r in data.get("routes", [])
            ],
            pipes=data.get("pipes", []),
            guards=data.get("guards", []),
            directives=data.get("directives", []),
            project_type=data.get("project_type", "standalone"),
            angular_version=data.get("angular_version", ""),
            total_files=int(data.get("total_files", 0)),
            total_lines=int(data.get("total_lines", 0)),
        )
    except Exception as e:
        return {"error": f"Failed to parse AnalysisReport fields: {e}"}

    plan = _orchestrator.build_plan_from_analysis(analysis)

    if _pipeline_state is not None:
        _pipeline_state.artifacts["migration_plan"] = plan
        _pipeline_state.artifacts.setdefault("processed_chunks", [])

    return {
        "total_chunks": len(plan.chunks),
        "execution_order": plan.execution_order,
        "parallel_groups": plan.parallel_groups,
        "total_estimated_tokens": plan.total_estimated_tokens,
        "recommended_batch_size": plan.recommended_batch_size,
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "type": c.type,
                "source_files": c.source_files,
                "dependencies": c.dependencies,
                "priority": c.priority,
                "estimated_tokens": c.estimated_tokens,
            }
            for c in plan.chunks
        ],
    }


# ---------------------------------------------------------------------------
# Tool 3 — Context projection
# ---------------------------------------------------------------------------

def get_context_for_stage(stage_name: str, level: int) -> dict[str, Any]:
    """Get migration context projected to the correct level for a pipeline stage.

    Call this BEFORE invoking each sub-agent to obtain the right amount of
    context detail. Higher levels include more source code but cost more tokens.

    Context levels:
      1 = METADATA_ONLY   — file names, project structure
                            (use for: analyzer, risk_detection, migration_planner)
      2 = AST_SUMMARIES   — class/function signatures
                            (use for: state_migration)
      3 = SOURCE_FRAGMENTS — targeted code snippets
                            (use for: transformer, refactor, test_generation, validator)
      4 = FULL_SOURCE     — complete file contents
                            (use only if Level 3 is still insufficient)

    Args:
        stage_name: Name of the requesting agent (used in escalation logging).
        level: Desired context level integer (1–4).

    Returns:
        Context payload dict at the requested level.
    """
    err = _require_state()
    if err:
        return err

    try:
        ctx_level = ContextLevel(level)
    except ValueError:
        return {"error": f"Invalid context level {level!r}. Must be an integer 1–4."}

    return _pipeline_state.context_engine.project(ctx_level)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Tool 4 — Context escalation
# ---------------------------------------------------------------------------

def escalate_context(agent_name: str, reason: str) -> dict[str, Any]:
    """Request one context level escalation when current detail is insufficient.

    Escalates from the current level to the next (e.g., Level 1 → Level 2).
    Bounded by the escalation policy (max 2 escalations per agent, no skipping).

    Args:
        agent_name: Name of the requesting agent (e.g., 'transformer_agent_v3').
        reason: Explanation of why more detail is needed (recorded in the log).

    Returns:
        Dict with 'escalated_to', 'previous_level', and 'context' payload,
        or 'error' if escalation is denied by policy.
    """
    err = _require_state()
    if err:
        return err

    engine: ContextEngine = _pipeline_state.context_engine  # type: ignore[union-attr]
    current = engine.current_level
    target_value = min(current.value + 1, ContextLevel.FULL_SOURCE.value)
    target = ContextLevel(target_value)

    success, payload = engine.escalate(
        agent_name=agent_name,
        target_level=target,
        trigger=EscalationTrigger.AGENT_REQUEST,
        reason=reason,
    )

    if not success:
        return {
            "error": (
                f"Context escalation denied for '{agent_name}' "
                f"(max escalations reached or target not higher than current). "
                f"Current level: {current.name}."
            )
        }

    return {
        "escalated_to": target.name,
        "previous_level": current.name,
        "context": payload,
    }


# ---------------------------------------------------------------------------
# Tool 5 — Artifact registry: store
# ---------------------------------------------------------------------------

def store_artifact(stage_name: str, artifact_json: str) -> dict[str, Any]:
    """Store a typed pipeline artifact in the artifact registry.

    Call after each agent stage completes to register its output for downstream
    stages. Artifacts are retrievable by stage_name via get_artifact().

    Recommended stage_name values:
      'analysis'       — AnalysisReport from analyzer_agent
      'risk'           — RiskReport from risk_detection_agent
      'plan'           — MigrationPlan from migration_planner_agent
      'state_plan'     — StateMigrationPlan from state_migration_agent
      'validation'     — ValidationReport from validator_agent_v3
      'report'         — MigrationReport from report_agent
      'chunk_<id>'     — Per-chunk result (e.g., 'chunk_UserList_0')

    Args:
        stage_name: Registry key for this artifact.
        artifact_json: JSON string of the artifact to store.

    Returns:
        Confirmation dict with 'stored' key and top-level field names.
    """
    try:
        artifact = json.loads(artifact_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid artifact JSON: {e}"}

    if _pipeline_state is not None:
        _pipeline_state.artifacts[stage_name] = artifact
    else:
        get_cache().set("artifact", artifact, stage=stage_name)

    top_keys = list(artifact.keys()) if isinstance(artifact, dict) else f"list[{len(artifact)}]"
    return {"stored": stage_name, "top_level_keys": top_keys}


# ---------------------------------------------------------------------------
# Tool 6 — Artifact registry: retrieve
# ---------------------------------------------------------------------------

def get_artifact(stage_name: str) -> dict[str, Any]:
    """Retrieve a previously stored pipeline artifact by stage name.

    Args:
        stage_name: The key used when storing (e.g., 'analysis', 'risk').

    Returns:
        The stored artifact dict, or an error dict if not found.
    """
    if _pipeline_state is not None:
        artifact = _pipeline_state.artifacts.get(stage_name)
        if artifact is not None:
            if isinstance(artifact, dict):
                return artifact
            return {"data": artifact}

    cached = get_cache().get("artifact", stage=stage_name)
    if cached is not None:
        return cached if isinstance(cached, dict) else {"data": cached}

    available = list(_pipeline_state.artifacts.keys()) if _pipeline_state else []
    return {
        "error": f"No artifact stored for stage '{stage_name}'.",
        "available_stages": available,
    }


# ---------------------------------------------------------------------------
# Tool 7 — Chunk iteration: get next
# ---------------------------------------------------------------------------

def get_next_chunk() -> dict[str, Any]:
    """Return the next unprocessed migration chunk from the execution order.

    Use inside the Phase 2 transformation loop:
      1. Call get_next_chunk() to get the chunk
      2. Call transformer_agent with the chunk's source_files
      3. Call refactor_agent on the transformer output
      4. Call test_generation_agent on the refactored output
      5. Call mark_chunk_done(chunk_id, result_json) to advance the pointer
      6. Repeat until get_next_chunk() returns {'done': True}

    Returns:
        Chunk details dict, or {'done': True, 'total_processed': N} when finished.
    """
    # Check loop limit (prevents Phase 2 loop from running forever)
    err = _check_loop_limit()
    if err:
        return err

    err = _require_state()
    if err:
        return err

    plan: MigrationPlan | None = _pipeline_state.artifacts.get("migration_plan")  # type: ignore[union-attr]
    if not plan:
        return {
            "error": (
                "No MigrationPlan in pipeline state. "
                "Call build_migration_chunks(analysis_json) first."
            )
        }

    processed: list[str] = _pipeline_state.artifacts.get("processed_chunks", [])  # type: ignore[union-attr]
    total = len(plan.execution_order)

    for chunk_id in plan.execution_order:
        if chunk_id not in processed:
            chunk = next((c for c in plan.chunks if c.chunk_id == chunk_id), None)
            if chunk:
                return {
                    "chunk_id": chunk.chunk_id,
                    "type": chunk.type,
                    "source_files": chunk.source_files,
                    "dependencies": chunk.dependencies,
                    "priority": chunk.priority,
                    "estimated_tokens": chunk.estimated_tokens,
                    "progress": f"{len(processed)}/{total}",
                    "remaining_after_this": total - len(processed) - 1,
                }

    return {"done": True, "total_processed": len(processed)}


# ---------------------------------------------------------------------------
# Tool 8 — Chunk iteration: mark done
# ---------------------------------------------------------------------------

def mark_chunk_done(chunk_id: str, result_json: str) -> dict[str, Any]:
    """Mark a migration chunk as processed and store its ReactSource result.

    Call after transformer + refactor + test_generation have finished for a chunk.

    Args:
        chunk_id: ID of the completed chunk (from get_next_chunk response).
        result_json: JSON string of the chunk output (RefactoredReactSource artifact).

    Returns:
        Progress summary with completion count and percentage.
    """
    # Check loop limit
    err = _check_loop_limit()
    if err:
        return err

    err = _require_state()
    if err:
        return err

    processed: list[str] = _pipeline_state.artifacts.setdefault("processed_chunks", [])  # type: ignore[union-attr]
    if chunk_id not in processed:
        processed.append(chunk_id)

    chunk_results: dict = _pipeline_state.artifacts.setdefault("chunk_results", {})  # type: ignore[union-attr]
    try:
        chunk_results[chunk_id] = json.loads(result_json)
    except json.JSONDecodeError:
        chunk_results[chunk_id] = {"content": result_json}

    plan: MigrationPlan | None = _pipeline_state.artifacts.get("migration_plan")  # type: ignore[union-attr]
    total = len(plan.execution_order) if plan else len(processed)
    done = len(processed)

    return {
        "chunk_id": chunk_id,
        "status": "completed",
        "chunks_done": done,
        "total_chunks": total,
        "percentage_complete": round(done / total * 100) if total else 0,
    }


# ---------------------------------------------------------------------------
# Tool 9 — Pipeline status
# ---------------------------------------------------------------------------

def get_pipeline_status() -> dict[str, Any]:
    """Get current V2 pipeline execution status and metrics.

    Returns:
        Summary dict with context level, artifact inventory, chunk progress,
        escalation history, elapsed time, and cache statistics.
    """
    if _pipeline_state is None:
        return {"status": "not_initialized"}

    processed: list[str] = _pipeline_state.artifacts.get("processed_chunks", [])
    plan: MigrationPlan | None = _pipeline_state.artifacts.get("migration_plan")
    total_chunks = len(plan.execution_order) if plan else 0

    # Exclude internal bookkeeping keys from artifact inventory
    _internal = {"processed_chunks", "chunk_results", "migration_plan"}
    user_artifacts = [k for k in _pipeline_state.artifacts if k not in _internal]

    return {
        "status": "running",
        "current_context_level": _pipeline_state.context_engine.current_level.name,
        "artifacts_stored": user_artifacts,
        "chunks_processed": len(processed),
        "total_chunks": total_chunks,
        "percentage_complete": round(len(processed) / total_chunks * 100) if total_chunks else 0,
        "escalation_summary": _pipeline_state.context_engine.get_escalation_summary(),
        "elapsed_seconds": round(time.time() - _pipeline_state.start_time, 1),
        "cache_stats": _orchestrator.cache.stats(),
    }
