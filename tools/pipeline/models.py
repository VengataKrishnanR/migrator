"""Typed artifact models for V2 migration pipeline.

Each agent stage produces and consumes strongly-typed artifacts to minimize
raw source exchange and enable precise context control.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ContextLevel(IntEnum):
    """Hierarchical context projection levels for token optimization."""

    METADATA_ONLY = 1      # Project structure, file names, dependencies
    AST_SUMMARIES = 2      # Abstract syntax tree summaries
    SOURCE_FRAGMENTS = 3   # Targeted code snippets
    FULL_SOURCE = 4        # Complete source files


@dataclass
class Component:
    """Angular component metadata."""

    name: str
    path: str
    selector: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    lifecycle_hooks: list[str] = field(default_factory=list)
    template_type: str = "inline"  # inline | external
    has_forms: bool = False
    has_router: bool = False
    dependencies: list[str] = field(default_factory=list)


@dataclass
class Service:
    """Angular service metadata."""

    name: str
    path: str
    injectable: bool = True
    dependencies: list[str] = field(default_factory=list)
    http_calls: list[str] = field(default_factory=list)


@dataclass
class Route:
    """Angular route metadata."""

    path: str
    component: str | None = None
    lazy_loaded: bool = False
    guards: list[str] = field(default_factory=list)
    children: list[Route] = field(default_factory=list)


@dataclass
class DependencyNode:
    """Dependency graph node."""

    file_path: str
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)


@dataclass
class AnalysisReport:
    """Output of analyzer_agent — project-wide Angular structure."""

    components: list[Component]
    services: list[Service]
    modules: list[dict[str, Any]]
    routes: list[Route]
    pipes: list[dict[str, str]]
    guards: list[dict[str, str]]
    directives: list[dict[str, str]]
    project_type: str = "standalone"  # standalone | module-based
    angular_version: str = ""
    total_files: int = 0
    total_lines: int = 0


@dataclass
class RiskItem:
    """Individual migration risk."""

    severity: str  # critical | high | medium | low
    category: str  # complexity | compatibility | data-loss | performance
    description: str
    affected_files: list[str]
    mitigation: str = ""


@dataclass
class RiskReport:
    """Output of risk_detection_agent — migration risks and blockers."""

    risks: list[RiskItem]
    overall_risk_score: float  # 0.0 (safe) to 1.0 (critical)
    recommended_approach: str = "incremental"  # incremental | big-bang | hybrid
    estimated_effort_hours: int = 0


@dataclass
class MigrationChunk:
    """Unit of migration work."""

    chunk_id: str
    type: str  # component | service | module | route
    source_files: list[str]
    dependencies: list[str]
    priority: int = 1
    estimated_tokens: int = 0


@dataclass
class MigrationPlan:
    """Output of migration_planner_agent — execution roadmap."""

    chunks: list[MigrationChunk]
    execution_order: list[str]  # chunk_ids in dependency order
    parallel_groups: list[list[str]]  # chunks that can run in parallel
    total_estimated_tokens: int = 0
    recommended_batch_size: int = 5


@dataclass
class StateMapping:
    """Angular state to React state mapping."""

    angular_pattern: str  # service | component-prop | template-variable
    react_pattern: str    # context | hook | prop
    source: str
    target: str
    notes: str = ""


@dataclass
class StateMigrationPlan:
    """Output of state_migration_agent — state management strategy."""

    mappings: list[StateMapping]
    recommended_library: str = "context"  # context | redux | zustand | none
    shared_state_files: list[str] = field(default_factory=list)
    requires_refactoring: bool = False


@dataclass
class ReactSource:
    """Output of transformer_agent — converted React code."""

    file_path: str
    content: str
    component_name: str = ""
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    uses_hooks: list[str] = field(default_factory=list)
    has_typescript_errors: bool = False


@dataclass
class RefactoredReactSource:
    """Output of refactor_agent — cleaned and optimized React code."""

    file_path: str
    content: str
    optimizations_applied: list[str] = field(default_factory=list)
    removed_anti_patterns: list[str] = field(default_factory=list)
    performance_improvements: list[str] = field(default_factory=list)


@dataclass
class TestCase:
    """Individual test case."""

    name: str
    type: str  # unit | integration | e2e
    file_path: str
    content: str
    covers: list[str] = field(default_factory=list)


@dataclass
class TestSuite:
    """Output of test_generation_agent — automated test cases."""

    tests: list[TestCase]
    coverage_targets: list[str]
    framework: str = "vitest"  # vitest | jest | testing-library
    total_tests: int = 0


@dataclass
class TestMatrixEntry:
    """One row of the test matrix — what to test for a given target."""

    target: str
    type: str  # unit | integration | e2e
    scenarios: list[str] = field(default_factory=list)
    priority: str = "medium"  # high | medium | low


@dataclass
class TestPlan:
    """Output of test_planner_agent (V3, stage 3.1) — the testing strategy.

    The complete testing *plan* the test-generation stage executes against:
    strategy, per-target matrix, mocking approach, coverage target, and a
    manual-testing checklist for what automation cannot cover.
    """

    strategy_summary: str
    framework: str = "vitest"
    coverage_target_pct: int = 80
    matrix: list[TestMatrixEntry] = field(default_factory=list)
    mocking_strategy: str = ""
    manual_checklist: list[str] = field(default_factory=list)


@dataclass
class ValidationIssue:
    """Individual validation problem."""

    severity: str  # error | warning | info
    category: str  # syntax | logic | best-practice | performance
    file_path: str
    line: int | None = None
    message: str = ""
    suggestion: str = ""


@dataclass
class ValidationReport:
    """Output of validator_agent_v3 — quality gate results."""

    passed: bool
    issues: list[ValidationIssue]
    typescript_errors: int = 0
    eslint_warnings: int = 0
    react_violations: int = 0
    overall_score: float = 0.0  # 0.0 (fail) to 100.0 (perfect)


@dataclass
class MigrationMetrics:
    """Overall migration statistics."""

    files_migrated: int = 0
    lines_converted: int = 0
    components_created: int = 0
    hooks_generated: int = 0
    tests_written: int = 0
    total_tokens_used: int = 0
    duration_seconds: float = 0.0


@dataclass
class MigrationReport:
    """Output of report_agent — final summary and artifacts."""

    success: bool
    metrics: MigrationMetrics
    validation: ValidationReport
    output_files: list[str]
    next_steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class MigrationContext:
    """Hierarchical context container for token-optimized agent execution.

    Supports 4 levels of detail:
        Level 1: Metadata only (file names, structure)
        Level 2: + AST summaries
        Level 3: + Targeted source fragments
        Level 4: + Full source code
    """

    # Core project metadata (Level 1)
    project_summary: dict[str, Any] = field(default_factory=dict)
    dependency_graph: dict[str, DependencyNode] = field(default_factory=dict)

    # Analysis outputs (Level 1-2)
    risk_profile: RiskReport | None = None
    migration_plan: MigrationPlan | None = None
    component_manifest: list[Component] = field(default_factory=list)
    route_graph: list[Route] = field(default_factory=list)
    service_graph: list[Service] = field(default_factory=list)

    # AST summaries (Level 2)
    ast_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Source fragments (Level 3)
    source_fragments: dict[str, str] = field(default_factory=dict)

    # Full sources (Level 4)
    full_sources: dict[str, str] = field(default_factory=dict)

    def to_level_payload(self, level: ContextLevel) -> dict[str, Any]:
        """Project context down to specified level for token optimization."""
        payload: dict[str, Any] = {
            "project_summary": self.project_summary,
            "dependency_graph": {k: v.__dict__ for k, v in self.dependency_graph.items()},
        }

        if self.risk_profile:
            payload["risk_profile"] = {
                "overall_risk_score": self.risk_profile.overall_risk_score,
                "high_risks": [
                    r.description
                    for r in self.risk_profile.risks
                    if r.severity in ("critical", "high")
                ],
            }

        if self.migration_plan:
            payload["migration_plan"] = {
                "total_chunks": len(self.migration_plan.chunks),
                "execution_order": self.migration_plan.execution_order[:10],  # First 10
            }

        if level >= ContextLevel.AST_SUMMARIES and self.ast_summaries:
            payload["ast_summaries"] = self.ast_summaries

        if level >= ContextLevel.SOURCE_FRAGMENTS and self.source_fragments:
            payload["source_fragments"] = self.source_fragments

        if level >= ContextLevel.FULL_SOURCE and self.full_sources:
            payload["full_sources"] = self.full_sources

        return payload
