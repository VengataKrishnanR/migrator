"""Migration orchestrator for V2 artifact-driven pipeline.

Coordinates execution of 9-agent pipeline with hierarchical context management,
caching, and chunk-based processing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .cache import get_cache
from .chunking import ChunkingStrategy, MigrationChunker
from .context_engine import ContextEngine, ContextEscalationPolicy
from .contracts import AgentExecutionSpec
from .models import (
    AnalysisReport,
    ContextLevel,
    MigrationContext,
    MigrationMetrics,
    MigrationPlan,
    MigrationReport,
    ReactSource,
    RefactoredReactSource,
    RiskReport,
    StateMigrationPlan,
    TestSuite,
    ValidationReport,
)


@dataclass
class OrchestrationState:
    """Runtime state for migration orchestration."""

    context: MigrationContext
    context_engine: ContextEngine
    artifacts: dict[str, Any] = field(default_factory=dict)  # Stage outputs
    metrics: MigrationMetrics = field(default_factory=MigrationMetrics)
    start_time: float = 0.0

    def __post_init__(self):
        """Initialize start time."""
        if self.start_time == 0.0:
            self.start_time = time.time()


class MigrationOrchestrator:
    """Orchestrates V2 migration pipeline execution.

    Manages:
    - Agent execution order and contracts
    - Context level projection and escalation
    - Artifact registry and handoffs
    - Caching and token optimization
    - Metrics collection
    """

    def __init__(
        self,
        chunking_strategy: ChunkingStrategy | None = None,
        escalation_policy: ContextEscalationPolicy | None = None,
    ):
        """Initialize orchestrator.

        Args:
            chunking_strategy: Migration chunking configuration
            escalation_policy: Context escalation policy
        """
        self.chunking_strategy = chunking_strategy or ChunkingStrategy()
        self.escalation_policy = escalation_policy or ContextEscalationPolicy()
        self.cache = get_cache()
        self.chunker = MigrationChunker(self.chunking_strategy)

    def initialize_context(
        self, angular_project_path: str
    ) -> tuple[MigrationContext, ContextEngine]:
        """Initialize migration context from Angular project.

        Args:
            angular_project_path: Path to Angular project root

        Returns:
            (MigrationContext, ContextEngine) tuple
        """
        # Check cache first
        cached = self.cache.get("context", project_path=angular_project_path)
        if cached:
            context = cached
        else:
            # Build fresh context (Level 1 only initially)
            context = MigrationContext(
                project_summary={
                    "path": angular_project_path,
                    "initialized_at": time.time(),
                },
                dependency_graph={},  # Will be populated by analyzer_agent
            )
            self.cache.set("context", context, project_path=angular_project_path)

        # Create context engine
        engine = ContextEngine(context, self.escalation_policy)

        return context, engine

    def execute_stage(
        self,
        state: OrchestrationState,
        spec: AgentExecutionSpec,
        agent_callable: Any,  # Actual agent invocation
        input_artifact: Any,
    ) -> Any:
        """Execute single agent stage with context management.

        Args:
            state: Current orchestration state
            spec: Agent execution specification
            agent_callable: Agent invocation function
            input_artifact: Input for this stage

        Returns:
            Output artifact from agent execution
        """
        # Project context to agent's minimum level
        context_payload = state.context_engine.project(spec.min_context_level)

        # Try execution at minimum level first
        for attempt in range(spec.max_retries + 1):
            try:
                # Invoke agent with projected context
                output = agent_callable(input_artifact, context_payload)

                # Cache successful output
                self.cache.set(
                    spec.cache_key_prefix,
                    output,
                    input_hash=hash(str(input_artifact)),
                )

                return output

            except Exception as e:
                error_msg = str(e)

                # Escalate context on any non-API error (API errors need retry, not more context)
                _api_error = any(code in error_msg for code in ["429", "500", "502", "503", "504"])
                if spec.allow_escalation and not _api_error:
                    next_level = min(
                        spec.min_context_level + 1, spec.max_context_level
                    )

                    if next_level > state.context_engine.current_level:
                        success, new_payload = state.context_engine.escalate(
                            agent_name=spec.agent_name,
                            target_level=next_level,
                            reason=f"Retry {attempt + 1} after error",
                        )

                        if success:
                            context_payload = new_payload
                            continue

                # If last attempt, raise
                if attempt == spec.max_retries:
                    raise

        # Should not reach here
        raise RuntimeError(f"Agent {spec.agent_name} failed after {spec.max_retries} retries")

    def build_plan_from_analysis(self, analysis: AnalysisReport) -> MigrationPlan:
        """Build migration plan from analysis report.

        Args:
            analysis: Output from analyzer_agent

        Returns:
            Executable migration plan
        """
        # Check cache
        cached = self.cache.get("migration_plan", analysis_hash=hash(str(analysis)))
        if cached:
            return cached

        # Build fresh plan
        plan = self.chunker.build_plan(analysis)

        # Cache for reuse
        self.cache.set("migration_plan", plan, analysis_hash=hash(str(analysis)))

        return plan

    def execute_chunk(
        self,
        state: OrchestrationState,
        chunk_id: str,
        # Agent callables would be passed here
    ) -> dict[str, Any]:
        """Execute migration for a single chunk.

        Args:
            state: Current orchestration state
            chunk_id: Chunk to process

        Returns:
            Chunk execution results
        """
        # Get chunk from plan
        plan: MigrationPlan = state.artifacts.get("migration_plan")
        if not plan:
            raise ValueError("No migration plan in state")

        chunk = next((c for c in plan.chunks if c.chunk_id == chunk_id), None)
        if not chunk:
            raise ValueError(f"Chunk {chunk_id} not found in plan")

        # Check cache
        cached = self.cache.get("chunk_result", chunk_id=chunk_id)
        if cached:
            return cached

        # Execute chunk-specific pipeline
        # (transformer -> refactor -> test_generation -> validator)
        # This would invoke actual agents - stubbed for now

        result = {
            "chunk_id": chunk_id,
            "status": "completed",
            "files_generated": chunk.source_files,
        }

        # Cache result
        self.cache.set("chunk_result", result, chunk_id=chunk_id)

        return result

    def finalize_report(
        self,
        state: OrchestrationState,
        validation: ValidationReport,
        output_files: list[str],
    ) -> MigrationReport:
        """Generate final migration report.

        Args:
            state: Current orchestration state
            validation: Final validation results
            output_files: List of generated React files

        Returns:
            Complete migration report
        """
        # Calculate metrics
        duration = time.time() - state.start_time
        state.metrics.duration_seconds = duration

        return MigrationReport(
            success=validation.passed,
            metrics=state.metrics,
            validation=validation,
            output_files=output_files,
            next_steps=[
                "Review validation report for any warnings",
                "Run test suite with `npm test`",
                "Check manually for complex state interactions",
                "Update package.json dependencies",
                "Configure build system (Vite/Webpack)",
            ],
            warnings=[],
        )

    def get_execution_summary(self, state: OrchestrationState) -> dict[str, Any]:
        """Get summary of orchestration execution.

        Args:
            state: Current orchestration state

        Returns:
            Dict with execution metrics and context escalation info
        """
        return {
            "duration_seconds": time.time() - state.start_time,
            "artifacts_generated": list(state.artifacts.keys()),
            "context_escalations": state.context_engine.get_escalation_summary(),
            "cache_stats": self.cache.stats(),
            "metrics": {
                "files_migrated": state.metrics.files_migrated,
                "lines_converted": state.metrics.lines_converted,
                "total_tokens": state.metrics.total_tokens_used,
            },
        }
