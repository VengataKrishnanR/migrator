# V3 Build Status

Tracks progress against `docs/V3_ARCHITECTURE_PLAN.md`. Update this at the end of
every milestone so the next session/model can resume without re-deriving context.

## Legend
✅ done & tested · 🚧 in progress · ⬜ not started

---

## M0 — Baseline freeze · 🚧 (partial)
- ✅ `scripts/ci.sh` — offline test entrypoint (stub mode, no network).
- ⬜ **Commit the V2 baseline + tag `v2-baseline`.** Deferred: the working tree has
  ~88 uncommitted changes (the V2 refactor + component deletions). This is a
  user decision — committing someone's uncommitted work, including `.env` and
  `.adk/session.db`, shouldn't happen unprompted. Run when ready:
  ```
  git add -A && git commit -m "chore: V2 baseline before V3 build" && git tag v2-baseline
  ```
- ⬜ Golden quick-mode tests (snapshot paste→transform→refactor→validate with
  StubLlm). Pending — needs the existing direct-mode path captured; do alongside M2.

## M1 — Job model, persistence, ingestion, API skeleton · ✅
New code:
- `tools/workflow/` — `models.py` (JobState + all §7 models), `state_machine.py`
  (MigrationJob, TRANSITIONS, audit), `store.py` (SQLite: jobs, phase_runs,
  artifacts, approvals, audit_events, token_usage).
- `tools/ingestion/` — `adapters.py` (paste/files/zip/git), `security.py`
  (zip-slip, symlink, size, count, nesting guards), `profiler.py` (Angular
  detection — filename + content signals), `workspace.py`.
- `server/` — `service.py` (JobService: create/run/resume/approve, idempotent),
  `runners.py` (PhaseRunner protocol + StubPhaseRunner), `app.py` (FastAPI:
  jobs CRUD, events SSE, artifacts, approvals, cancel, resume, health),
  `config.py`.

Tests (34 passing): `tests/test_v3_workflow.py`, `test_v3_ingestion.py`,
`test_v3_service.py`, `test_v3_api.py`. Covers illegal transitions, audit,
crash-resume, zip-slip/oversize/non-Angular rejection, gate parking + bounded
revisions, and the HTTP approval round-trip.

**Acceptance met:** create from paste/files/zip; workspace materialized; zip-slip
& non-Angular rejected with failure; stubbed job reaches COMPLETED; restart-resume
passes. (Git ingestion adapter is implemented; its live test needs a local bare-repo
fixture — add in M5 alongside git *integration*.)

## M2 — Phase 1 runner + Gate A · ✅
New code:
- `server/agent_invoker.py` — programmatic ADK invocation (`InMemoryRunner` →
  collect final text → `extract_json` → validate), with **one repair retry** on
  parse/schema failure.
- `server/artifact_schemas.py` — shape validators (analysis/risk/plan/state).
- `server/phase_runner.py` — `RealPhaseRunner`: Phase 1 = analyzer → risk →
  migration_planner → state_migration_planner, threading typed artifacts
  (`analysis`/`risk`/`plan`/`state_plan`), idempotent resume, `Phase1Report` with
  a human summary. Phases 2–4 delegate to `StubPhaseRunner` (fallback).
- `tools/workflow/artifacts.py` — shared artifact read/write (service + runner).
- `tools/workflow/store.py` — added `clear_phase()` so a Gate-A **revise** re-runs
  Phase 1 (vs. crash-resume which skips completed stages).
- `server/__init__.py` — `build_default_runner()` (lazy, keeps core importable
  without google-adk). `server/app.py` now uses the real runner.
- Prompts: `## Revision feedback` section appended to the four Phase-1 agent prompts.

Tests (8, `tests/test_v3_phase1.py`): JSON extraction (fenced/bare/none),
validator rejection, full Phase-1 run produces all four artifacts + 4 completed
stages, Gate-A approve→Gate-B, **revise re-runs Phase 1** (stages repopulated),
and auto-gate full run → COMPLETED. Total V3 suite: **42 passing**.

**Acceptance met:** with StubLlm a fixture project produces a Phase-1 report and
parks at `AWAITING_PLAN_APPROVAL`; approve → phase 2; revise (with comments)
re-runs Phase 1 and records the revision; all decisions in `audit_events`.
*Live Apigee smoke test* (`docs/SMOKE.md`) — pending, run once before release.

**Env note:** under WSL the Windows `.venv` `python.exe` does NOT inherit shell
env vars (e.g. `NGREACT_LLM_MODE`). Tests set it via `monkeypatch.setenv`
(in-process `os.environ`), which works. For CLI runs, set it inside Python or via
`WSLENV`. `.env` currently pins `NGREACT_LLM_MODE=openai`.

## M3 — Phase 2 transformation loop · ✅
New code (all in `server/phase_runner.py`):
- `_run_phase2()` — per-chunk loop over `plan.execution_order`: transformer →
  refactor_optimizer, threading the StateMigrationPlan and each chunk's source.
- Per-chunk checkpointing: stage records keyed `transformer:<chunk_id>` /
  `refactor_optimizer:<chunk_id>`; `_invoke_chunk_stage` records + resumes each.
- Generated React written to `workspace.output_dir` (traversal-safe `_write_output`);
  per-chunk `react_<id>` / `refactored_<id>` artifacts persisted; `Phase2Report`
  summarizes chunks/files/optimizations.
