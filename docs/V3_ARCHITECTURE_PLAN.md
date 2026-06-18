# NgReact V3 — Enterprise Migration Platform: Architecture & Build Plan

> **Purpose of this document.** This is a complete, self-contained build specification.
> It was produced by a planning model; a separate build model will implement it.
> Every section is written so the builder does not need to re-derive intent.
> Where a decision was open, a **recommended default** is stated and marked `DECISION`.

---

## 0. Executive summary

V3 restructures the existing 9-agent V2 pipeline into a **4-phase, gate-controlled,
deterministically orchestrated migration platform**:

| Phase | Name | Agents | Output | Gate after |
|---|---|---|---|---|
| 1 | Discovery & Planning | analyzer, risk_detection, migration_planner, state_migration_planner | `Phase1Report` | **Gate A** — human approves the migration plan |
| 2 | Transformation | transformer, refactor_optimizer | `Phase2Report` | none (auto-continue) |
| 3 | Test Generation | test_planner, test_generator | `Phase3Report` | none (auto-continue) |
| 4 | Validation & Integration | validator, report_agent + deterministic IntegrationService | `Phase4Report` + `MigrationReport` | **Gate B** — human approves before any output is delivered/pushed |

The four headline changes from V2:

1. **Deterministic orchestration.** The pipeline sequence moves out of the root-agent
   prompt (`prompts/v2_root_agent.md`, which today *asks* the LLM to "call each tool
   exactly once") into a Python **state machine** (`MigrationJob`). Agents are invoked
   programmatically per stage. The LLM decides *content*, never *control flow*.
2. **Human-in-the-loop gates** with persisted approval records, audit trail, and
   revise/reject feedback loops.
3. **Universal ingestion and integration.** Input: paste, file upload(s), zip, or git
   repository. Output: on-screen, zip download, or **git branch + push** (never to the
   base branch), optional PR creation.
4. **Provider-agnostic LLM layer**, first-class for both the **DHL GenAI Gateway
   (Apigee)** and direct vendor APIs, selected by config — no code change to switch.

---

## 1. Current state assessment (what exists, what to reuse)

Repo: ADK-based agent (`google-adk>=2.1.0`), Python 3.13, single entry `agent.py`.

### Reuse as-is or with light changes
| Asset | Location | Verdict |
|---|---|---|
| 9 sub-agent factories + prompts | `tools/agents/*.py`, `tools/agents/prompts/*.md` | **Reuse.** Regroup into phases; prompts get additive edits (report sections, feedback-revision input). |
| Typed artifacts | `tools/pipeline/models.py` | **Reuse + extend** (new models in §7). |
| Hierarchical context engine (L1–L4) | `tools/pipeline/context_engine.py` | **Reuse unchanged.** |
| Chunking | `tools/pipeline/chunking.py` | **Reuse unchanged.** |
| Cache | `tools/pipeline/cache.py` | **Reuse**; key by content hash (zip/paste have no stable path). |
| LLM layer (stub / google-ai / apigee modes) | `components/llm/*` (`build_model_for_env`, `ApigeeSettings`, `models_registry.py`, `models.{prod,test}.yaml`) | **Reuse.** Already supports Apigee env-specific proxy URLs (`APIGEE_PROXY_URL_<ENV>`), Azure + Vertex deployments via gateway. Formalize per-agent routing (§9). |
| Logging + tracing | `components/logging`, `components/tracing.py` | **Reuse**; extend with per-phase metrics. |
| DHL DUIL standard (`@dhl-official/react-library`) | embedded in prompts | **Reuse**; move the mapping table into a shared prompt fragment included by transformer/refactor/validator prompts so it is defined once. |
| Stub LLM | `components/llm/stub_llm.py` | **Reuse** — backbone of the regression suite (§13). |

### Gaps V3 must fill
- No job/workflow persistence (only `.adk/session.db` from ADK web).
- Orchestration is prompt-obedience-based → non-deterministic, no resume.
- No approval mechanism, no audit log.
- No ingestion layer: zip, multi-file upload, git clone all missing. (`run_ui.py` +
  custom UI were deleted in the working tree; only `ui/app.js` survives, orphaned.)
- No integration layer: no zip export, no git branch/commit/push, no PR creation.
- Tests: one system test file; no contract tests, no golden artifacts.
- No authn/z, no rate limiting on a public API surface.

### Pre-work (M0, see §12)
The working tree has large uncommitted changes (V2 refactor; deleted `memory/`,
`postgres/`, `qdrant/`, `security/` components, deleted `run_ui.py`). **Commit the V2
baseline first** so V3 work has a clean diff base and the regression suite has a
reference point.

---

## 2. Target architecture overview

```
                    ┌────────────────────────────────────────────────────────────┐
                    │                      FastAPI server  (server/)             │
                    │                                                            │
 UI (paste/upload/  │  REST /api/*            SSE /api/jobs/{id}/events          │
 zip/git + approve) │     │                                                      │
 ───────────────────┼────►│                                                      │
                    │     ▼                                                      │
                    │  JobService ──► IngestionService (paste|files|zip|git)     │
                    │     │                  └─► Workspace  jobs/<id>/input      │
                    │     ▼                                                      │
                    │  MigrationJob state machine (deterministic)                │
                    │     │                                                      │
                    │     ├─ Phase 1 runner ─► [analyzer → risk → planner →      │
                    │     │                     state_planner]  ─► Phase1Report  │
                    │     ├─ GATE A (ApprovalService: approve/revise/reject)     │
                    │     ├─ Phase 2 runner ─► per-chunk [transformer →          │
                    │     │                     refactor_optimizer] ─► Phase2Rpt │
                    │     ├─ Phase 3 runner ─► [test_planner → per-chunk         │
                    │     │                     test_generator]   ─► Phase3Rpt   │
                    │     ├─ Phase 4 runner ─► [validator → report_agent]        │
                    │     ├─ GATE B (final approval, mandatory)                  │
                    │     └─ IntegrationService ─► zip download | git branch+push│
                    │                              (+ optional PR)               │
                    │                                                            │
                    │  Agents invoked via ADK Runner; model from ProviderRouter  │
                    │  (apigee | direct | stub)                                  │
                    │                                                            │
                    │  Persistence: SQLite (default) / Postgres (flag)           │
                    │  jobs, phase_runs, artifacts, approvals, audit, tokens     │
                    └────────────────────────────────────────────────────────────┘
```

Two execution modes survive:
- **Quick mode** (paste of a single component, < ~150 lines): existing direct
  transformer→refactor→validator path, conversational, no job record required
  (still logged). Unchanged behavior — protected by the regression suite.
- **Pipeline mode**: everything else. Always creates a `MigrationJob`.

---

## 3. Job state machine (the core of V3)

`tools/workflow/state_machine.py`

```
CREATED
  → INGESTING                  (ingestion adapter runs)
  → PHASE1_RUNNING
  → AWAITING_PLAN_APPROVAL     (Gate A; skippable via job option auto_approve_plan)
       ├─ approved → PHASE2_RUNNING
       ├─ revise   → PHASE1_RUNNING   (re-run with approver feedback appended)
       └─ rejected → REJECTED  (terminal)
  → PHASE2_RUNNING             (chunk loop; per-chunk progress events)
  → PHASE3_RUNNING
  → PHASE4_RUNNING
  → AWAITING_FINAL_APPROVAL    (Gate B; NEVER skippable when target=git)
       ├─ approved → INTEGRATING
       ├─ revise   → PHASE2_RUNNING (selected chunks) or PHASE4_RUNNING (re-validate)
       └─ rejected → REJECTED
  → INTEGRATING                (zip assembly and/or git branch+push)
  → COMPLETED
Any state → FAILED (terminal, with error artifact)   |   Any state → CANCELLED
```

Rules the builder must enforce in code (not prompts):

- Transitions only via `MigrationJob.transition(to, actor, reason)` — writes an
  `audit_events` row every time.
- Every phase runner is **idempotent and resumable**: it checks `phase_runs` +
  artifact registry before invoking an agent; completed stages/chunks are skipped on
  resume. Server restart mid-job must resume from the last completed stage.
- Each stage gets a **token budget** and **wall-clock timeout** from config; breach →
  stage fails → retry policy (1 retry with context escalation, mirroring the existing
  `MigrationOrchestrator.execute_stage` logic) → then `FAILED`.
- Agent invocation: each stage builds a fresh ADK `Runner` with the stage's agent
  (from the existing factories), passes the typed input artifact (JSON) + context
  payload from `ContextEngine.project(level)`, and parses/validates the output into
  the typed artifact. Output that fails schema validation triggers one repair retry
  (re-prompt with validation errors), then stage failure.

---

## 4. Phase and agent specifications

### Phase 1 — Discovery & Planning
Stage order, levels, and artifacts (existing factories, regrouped):

| Stage | Agent (existing factory) | Context level | Input | Output artifact |
|---|---|---|---|---|
| 1.1 | `build_analyzer_agent` | 1 (→2 on escalation) | workspace inventory | `AnalysisReport` |
| 1.2 | `build_risk_detection_agent` | 1 | AnalysisReport | `RiskReport` |
| 1.3 | `build_migration_planner_agent` | 1 | AnalysisReport + RiskReport | `MigrationPlan` (chunks via existing `MigrationChunker`) |
| 1.4 | `build_state_migration_agent` | 2 | AnalysisReport + MigrationPlan | `StateMigrationPlan` |

Then the **phase runner** (deterministic code, not an agent) composes `Phase1Report`
(§7) and the Gate A `ApprovalRequest` containing: component/service/route counts,
risk score + top risks, chunk count + execution order, state strategy, effort
estimate, and *what the human is approving*.

Prompt change for 1.1–1.4: add a `## Revision feedback` section — when re-run after
a `revise` decision, the runner appends approver comments; the prompt must instruct
the agent to address them explicitly and list what changed.

### Phase 2 — Transformation
Per-chunk loop in dependency order (`MigrationPlan.execution_order`); chunks in the
same `parallel_groups` entry MAY run concurrently (config `max_parallel_chunks`,
default 1 for v3.0 — concurrency is a stretch goal, the loop must be written so
turning it on is a config change).

| Stage | Agent | Level | Input | Output |
|---|---|---|---|---|
| 2.1 per chunk | `build_transformer_agent` | 3 | chunk sources + StateMigrationPlan + ctx | `ReactSource[]` |
| 2.2 per chunk | `build_refactor_agent` → rename concept to **refactor_optimizer** | 3 | ReactSource[] | `RefactoredReactSource[]` |

The user's "transformation, refactor and optimization" maps to: transformer (2.1)
plus refactor agent (2.2) whose existing artifact already carries
`optimizations_applied` / `performance_improvements` / `removed_anti_patterns`.
`DECISION (recommended)`: keep two agents; extend the refactor prompt with an
explicit optimization checklist (memoization where measured-needed, list keys,
effect dependency audits, code-split lazy routes, bundle hygiene) rather than adding
a third agent — a third LLM pass per chunk roughly +50% phase cost for marginal gain.

Runner records per-chunk: files in/out, optimizations, token usage, duration →
`Phase2Report`. Test generation is **removed from the Phase 2 loop** (it moves to
Phase 3) — this is a deliberate change from V2's per-chunk
transformer→refactor→test trio.

### Phase 3 — Test Generation
New split: plan first, then generate.

| Stage | Agent | Level | Input | Output |
|---|---|---|---|---|
| 3.1 | **NEW** `build_test_planner_agent` (`tools/agents/test_planner.py` + prompt) | 1–2 | AnalysisReport + MigrationPlan + Phase2 file manifest | `TestPlan` (§7) |
| 3.2 per chunk | `build_test_generation_agent` (existing) | 3 | RefactoredReactSource[] + TestPlan slice for chunk | `TestSuite` |

`TestPlan` = the "complete testing plan" the user asked for: strategy, framework
(vitest + @testing-library/react default), coverage targets per component, test
matrix (unit / integration / e2e scenarios with priorities), mocking strategy for
migrated services/HTTP, DUIL-component testing notes, and a manual-testing checklist
for items automation can't cover.

`DECISION (recommended)`: V3.0 **generates** tests but does not execute them
(executing requires a node toolchain sandbox; specced as M6 stretch:
`tools/testing/runner.py` running `npm ci && vitest run` in an isolated temp dir
with no network, results merged into ValidationReport).

### Phase 4 — Validation, Reporting, Approval, Integration

| Stage | Actor | Input | Output |
|---|---|---|---|
| 4.1 | `build_validator_agent_v2` (level 3) + deterministic checks from `tools/functions/react_validator.py` | all RefactoredReactSource + TestSuites | `ValidationReport` |
| 4.2 | `build_report_agent` | Phase1–3 reports + ValidationReport | `MigrationReport` (now embeds the four per-phase reports — "what was done in each phase") |
| 4.3 | **Gate B** ApprovalService | MigrationReport + file diff preview | `ApprovalRecord` |
| 4.4 | **IntegrationService** (pure code, NO LLM) | approved output tree | zip and/or git branch push (+ PR URL) |

Validator `passed:false` remains a valid terminal *quality* result: the job still
reaches Gate B with the report; the human decides ship / revise / reject. Never
auto-retry on quality grounds (preserves the V2 rule).

---

## 5. Human-in-the-loop approval subsystem

`server/services/approvals.py`, tables `approvals` + `audit_events`.

- `ApprovalRequest`: `{job_id, gate: "plan"|"final", summary_md, artifact_refs[],
  requested_at, expires_at, status: pending|approved|rejected|revision_requested,
  decided_by, decided_at, comments}`.
- Decisions via `POST /api/jobs/{id}/approvals/{gate}` with
  `{decision: approve|reject|revise, comments?}`. `revise` requires comments.
- **Revise loops are bounded**: `max_revisions_per_gate` (default 3); breach forces
  approve-or-reject.
- Pending approval does not block the worker: the job parks in `AWAITING_*` and the
  state machine resumes on the API call (event-driven, not polling).
- Notifications: emit a webhook (`APPROVAL_WEBHOOK_URL`, optional) on gate entry so
  Teams/Slack/email integration is a config concern, not code.
- Audit: every decision row stores actor identity (from auth principal, §11), UTC
  timestamp, gate, decision, comments, and the SHA-256 of the report markdown that
  was on screen — what was approved is provable later.
- AuthZ: `approver` role required for decisions; the job creator MAY approve their
  own job only if `ALLOW_SELF_APPROVAL=true` (default true for dev, false for prod).

---

## 6. Ingestion & integration

### 6.1 Ingestion — `tools/ingestion/`
Common interface; all adapters normalize into a **Workspace**
(`<DATA_DIR>/jobs/<job_id>/input/`) plus an `IngestionManifest` (§7).

| Adapter | Source | Notes / hard requirements |
|---|---|---|
| `paste.py` | request body text | Detect single file vs multi-file paste (split on `// file: path` markers; else single `component.ts`). |
| `files.py` | multipart upload(s) | Preserve relative paths when provided. |
| `zip_archive.py` | uploaded .zip | **Security mandatory**: zip-slip path traversal guard (resolve + verify under workspace), reject symlinks, max 200 MB compressed / 1 GB inflated / 20k files, depth limit, reject nested zips beyond 1 level. |
| `git_repo.py` | repo URL + optional branch + auth ref | `git clone --depth 1 --branch <b>`; HTTPS+PAT (header-injected, never written to disk or logs) and SSH; record `remote_url`, `base_branch`, `base_commit_sha` in manifest — required later for push. Support GitHub / GitLab / Bitbucket incl. self-hosted enterprise hosts. |

All adapters then run a shared **sanitizer/profiler**: strip `node_modules`, `dist`,
`.git` internals from the working set; detect Angular markers (`angular.json`,
`@angular/*` in package.json, `.component.ts`); compute file inventory + size stats.
Non-Angular input → job fails fast at `INGESTING` with a clear message.

### 6.2 Integration — `tools/integration/`
Runs only after Gate B approval. Output tree assembled at
`<DATA_DIR>/jobs/<job_id>/output/`.

- `zip_export.py`: deterministic zip of output tree; served at
  `GET /api/jobs/{id}/output.zip` (auth required; link surfaced in UI).
- `git_integration.py` — **GitIntegrationService**, hard rules:
  1. Only valid when the job was ingested from git (manifest has remote) **or** the
     user supplies a target repo at integration time.
  2. Branch name: `migration/ng2react/<job_id>-<yyyymmdd>` (configurable template).
     **Never** commit to the base branch; refuse `main|master|develop` as targets.
  3. Fresh clone of `base_commit_sha`'s branch → create branch → write output →
     commit → push. Commit message template includes job id, phase metrics, gate-B
     approver, and report SHA. `MIGRATION_REPORT.md` is committed at the output root.
  4. Output layout `DECISION (recommended)`: write the React app to a new top-level
     `react-app/` directory in the repo (configurable `output_path`), leaving the
     Angular source untouched — reviewable side-by-side; deletion of Angular code is
     a human follow-up, never automated.
  5. Optional PR/MR: provider adapters (`github.py`, `gitlab.py`, `bitbucket.py`)
     behind one `create_pull_request(branch, title, body) -> url` interface; PR body
     = report executive summary. On API failure, the push still succeeds and the PR
     error is reported as a warning.
  6. Credentials resolved at call time from env/secret store (`GIT_TOKEN_<HOST>` or
     vault hook, §11); tokens never persisted in DB or logs.

---

## 7. New / changed data models (`tools/pipeline/models.py` additions)

```python
class JobState(str, Enum): ...            # §3 states

@dataclass
class IngestionManifest:
    source_type: str        # paste | files | zip | git
    file_count: int; total_bytes: int
    angular_version: str | None
    project_root: str       # relative root inside workspace
    remote_url: str | None = None
    base_branch: str | None = None
    base_commit_sha: str | None = None
    warnings: list[str] = field(default_factory=list)

@dataclass
class TestPlan:             # output of NEW test_planner_agent
    strategy_summary: str
    framework: str          # vitest default
    coverage_target_pct: int
    matrix: list[TestMatrixEntry]   # {target, type: unit|integration|e2e, scenarios[], priority}
    mocking_strategy: str
    manual_checklist: list[str]

@dataclass
class PhaseReport:          # one per phase; Phase{1..4}Report are instances
    phase: int; title: str
    started_at: float; finished_at: float
    stages: list[StageRecord]       # {stage, agent, status, retries, tokens_in/out, duration_s}
    summary_md: str                 # human-readable "what was done"
    artifacts: list[str]            # artifact registry keys
    warnings: list[str]

@dataclass
class ApprovalRecord:
    gate: str; decision: str; decided_by: str; decided_at: float
    comments: str; report_sha256: str

# MigrationReport gains:
#   phase_reports: list[PhaseReport]
#   approvals: list[ApprovalRecord]
#   integration: dict  (zip path / branch / pr_url)
```

DB schema (SQLAlchemy, SQLite default file `<DATA_DIR>/ngreact.db`; `DATABASE_URL`
env switches to Postgres — both must pass the same test suite):

```
jobs(id PK, state, source_type, options_json, created_by, created_at, updated_at)
phase_runs(id PK, job_id FK, phase, stage, chunk_id NULL, status, retries,
           tokens_in, tokens_out, duration_s, error_text, started_at, finished_at)
artifacts(id PK, job_id FK, key, kind, path, sha256, created_at)   -- payloads on disk, not in DB
approvals(id PK, job_id FK, gate, status, summary_sha256, decided_by, decided_at, comments)
audit_events(id PK, job_id FK, actor, event, detail_json, created_at)
token_usage(id PK, job_id FK, phase, agent, model, tokens_in, tokens_out, cost_estimate)
```

Artifact payloads (JSON / markdown / source files) live on disk under
`<DATA_DIR>/jobs/<id>/artifacts/`; the DB stores pointers + hashes.

---

## 8. API surface (`server/`)

FastAPI app, mounted UI static files, OpenAPI on. All routes under `/api`.

```
POST   /api/jobs                          create job
       multipart/form-data OR json:
       { source: {type: paste|files|zip|git, ...},
         options: { auto_approve_plan: bool=false,
                    target: screen|zip|git, output_path: "react-app",
                    create_pr: bool=false, model_profile: str|null } }
GET    /api/jobs?state=&page=             list (RBAC-scoped)
GET    /api/jobs/{id}                     state + phase + chunk progress + gate info
GET    /api/jobs/{id}/events              SSE: state transitions, chunk progress, logs
GET    /api/jobs/{id}/artifacts           registry listing
GET    /api/jobs/{id}/artifacts/{key}     artifact content
GET    /api/jobs/{id}/report              consolidated MigrationReport (md + json)
POST   /api/jobs/{id}/approvals/{gate}    {decision, comments?}
POST   /api/jobs/{id}/cancel
POST   /api/jobs/{id}/resume              resume after crash/restart
GET    /api/jobs/{id}/output.zip
POST   /api/jobs/{id}/integrate/git      {repo_url?, base_branch?, output_path?, create_pr?}
POST   /api/chat                          quick mode (paste) — preserves V2 behavior
GET    /api/health                        liveness + provider mode + model registry status
```

Long-running work executes on a background worker. `DECISION (recommended)`: v3.0
uses an in-process `asyncio` task queue with DB-backed job state (resume covers
restarts); the JobService interface must be queue-agnostic so Celery/RQ can be
swapped in at M6 without route changes.

---

## 9. LLM provider strategy (Apigee + direct)

Keep `NGREACT_LLM_MODE = stub | google-ai | apigee` and `build_model_for_env()` as
the single factory. Build on what exists:

- **ProviderRouter** (`components/llm/router.py`, thin): resolves
  `(agent_name) -> model instance` using `models.{prod,test}.yaml`. Registry gains a
  per-agent block, e.g. heavier model for transformer/validator, lighter for
  risk/report. Unknown agent → registry default. This is the "adapt both" knob:
  the same agent set runs through Apigee (Azure OpenAI / Vertex deployments behind
  the DHL gateway, env-specific proxy URLs already supported by `ApigeeSettings`)
  or direct vendor APIs, chosen entirely by env + yaml.
- **Resilience policy** (one place, wrapping all REST calls): retries with
  exponential backoff + jitter on 429/5xx honoring `Retry-After`; circuit breaker
  (open after N consecutive failures, half-open probe); per-job token budget
  enforcement; usage recorded to `token_usage` after every call (Apigee gateway
  chargeback needs this).
- **Streaming** stays behind `APIGEE_STREAMING_ENABLED`; pipeline agents run
  non-streaming, quick-mode chat may stream.
- **Stub mode** must cover every new agent (test_planner) with canned artifacts so
  the full 4-phase pipeline runs deterministically in CI with zero network.

---

## 10. UI plan (`ui/`)

Rebuild on the surviving `ui/app.js` patterns (DHL-styled, FastAPI-backed).
Screens (plain HTML/CSS/JS is fine; this is not the product, it's the console):

1. **New migration**: tabs Paste / Upload / Zip / Git (URL + branch + token field),
   options (target, output_path, auto-approve plan, create PR).
2. **Job dashboard**: phase stepper (1→2→3→4), live chunk progress via SSE, token
   + cost counters.
3. **Approval screens**: Gate A renders Phase1Report markdown + plan table with
   Approve / Request changes (comment box) / Reject. Gate B adds a file tree of the
   output with per-file before/after view and the validation summary.
4. **Report view**: consolidated report; per-phase expandables; download zip; git
   integration panel (branch name preview, PR toggle) for jobs with target=git.

---

## 11. Enterprise hardening

- **AuthN**: OIDC bearer-token validation middleware (issuer/audience from env) —
  fits DHL SSO; `AUTH_MODE=none` for local dev. Principal flows into
  `created_by` / `decided_by` / audit rows.
- **AuthZ**: two roles v3.0 — `user` (create/view own jobs) and `approver`
  (decide gates, view all). Role claim name configurable.
- **Secrets**: all tokens via env with a single `secrets.py` accessor so a vault
  backend (e.g. HashiCorp) is a drop-in; secrets never logged, never in DB, masked
  in artifacts (`Authorization`, `token`, `apikey` regex scrub on everything
  persisted or echoed by agents).
- **Data handling**: source code never leaves the chosen LLM route (Apigee in
  prod). `DATA_RETENTION_DAYS` (default 30) purge task for job workspaces.
  No source content in logs above DEBUG.
- **Input safety**: zip limits (§6.1), upload size caps at the HTTP layer, git
  clone timeout + size cap, MIME/type allowlist.
- **Observability**: extend existing tracing patch with `job_id`/`phase`/`chunk_id`
  attributes on every span; structured JSON logs (loguru already present);
  `/api/health` for probes; Prometheus-style metrics endpoint is an M6 stretch.
- **Cost control**: per-job token ceiling (default e.g. 2M), per-phase budgets,
  surfaced in the dashboard; hard stop → job `FAILED` with a resumable checkpoint.

---

## 12. Build plan — milestones for the build model

Each milestone ends green: code + tests + the acceptance criteria below pass.
Suggested branch per milestone: `feat/v3-m<N>-<slug>`.

### M0 — Baseline freeze (small)
- Commit the current working tree as the V2 baseline (separate commit for the
  component deletions). Tag `v2-baseline`.
- Add CI script (`make test` or `scripts/ci.sh`): run pytest with stub LLM mode.
- Write **quick-mode golden tests**: paste a fixture Angular component through
  transformer→refactor→validator with StubLlm; snapshot artifacts. These protect
  V2 behavior through the whole V3 build.
- **Accept**: CI green; tag exists; golden snapshots committed under `tests/golden/`.

### M1 — Job model, persistence, ingestion, API skeleton
- `server/` FastAPI app; DB layer + schema (§7); `MigrationJob` state machine with
  transitions, audit rows, resume scaffolding (phases stubbed as no-ops).
- `tools/ingestion/` all four adapters + sanitizer/profiler + `IngestionManifest`.
- Endpoints: jobs CRUD, events SSE, artifacts, health. UI screen 1 + minimal
  dashboard.
- **Accept**: create a job from each of paste / files / zip / git (local fixture
  repo); workspace materialized correctly; zip-slip and oversize fixtures rejected
  with 4xx; job reaches a stubbed `COMPLETED`; restart-resume test passes.

### M2 — Phase 1 runner + Gate A
- Phase 1 runner invoking the four existing agents via ADK Runner with context
  projection; artifact validation + repair-retry; `Phase1Report` composer.
- ApprovalService + approvals API + Gate A UI; revise loop re-runs Phase 1 with
  feedback (bounded).
- **Accept**: with StubLlm, a fixture project produces a Phase1Report and parks at
  `AWAITING_PLAN_APPROVAL`; approve → `PHASE2_RUNNING`(stub); revise with comments
  → Phase 1 re-runs and report records the revision; reject → `REJECTED`; all
  decisions present in `audit_events`. One live smoke test against Apigee testing
  env (manual, documented in `docs/SMOKE.md`).

### M3 — Phase 2 transformation loop
- Chunk loop (sequential v3.0, structured for parallel), transformer +
  refactor_optimizer per chunk, per-chunk checkpointing in `phase_runs`,
  `Phase2Report`, SSE chunk progress. Refactor prompt gains the optimization
  checklist; DUIL table extracted to a shared prompt fragment.
- **Accept**: multi-chunk fixture migrates end-to-end with stub; kill the server
  mid-loop → resume completes remaining chunks only; Phase2Report lists per-chunk
  files, optimizations, tokens.

### M4 — Phase 3 test generation
- New `test_planner` agent (factory + prompt + stub output + registry entry);
  per-chunk test generation consuming TestPlan slices; `Phase3Report`.
- **Accept**: TestPlan artifact has matrix entries for every migrated component;
  generated test files land in the output tree mirroring source layout;
  Phase3Report counts match TestSuite totals.

### M5 — Phase 4: validation, report, Gate B, integration
- Validator stage (LLM + deterministic checks), report_agent consuming the four
  PhaseReports, Gate B UI with file tree + diff preview, IntegrationService:
  zip export + GitIntegrationService (branch/commit/push, refuse protected
  branches) + GitHub PR adapter (GitLab/Bitbucket stubs with the interface).
- **Accept**: end-to-end git fixture: ingest from a local bare repo → approve both
  gates → branch `migration/ng2react/...` exists in the bare repo with output under
  `react-app/` + `MIGRATION_REPORT.md`; base branch untouched; integration without
  Gate B approval is impossible (test asserts 409); `output.zip` matches output
  tree hash; validator `passed:false` still reaches Gate B.

### M6 — Enterprise hardening + polish
- OIDC middleware + roles; secrets accessor + log scrubbing; retention purge task;
  resilience policy (backoff/circuit breaker) on the REST LLM path; token budgets;
  Postgres CI leg; UI report view polish; approval webhook.
- Stretch (separately mergeable): test execution sandbox; parallel chunks;
  Prometheus metrics; queue swap-out.
- **Accept**: auth on/off modes both tested; secret-scrub test (token in agent
  output never reaches disk); 429-storm simulation completes job via backoff;
  same suite green on SQLite and Postgres.

---

## 13. Regression test plan

Layers (all runnable offline via stub mode):

1. **Golden quick-mode tests** (from M0) — V2 paste behavior never regresses.
2. **Contract tests per agent**: stub input → output parses into its typed artifact;
   schema-violation fixture triggers exactly one repair retry.
3. **State machine property tests**: illegal transitions raise; every transition
   writes audit; resume from every interruptible state.
4. **Ingestion suite**: per adapter happy path + malicious fixtures (zip-slip,
   symlink, oversize, non-Angular, broken git URL).
5. **Approval suite**: gate ordering, self-approval flag, revision bound, report-SHA
   binding.
6. **Integration suite**: local bare-repo push tests; protected-branch refusal;
   PR adapter mocked at HTTP layer.
7. **E2E pipeline tests**: one per input mode, full 4 phases with stub, asserting
   final report structure and per-phase reports.
8. **Live smoke checklist** (`docs/SMOKE.md`, manual): one small real project through
   Apigee testing env per release; checklist of gate screens, report quality, push.

CI matrix: `{SQLite, Postgres} × {auth on, off}`, stub mode, Python 3.13.

---

## 14. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LLM output not schema-valid at scale | pipeline stalls | repair-retry + artifact validation at every stage; stub-mode contract tests pin schemas |
| Token costs on large repos | budget blowout | chunking already bounds per-call size; per-phase budgets + hard job ceiling; Level 1–4 context discipline preserved |
| Git push to wrong branch | production damage | branch-name template + protected-branch denylist + Gate B prerequisite enforced in code + bare-repo tests |
| Approval bottleneck stalls jobs | poor UX | webhook notifications; `auto_approve_plan` for Gate A; expiry surfaces stale jobs |
| Prompt-orchestration habits leak back | non-determinism returns | root-agent prompt loses all pipeline instructions in M2 (it keeps only quick mode + chat); pipeline order exists only in Python |
| WSL/Windows path issues (`/mnt/c/...` with spaces) | flaky file ops | all paths via `pathlib`, no shell string interpolation; CI runs the ingestion suite on the spaced path |
| Apigee gateway throttling | phase failures | resilience policy honors Retry-After; circuit breaker; per-call telemetry to spot it |

---

## 15. Decisions taken (overridable before M-start)

| # | Decision | Default chosen | Alternative |
|---|---|---|---|
| D1 | Optimization as third agent? | **No** — folded into refactor_optimizer checklist | separate optimizer agent (+cost) |
| D2 | Execute generated tests? | **Not in v3.0** — generate + plan only; sandbox runner is M6 stretch | run vitest in sandbox at M5 |
| D3 | Git output layout | **`react-app/` alongside Angular source** (configurable `output_path`) | in-place replacement (rejected: irreversible, unreviewable) |
| D4 | Gate A mandatory? | Optional (`auto_approve_plan`), **Gate B mandatory always** for zip+git, screen-only quick results exempt | both mandatory |
| D5 | DB | SQLite default, Postgres via `DATABASE_URL` (same ORM) | Postgres-only |
| D6 | Worker | in-process asyncio + DB state, queue-swappable interface | Celery/Redis from day 1 (over-engineering at current scale) |
| D7 | AuthN | OIDC bearer middleware, `AUTH_MODE=none` for dev | API keys (weaker fit for DHL SSO) |
| D8 | PR creation | optional flag, GitHub adapter first | all three providers at M5 |
