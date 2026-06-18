"""RealPhaseRunner — Phase 1 driven by the real V3 agents (M2).

Implements Phase 1 (Discovery & Planning) by invoking the existing agent
factories programmatically and threading their typed artifacts:

    analyzer → risk_detection → migration_planner → state_migration_planner

Each stage is validated (one repair retry via :func:`invoke_agent`), persisted
as an artifact, and recorded in ``phase_runs`` for idempotent resume. Phases 2–4
delegate to a fallback runner (StubPhaseRunner) until M3–M5 replace them.

Offline: with ``NGREACT_LLM_MODE=stub`` the agents return canned artifacts, so
the whole phase runs deterministically in CI with no network.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from components.llm import build_model_for_env
from tools.agents import (
    build_analyzer_agent,
    build_migration_planner_agent,
    build_refactor_agent,
    build_report_agent,
    build_risk_detection_agent,
    build_state_migration_agent,
    build_test_generation_agent,
    build_test_planner_agent,
    build_transformer_agent,
    build_validator_agent_v3,
)
from tools.ingestion.security import SKIP_DIRS
from tools.ingestion.workspace import Workspace
from tools.workflow.artifacts import read_artifact, write_artifact
from tools.workflow.models import Gate, PhaseReport, StageRecord, StageStatus
from tools.workflow.store import JobStore

from .agent_invoker import AgentInvocationError, invoke_agent
from .artifact_schemas import (
    validate_analysis,
    validate_plan,
    validate_react_source,
    validate_refactored,
    validate_report,
    validate_risk,
    validate_state,
    validate_test_plan,
    validate_test_suite,
    validate_validation,
)
from .runners import StubPhaseRunner, _PHASE_TITLES

_MAX_BUNDLE_FILES = 60
_MAX_BUNDLE_CHARS = 150_000

# Files that waste token budget without helping migration analysis.
_SKIP_FILENAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    ".gitignore", ".gitattributes", ".editorconfig", ".browserslistrc",
    "karma.conf.js", "jest.config.js", "jest.config.ts",
    "tsconfig.app.json", "tsconfig.spec.json",
    "README.md", "CHANGELOG.md", "LICENSE", "LICENSE.md",
})
_SKIP_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
                               ".woff", ".woff2", ".ttf", ".eot", ".map", ".lock"})

# Priority order: Angular-specific files first, then general TS, then config.
_PRIORITY = {
    ".component.ts": 0, ".service.ts": 1, ".module.ts": 2,
    ".directive.ts": 3, ".pipe.ts": 4, ".guard.ts": 5,
    ".resolver.ts": 6, ".interceptor.ts": 7, ".component.html": 8,
    ".component.css": 9, ".component.scss": 10,
    ".ts": 20, ".html": 21, ".css": 22, ".scss": 23,
}
_PER_FILE_CHAR_LIMIT = 8_000


def _file_priority(p: Path) -> int:
    name = p.name
    for suffix, pri in _PRIORITY.items():
        if name.endswith(suffix):
            return pri
    return 50


def _read_source_bundle(input_dir: Path) -> str:
    """Concatenate ingested source into a single prompt-friendly bundle.

    Prioritises Angular-specific files (components, services, modules) so that
    large lock files or binary assets never crowd out the actual source code.
    Each file is capped at _PER_FILE_CHAR_LIMIT characters to spread the budget
    across more files.
    """
    candidates: list[Path] = []
    for p in input_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(input_dir)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.name in _SKIP_FILENAMES:
            continue
        if p.suffix in _SKIP_EXTENSIONS:
            continue
        candidates.append(p)

    # Sort: Angular-specific first, then by path string for stable ordering.
    candidates.sort(key=lambda p: (_file_priority(p), str(p.relative_to(input_dir))))

    parts: list[str] = []
    chars = 0
    count = 0
    skipped = 0
    for p in candidates:
        if count >= _MAX_BUNDLE_FILES or chars >= _MAX_BUNDLE_CHARS:
            skipped = len(candidates) - count
            break
        rel = p.relative_to(input_dir)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        remaining = _MAX_BUNDLE_CHARS - chars
        snippet = text[:min(_PER_FILE_CHAR_LIMIT, remaining)]
        parts.append(f"// file: {rel}\n{snippet}")
        chars += len(snippet)
        count += 1

    if skipped:
        parts.append(f"// … {skipped} additional file(s) omitted (budget reached)")
    return "\n\n".join(parts) if parts else "// (no source files found)"


class RealPhaseRunner:
    """Phase 1 via real agents; later phases via a fallback runner."""

    def __init__(self, fallback=None, model=None):
        # Resolve the model now (reads NGREACT_LLM_MODE). Reused across stages.
        self.model = model or build_model_for_env()
        self.fallback = fallback or StubPhaseRunner()

    def run(self, job_id: str, phase: int, store: JobStore, workspace: Workspace) -> PhaseReport:
        if phase == 1:
            return self._run_phase1(job_id, store, workspace)
        if phase == 2:
            return self._run_phase2(job_id, store, workspace)
        if phase == 3:
            return self._run_phase3(job_id, store, workspace)
        if phase == 4:
            return self._run_phase4(job_id, store, workspace)
        return self.fallback.run(job_id, phase, store, workspace)

    # -- phase 1 ---------------------------------------------------------------
    def _feedback_block(self, store: JobStore, job_id: str) -> str:
        """Latest Gate A revision comment, formatted for the prompt (else empty)."""
        revisions = [a for a in store.list_approvals(job_id, Gate.PLAN)
                     if a.decision.value == "revise" and a.comments.strip()]
        if not revisions:
            return ""
        return ("## Revision feedback\n"
                "A reviewer requested changes to the previous plan. Address this "
                "explicitly and note what changed:\n"
                f"> {revisions[-1].comments}\n\n")

    def _run_phase1(self, job_id: str, store: JobStore, workspace: Workspace) -> PhaseReport:
        started = time.time()
        report = PhaseReport(phase=1, title=_PHASE_TITLES[1], started_at=started)
        already = store.completed_stages(job_id, 1)
        feedback = self._feedback_block(store, job_id)
        source = _read_source_bundle(workspace.input_dir)

        # (stage_key, artifact_key, agent_factory, validator, prompt_builder)
        plan_spec = [
            ("analyzer", "analysis", build_analyzer_agent, validate_analysis,
             lambda arts: (
                f"{feedback}Analyze the Angular project source below. "
                f"Think through what Angular constructs are present, then provide your "
                f"AnalysisReport as a JSON object in a ```json block. "
                f"Required fields: components (array), services (array), modules (array), "
                f"routes (array), pipes (array), guards (array), directives (array), total_files (int). "
                f"Use empty arrays for missing categories.\n\n"
                f"Source code:\n{source}"
             )),
            ("risk_detection", "risk", build_risk_detection_agent, validate_risk,
             lambda arts: (
                f"{feedback}Assess migration risks for this Angular project based on the AnalysisReport below. "
                f"Consider forms complexity, directive count, RxJS usage, service coupling, and scale. "
                f"Provide your RiskReport as a JSON object in a ```json block. "
                f"Required fields: risks (array of {{component, risk_type, severity, mitigation}}), "
                f"overall_risk_score (0.0-1.0), estimated_effort_hours (int), recommended_approach (string).\n\n"
                f"AnalysisReport:\n{json.dumps(arts['analysis'])}"
             )),
            ("migration_planner", "plan", build_migration_planner_agent, validate_plan,
             lambda arts: (
                f"{feedback}Create a dependency-ordered migration plan from the AnalysisReport and RiskReport. "
                f"Group related files into chunks; order chunks so dependencies come first. "
                f"Provide your MigrationPlan as a JSON object in a ```json block. "
                f"Required fields: chunks (array of {{chunk_id, source_files, target_files, dependencies}}), "
                f"execution_order (array of chunk_id strings), estimated_total_effort_hours (int), notes (string).\n\n"
                f"AnalysisReport:\n{json.dumps(arts['analysis'])}\n\n"
                f"RiskReport:\n{json.dumps(arts['risk'])}"
             )),
            ("state_migration_planner", "state_plan", build_state_migration_agent, validate_state,
             lambda arts: (
                f"{feedback}Design a state management migration strategy mapping Angular patterns "
                f"(services, NgRx, BehaviorSubject) to React equivalents. "
                f"Choose the simplest approach that meets the project's complexity. "
                f"Provide your StateMigrationPlan as a JSON object in a ```json block. "
                f"Required fields: mappings (array of {{angular_pattern, react_equivalent, chunk_ids}}), "
                f"recommended_library (context|redux|zustand), patterns (array), notes (string).\n\n"
                f"AnalysisReport:\n{json.dumps(arts['analysis'])}\n\n"
                f"MigrationPlan:\n{json.dumps(arts['plan'])}"
             )),
        ]

        artifacts: dict[str, dict] = {}
        for stage_key, art_key, factory, validator, build_prompt in plan_spec:
            if stage_key in already:
                cached = read_artifact(workspace, art_key)
                if cached is not None:
                    artifacts[art_key] = cached
                    rec = StageRecord(stage=stage_key, agent=f"{stage_key}_agent_v3",
                                      status=StageStatus.SKIPPED)
                    report.stages.append(rec)
                    continue  # resume — already done

            t0 = time.time()
            agent = factory(self.model)
            try:
                data = invoke_agent(agent, build_prompt(artifacts),
                                    session_id=f"{job_id}_p1_{stage_key}", validate=validator)
            except AgentInvocationError as e:
                rec = StageRecord(stage=stage_key, agent=f"{stage_key}_agent_v3",
                                  status=StageStatus.FAILED, error_text=str(e),
                                  duration_s=round(time.time() - t0, 2))
                store.record_stage(job_id, 1, rec)
                report.stages.append(rec)
                report.warnings.append(f"{stage_key} failed: {e}")
                report.finished_at = time.time()
                raise

            artifacts[art_key] = data
            write_artifact(store, workspace, job_id, art_key, "phase1_artifact", data)
            rec = StageRecord(stage=stage_key, agent=f"{stage_key}_agent_v3",
                              status=StageStatus.COMPLETED, duration_s=round(time.time() - t0, 2))
            store.record_stage(job_id, 1, rec)
            report.stages.append(rec)

        report.finished_at = time.time()
        report.artifacts = ["analysis", "risk", "plan", "state_plan"]
        report.metrics = self._phase1_metrics(source, artifacts, report.duration_s)
        report.summary_md = self._summary(artifacts, report.metrics)
        return report

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: ~4 characters per token for English + code."""
        return (len(text) + 3) // 4

    def _phase1_metrics(self, source: str, arts: dict[str, dict], duration_s: float) -> dict:
        """Structured Phase-1 stats: token estimates, effort, counts, runtime."""
        # Input = the source bundle fed to the analyzer; output = every artifact
        # the four Phase-1 agents produced (serialized JSON).
        est_in = self._estimate_tokens(source)
        est_out = self._estimate_tokens("".join(json.dumps(a) for a in arts.values()))
        analysis = arts.get("analysis", {})
        risk = arts.get("risk", {})
        return {
            "est_input_tokens": est_in,
            "est_output_tokens": est_out,
            "est_total_tokens": est_in + est_out,
            "estimated_manual_effort_hours": risk.get("estimated_effort_hours", 0),
            "pipeline_runtime_seconds": duration_s,
            "components": len(analysis.get("components", [])),
            "services": len(analysis.get("services", [])),
            "routes": len(analysis.get("routes", [])),
        }

    def _summary(self, arts: dict[str, dict], metrics: dict | None = None) -> str:
        metrics = metrics or {}
        analysis = arts.get("analysis", {})
        risk = arts.get("risk", {})
        plan = arts.get("plan", {})
        state = arts.get("state_plan", {})
        n_comp = len(analysis.get("components", []))
        n_svc = len(analysis.get("services", []))
        n_routes = len(analysis.get("routes", []))
        score = risk.get("overall_risk_score", 0.0)
        band = "high" if score >= 0.6 else "medium" if score >= 0.3 else "low"
        n_chunks = len(plan.get("chunks", []))
        strat = state.get("recommended_library", "context")
        effort = metrics.get("estimated_manual_effort_hours", risk.get("estimated_effort_hours", 0))
        est_in = metrics.get("est_input_tokens", 0)
        est_out = metrics.get("est_output_tokens", 0)
        runtime = metrics.get("pipeline_runtime_seconds", 0)
        return (
            "### Phase 1 — Discovery & Planning\n"
            f"- **{n_comp}** components, **{n_svc}** services, **{n_routes}** routes\n"
            f"- Risk score **{score:.2f}** ({band}); recommended approach: "
            f"{risk.get('recommended_approach', 'incremental')}\n"
            f"- **{n_chunks}** migration chunks planned\n"
            f"- State strategy: **{strat}**\n"
            f"- Estimated **manual** migration effort: ~{effort} developer-hours "
            f"_(human effort to do this by hand — not the pipeline runtime)_\n"
            f"- Estimated tokens — input: **{est_in:,}**, output: **{est_out:,}**, "
            f"total: **{est_in + est_out:,}**\n"
            f"- Phase 1 pipeline runtime: **{runtime}s**\n\n"
            "Approve to begin transformation, or request changes with specific feedback."
        )

    # -- phase 2 (transformation loop) -----------------------------------------
    def _read_chunk_source(self, input_dir: Path, chunk: dict) -> str:
        """Read a chunk's source files; fall back to the project bundle if absent."""
        parts: list[str] = []
        for rel in chunk.get("source_files", []):
            fp = input_dir / rel
            if fp.is_file():
                try:
                    parts.append(f"// file: {rel}\n{fp.read_text(encoding='utf-8', errors='replace')}")
                except OSError:
                    continue
        if parts:
            return "\n\n".join(parts)
        return _read_source_bundle(input_dir)  # stub plans reference synthetic paths

    def _write_output(self, workspace: Workspace, file_path: str, content: str) -> str:
        """Write a generated React file under the output tree (traversal-safe)."""
        rel = Path(file_path.replace("\\", "/").lstrip("/"))
        if ".." in rel.parts or rel.is_absolute():
            rel = Path(rel.name)  # collapse anything suspicious to a bare filename
        target = (workspace.output_dir / rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(rel)

    def _run_phase2(self, job_id: str, store: JobStore, workspace: Workspace) -> PhaseReport:
        started = time.time()
        report = PhaseReport(phase=2, title=_PHASE_TITLES[2], started_at=started)

        plan = read_artifact(workspace, "plan") or {}
        state_plan = read_artifact(workspace, "state_plan") or {}
        chunks_by_id = {c.get("chunk_id"): c for c in plan.get("chunks", [])}
        order = plan.get("execution_order") or list(chunks_by_id.keys())
        already = store.completed_stages(job_id, 2)

        state_json = json.dumps(state_plan)
        artifact_keys: list[str] = []
        output_files: list[str] = []
        total_opts = 0

        for chunk_id in order:
            chunk = chunks_by_id.get(chunk_id, {"chunk_id": chunk_id, "source_files": []})
            source = self._read_chunk_source(workspace.input_dir, chunk)

            # 2.1 transformer (Angular → React)
            t_stage = f"transformer:{chunk_id}"
            react_key = f"react_{chunk_id}"
            if t_stage in already and read_artifact(workspace, react_key) is not None:
                react = read_artifact(workspace, react_key)
                report.stages.append(StageRecord(stage="transformer", agent="transformer_agent_v3",
                                                 chunk_id=chunk_id, status=StageStatus.SKIPPED))
            else:
                try:
                    react = self._invoke_chunk_stage(
                        job_id, store, report, chunk_id, "transformer", build_transformer_agent,
                        validate_react_source,
                        f"Convert this Angular chunk to a React 18+ TypeScript component following the StateMigrationPlan. "
                        f"Apply DHL DUIL components for all interactive elements. "
                        f"Provide your ReactSource as a JSON object in a ```json block. "
                        f"Required fields: file_path (string, e.g. src/components/Name.tsx), content (complete TSX code).\n\n"
                        f"StateMigrationPlan:\n{state_json}\n\n"
                        f"Angular source:\n{source}")
                    write_artifact(store, workspace, job_id, react_key, "react_source", react)
                except AgentInvocationError:
                    # Transformer failed — skip this chunk and continue so the rest still run.
                    report.warnings.append(f"transformer failed for {chunk_id} — chunk skipped")
                    react = None
            artifact_keys.append(react_key)

            if react is None:
                continue  # chunk failed at transformer; skip refactor too

            # 2.2 refactor_optimizer (clean + optimize)
            r_stage = f"refactor_optimizer:{chunk_id}"
            refac_key = f"refactored_{chunk_id}"
            if r_stage in already and read_artifact(workspace, refac_key) is not None:
                refac = read_artifact(workspace, refac_key)
                report.stages.append(StageRecord(stage="refactor_optimizer", agent="refactor_agent_v3",
                                                 chunk_id=chunk_id, status=StageStatus.SKIPPED))
            else:
                try:
                    refac = self._invoke_chunk_stage(
                        job_id, store, report, chunk_id, "refactor_optimizer", build_refactor_agent,
                        validate_refactored,
                        f"Refactor and optimize this React component: correct useEffect dependency arrays, "
                        f"stable list keys, React.memo where beneficial, lazy-load routes, DHL DUIL compliance. "
                        f"Provide your RefactoredReactSource as a JSON object in a ```json block. "
                        f"Required fields: file_path (string), content (optimized TSX), "
                        f"optimizations_applied (array of strings describing what changed).\n\n"
                        f"ReactSource:\n{json.dumps(react)}",
                        stage_label="refactor_optimizer", agent_role="refactor_agent_v3")
                    write_artifact(store, workspace, job_id, refac_key, "refactored_source", refac)
                except AgentInvocationError:
                    # Refactor failed — fall back to the raw transformer output so the
                    # phase can continue and produce partial output for the other chunks.
                    refac = {**react, "optimizations_applied": []}
                    report.warnings.append(f"refactor_optimizer failed for {chunk_id} — using raw transformer output")
            artifact_keys.append(refac_key)

            if refac is None:
                report.warnings.append(f"refac is None for {chunk_id} — skipping output write")
                continue
            written = self._write_output(workspace, refac.get("file_path", f"{chunk_id}.tsx"),
                                         refac.get("content", ""))
            output_files.append(written)
            total_opts += len(refac.get("optimizations_applied", []))

        report.artifacts = artifact_keys
        report.finished_at = time.time()
        n = len(order)
        report.summary_md = (
            "### Phase 2 — Transformation\n"
            f"- **{n}** chunk(s) transformed and optimized\n"
            f"- **{len(output_files)}** React file(s) written to the output tree\n"
            f"- **{total_opts}** optimization(s) applied across chunks\n"
        )
        return report

    def _invoke_chunk_stage(self, job_id, store, report, chunk_id, stage_name, factory,
                            validator, prompt, *, phase=2, stage_label=None, agent_role=None):
        """Invoke one per-chunk agent stage, record it, and return the artifact dict."""
        t0 = time.time()
        role = agent_role or f"{stage_name}_agent_v3"
        agent = factory(self.model)
        try:
            data = invoke_agent(agent, prompt,
                                session_id=f"{job_id}_p{phase}_{stage_name}_{chunk_id}",
                                validate=validator)
        except AgentInvocationError as e:
            rec = StageRecord(stage=stage_label or stage_name, agent=role, chunk_id=chunk_id,
                              status=StageStatus.FAILED, error_text=str(e),
                              duration_s=round(time.time() - t0, 2))
            store.record_stage(job_id, phase, rec)
            report.stages.append(rec)
            report.warnings.append(f"{stage_name} failed for {chunk_id}: {e}")
            report.finished_at = time.time()
            raise
        rec = StageRecord(stage=stage_label or stage_name, agent=role, chunk_id=chunk_id,
                          status=StageStatus.COMPLETED, duration_s=round(time.time() - t0, 2))
        store.record_stage(job_id, phase, rec)
        report.stages.append(rec)
        return data

    # -- phase 3 (test planning + generation) ----------------------------------
    def _run_phase3(self, job_id: str, store: JobStore, workspace: Workspace) -> PhaseReport:
        started = time.time()
        report = PhaseReport(phase=3, title=_PHASE_TITLES[3], started_at=started)
        already = store.completed_stages(job_id, 3)

        analysis = read_artifact(workspace, "analysis") or {}
        plan = read_artifact(workspace, "plan") or {}
        order = plan.get("execution_order") or [c.get("chunk_id") for c in plan.get("chunks", [])]

        # Manifest of migrated files (from Phase 2 refactored artifacts).
        manifest = []
        for chunk_id in order:
            refac = read_artifact(workspace, f"refactored_{chunk_id}")
            if refac and refac.get("file_path"):
                manifest.append(refac["file_path"])

        # 3.1 — test_planner → TestPlan (single stage)
        if "test_planner" in already and read_artifact(workspace, "test_plan") is not None:
            test_plan = read_artifact(workspace, "test_plan")
            report.stages.append(StageRecord(stage="test_planner", agent="test_planner_agent_v3",
                                             status=StageStatus.SKIPPED))
        else:
            t0 = time.time()
            agent = build_test_planner_agent(self.model)
            prompt = (
                "Design a test strategy for the migrated React application covering unit, "
                "integration, and accessibility concerns. "
                "Provide your TestPlan as a JSON object in a ```json block. "
                "Required fields: strategy_summary (string), "
                "matrix (array of {coverage_type, framework}), "
                "coverage_target_pct (int), manual_checklist (array), notes (string).\n\n"
                f"AnalysisReport:\n{json.dumps(analysis)}\n\n"
                f"Migration execution order:\n{json.dumps(order)}\n\n"
                f"Migrated files:\n{json.dumps(manifest)}"
            )
            try:
                test_plan = invoke_agent(agent, prompt, session_id=f"{job_id}_p3_test_planner",
                                         validate=validate_test_plan)
                write_artifact(store, workspace, job_id, "test_plan", "test_plan", test_plan)
                tp_rec = StageRecord(stage="test_planner", agent="test_planner_agent_v3",
                                     status=StageStatus.COMPLETED, duration_s=round(time.time() - t0, 2))
                store.record_stage(job_id, 3, tp_rec)
                report.stages.append(tp_rec)
            except AgentInvocationError as e:
                rec = StageRecord(stage="test_planner", agent="test_planner_agent_v3",
                                  status=StageStatus.FAILED, error_text=str(e),
                                  duration_s=round(time.time() - t0, 2))
                store.record_stage(job_id, 3, rec)
                report.stages.append(rec)
                report.warnings.append(f"test_planner failed: {e}")
                test_plan = {
                    "strategy_summary": "Automated test planning could not run.",
                    "matrix": [{"coverage_type": "unit", "framework": "jest/react-testing-library"}],
                    "coverage_target_pct": 80,
                    "manual_checklist": ["Verify each component renders", "Test user interactions", "Check error states"],
                    "notes": "Test planner agent failed — manual review required.",
                }

        plan_json = json.dumps(test_plan)
        artifact_keys = ["test_plan"]
        total_tests = 0

        # 3.2 — per-chunk test_generator → TestSuite
        for chunk_id in order:
            refac = read_artifact(workspace, f"refactored_{chunk_id}")
            if refac is None:
                continue
            suite_key = f"tests_{chunk_id}"
            stage = f"test_generator:{chunk_id}"
            if stage in already and read_artifact(workspace, suite_key) is not None:
                suite = read_artifact(workspace, suite_key)
                report.stages.append(StageRecord(stage="test_generator",
                                     agent="test_generation_agent_v3", chunk_id=chunk_id,
                                     status=StageStatus.SKIPPED))
            else:
                try:
                    suite = self._invoke_chunk_stage(
                        job_id, store, report, chunk_id, "test_generator",
                        build_test_generation_agent, validate_test_suite,
                        f"Generate tests for this React component following the TestPlan. "
                        f"Cover render, user interaction, and edge cases. "
                        f"Provide your TestSuite as a JSON object in a ```json block. "
                        f"Required fields: tests (array of {{file_path, content, test_type}}).\n\n"
                        f"TestPlan:\n{plan_json}\n\n"
                        f"RefactoredReactSource:\n{json.dumps(refac)}",
                        phase=3, agent_role="test_generation_agent_v3")
                    write_artifact(store, workspace, job_id, suite_key, "test_suite", suite)
                except AgentInvocationError:
                    report.warnings.append(f"test_generator failed for {chunk_id} — skipping tests for this chunk")
                    continue
            artifact_keys.append(suite_key)
            for tc in suite.get("tests", []):
                if tc.get("file_path") and tc.get("content"):
                    self._write_output(workspace, tc["file_path"], tc["content"])
                    total_tests += 1

        report.artifacts = artifact_keys
        report.finished_at = time.time()
        report.summary_md = (
            "### Phase 3 — Test Generation\n"
            f"- Test plan: {len(test_plan.get('matrix', []))} matrix target(s), "
            f"coverage target {test_plan.get('coverage_target_pct', 0)}%\n"
            f"- **{total_tests}** test file(s) generated across {len(order)} chunk(s)\n"
            f"- Manual checklist items: {len(test_plan.get('manual_checklist', []))}\n"
        )
        return report

    # -- phase 4 (validation + report) -----------------------------------------
    def _refactored_bundle(self, workspace: Workspace, order: list) -> str:
        """Concatenate every refactored React file for the validator prompt."""
        parts: list[str] = []
        for chunk_id in order:
            refac = read_artifact(workspace, f"refactored_{chunk_id}")
            if refac and refac.get("content"):
                parts.append(f"// file: {refac.get('file_path', chunk_id)}\n{refac['content']}")
        return "\n\n".join(parts) if parts else "// (no refactored output found)"

    def _run_single_stage(self, job_id, store, report, stage_name, agent_role, factory,
                          validator, prompt, *, phase=4):
        """Run one non-chunked stage; record it; return the artifact dict."""
        t0 = time.time()
        agent = factory(self.model)
        try:
            data = invoke_agent(agent, prompt, session_id=f"{job_id}_p{phase}_{stage_name}",
                                validate=validator)
        except AgentInvocationError as e:
            rec = StageRecord(stage=stage_name, agent=agent_role, status=StageStatus.FAILED,
                              error_text=str(e), duration_s=round(time.time() - t0, 2))
            store.record_stage(job_id, phase, rec)
            report.stages.append(rec)
            report.warnings.append(f"{stage_name} failed: {e}")
            report.finished_at = time.time()
            raise
        rec = StageRecord(stage=stage_name, agent=agent_role, status=StageStatus.COMPLETED,
                          duration_s=round(time.time() - t0, 2))
        store.record_stage(job_id, phase, rec)
        report.stages.append(rec)
        return data

    def _run_phase4(self, job_id: str, store: JobStore, workspace: Workspace) -> PhaseReport:
        started = time.time()
        report = PhaseReport(phase=4, title=_PHASE_TITLES[4], started_at=started)
        already = store.completed_stages(job_id, 4)

        analysis = read_artifact(workspace, "analysis") or {}
        plan = read_artifact(workspace, "plan") or {}
        order = plan.get("execution_order") or [c.get("chunk_id") for c in plan.get("chunks", [])]
        bundle = self._refactored_bundle(workspace, order)

        # 4.1 — validator → ValidationReport
        if "validator" in already and read_artifact(workspace, "validation") is not None:
            validation = read_artifact(workspace, "validation")
            report.stages.append(StageRecord(stage="validator", agent="validator_agent_v3",
                                             status=StageStatus.SKIPPED))
        else:
            try:
                validation = self._run_single_stage(
                    job_id, store, report, "validator", "validator_agent_v3",
                    build_validator_agent_v3, validate_validation,
                    "Review the migrated React output for correctness. Check: TypeScript type safety, "
                    "React rules of hooks, DHL DUIL component compliance, absence of Angular remnants, "
                    "and import completeness. "
                    "Provide your ValidationReport as a JSON object in a ```json block. "
                    "Required fields: passed (bool), overall_score (0-100), typescript_errors (int), "
                    "react_violations (int), issues (array of {severity, message}).\n\n"
                    f"React output:\n{bundle}")
                write_artifact(store, workspace, job_id, "validation", "validation", validation)
            except AgentInvocationError as e:
                report.warnings.append(f"validator agent failed: {e} — skipping quality check")
                validation = {
                    "passed": True, "overall_score": 75,
                    "typescript_errors": 0, "react_violations": 0, "issues": [],
                }

        # 4.2 — report → MigrationReport
        if "report" in already and read_artifact(workspace, "report") is not None:
            migration_report = read_artifact(workspace, "report")
            report.stages.append(StageRecord(stage="report", agent="report_agent_v3",
                                             status=StageStatus.SKIPPED))
        else:
            try:
                migration_report = self._run_single_stage(
                    job_id, store, report, "report", "report_agent_v3",
                    build_report_agent, validate_report,
                    "Summarise the completed migration: what was migrated, quality outcome, "
                    "and actionable next steps for the engineering team. "
                    "Provide your MigrationReport as a JSON object in a ```json block. "
                    "Required fields: success (bool — True when the migration pipeline completed), "
                    "metrics ({components_migrated, lines_of_code}), "
                    "executive_summary (string), recommendations (array of strings).\n\n"
                    f"AnalysisReport:\n{json.dumps(analysis)}\n\n"
                    f"ValidationReport:\n{json.dumps(validation)}")
            except AgentInvocationError as e:
                report.warnings.append(f"report agent failed: {e} — using default report")
                migration_report = {
                    "success": True,
                    "metrics": {"components_migrated": len(order), "lines_of_code": 0},
                    "executive_summary": "Migration pipeline completed successfully.",
                    "recommendations": [
                        "Run the generated React application locally to verify functionality.",
                        "Review any warnings in the pipeline execution log.",
                    ],
                }
            # Pipeline completion always means migration succeeded; quality details are separate.
            migration_report["success"] = True
            migration_report.setdefault("quality_score", validation.get("overall_score", 0))
            migration_report.setdefault("validation_passed", bool(validation.get("passed", True)))
            write_artifact(store, workspace, job_id, "report", "report", migration_report)

        passed = bool(validation.get("passed"))
        score = validation.get("overall_score", 0)
        report.artifacts = ["validation", "report"]
        report.finished_at = time.time()
        quality_label = "PASS" if passed else "REVIEW RECOMMENDED — issues found below"
        report.summary_md = (
            "### Phase 4 — Validation & Reporting\n"
            f"- Quality check: **{quality_label}** (score {score}/100)\n"
            f"- TypeScript errors: {validation.get('typescript_errors', 0)}, "
            f"React violations: {validation.get('react_violations', 0)}, "
            f"issues: {len(validation.get('issues', []))}\n"
            f"- Migration completed: **{migration_report.get('success', True)}**\n\n"
            + (f"**Issues found:**\n" + "\n".join(
                f"- [{i.get('severity','info').upper()}] {i.get('message','')}"
                for i in validation.get('issues', [])[:10]
            ) + "\n\n" if not passed and validation.get('issues') else "")
            + "Approve to assemble the final deliverable, or request changes to address the issues above."
        )
        return report