- `server/artifact_schemas.py` — `validate_react_source`, `validate_refactored`.
- Prompts: optimization checklist appended to `refactor_agent.md`; shared
  `tools/agents/prompts/_duil_fragment.md` (canonical DUIL mapping, defined once).

Tests (2, `tests/test_v3_phase2.py`): full run writes `.tsx` output + per-chunk
artifacts + chunk-keyed stage records; **idempotent resume** (re-running Phase 2
yields all-SKIPPED stages). Total V3 suite: **44 passing**.

**Acceptance met:** multi-chunk fixture migrates end-to-end with stub; per-chunk
checkpoints enable chunk-level resume; Phase2Report lists files + optimizations.
(Server-kill-mid-loop resume is covered structurally by the chunk-keyed
idempotency test; the M1 process-restart-resume test already proves DB reload.)

## M4 — Phase 3 test generation (test_planner agent) · ✅
- `test_planner` agent (factory + prompt + role marker), StubLlm canned `TestPlan`
  + dispatcher, registered in `tools/agents/__init__.py` — all already present.
- Wired `_run_phase3()` into `RealPhaseRunner.run()` (route `phase==3`); added the
  missing imports (`build_test_planner_agent`, `build_test_generation_agent`,
  `validate_test_plan`, `validate_test_suite`); fixed a double-append stage bug.
- `_run_phase3`: stage 3.1 test_planner (TestPlan from analysis + plan + Phase-2
  file manifest), stage 3.2 per-chunk test_generator → test files written to the
  output tree; `Phase3Report` summary.
- Tests (2, `tests/test_v3_phase3.py`): TestPlan + per-chunk suites + `*.test.tsx`
  written, stage records, idempotent resume. **46 passing.**

## M5 — Phase 4: validation, report, Gate B, integration · ✅
- `_run_phase4()` in `RealPhaseRunner`: stage 4.1 validator → `ValidationReport`
  over the concatenated refactored output; stage 4.2 report → `MigrationReport`;
  `Phase4Report` summary. Routed `phase==4`.
- `validate_validation` + `validate_report` schemas added.
- **Gate B** (`AWAITING_FINAL_APPROVAL`) parks before integration — verified by
  `test_gate_b_parks_then_approves`.
- **Integration**: `JobService._integrate()` assembles `deliverable.zip` from the
  output tree (replaces the M1 no-op) and records an `integration` artifact. Runs
  only after Gate B approval (enforced by the state flow).
- Tests (3, `tests/test_v3_phase4.py`): validation+report artifacts, deliverable
  zip, Gate B park→approve, idempotent resume. **49 passing.**
- **Opt-in remaining:** git *push* of the deliverable (`options.target == "git"`).
  Scaffolded/documented; the zip deliverable is the tested default. Pushing to a
  real remote needs credentials + provider adapter — deferred to M6.

## M6 — Enterprise hardening (auth, secrets, Postgres, resilience, git push) · 🚧
**Delivered & tested:**
- **API-key authentication** — `AUTH_MODE=apikey` + `NGREACT_API_KEY` gate every
  `/api/*` call (except `/api/health`) via `X-API-Key` or `Authorization: Bearer`.
  Static UI assets stay open. Middleware in `server/app.py`; `auth_mode`/`api_key`
  in `server/config.py`. Tests (6, `tests/test_v3_auth.py`): health open, protected
  401 without key, X-API-Key + Bearer accepted, wrong key rejected, UI open.
  **55 passing.**

**Deferred (need external infra — documented, not built):**
- **OIDC auth** (`AUTH_MODE=oidc`): needs a real IdP (Azure AD/Okta). The seam
  exists (`auth_mode` switch + middleware); wire an OIDC validator when an IdP is
  available.
- **Postgres store**: `JobStore` is SQLite (`DATABASE_URL` reserved). Swap requires
  a DB-agnostic store layer + a running Postgres; defer until deployment target set.
- **Git push of the deliverable** (`options.target == "git"`): integration assembles
  the zip today. Pushing needs credentials + a provider adapter (GitHub/GitLab/ADO)
  and can't be tested offline safely. Local-commit scaffold is the next concrete step.
- **Resilience**: LLM retries (rest_llm) + job resume (M1) already exist; a global
  request exception handler + circuit-breaker around the gateway are the remaining items.

### UI ↔ pipeline (gate fix)
The custom UI (`ui/`) now drives the **gated JobService pipeline** via `/api/jobs`:
create → Phase 1 → **parks at Gate A** → approve → Phases 2–4 → **parks at Gate B**
→ approve → integrate → deliverable. This replaces the earlier gateless
conversational facade (which ran all stages in one shot — the "went straight to
transforming" bug). Added `GET /api/jobs/{id}/artifacts/{key}` so the UI renders
gate reports. New `ui/index.html` + `ui/app.js` + gate/pipeline CSS.

---

## How to run
```
bash scripts/ci.sh                       # full offline suite
.venv/Scripts/python.exe -m uvicorn server.app:app --reload   # run the API (Windows venv under WSL)
```

## Key design invariants (do not regress)
- **Control flow is code, not prompts.** Order/retries/gates/resume live in
  `JobService` + `MigrationJob`. Agents decide content only.
- **Runners must be idempotent** — consult `store.completed_stages` and skip done
  work, or crash-resume breaks.
- **Integration (git push / zip) only after Gate B**, enforced in code; never
  commit to the base branch.
- Every state change goes through `MigrationJob.transition()` → writes an audit row.
