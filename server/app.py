"""FastAPI application — thin HTTP shell over :class:`server.service.JobService`.

Implements the M1 subset of the API surface (plan §8): job create/list/get,
artifacts, events (SSE), approvals, cancel, resume, and health. Long-running
work executes on a background thread; job state is DB-backed so a restart
resumes (plan §8, D6 — in-process worker, queue-swappable).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re as _re
import tempfile
import uuid

# ---------------------------------------------------------------------------
# ADK monkey-patch: allow JSX/TS curly braces in agent instruction files.
# ADK's inject_session_state raises KeyError for any {expr} it can't resolve
# as a session variable. We override it to silently pass those through so the
# LLM sees the original text (e.g. {onSubmit}, {control}, import { useState }).
# ---------------------------------------------------------------------------
try:
    import google.adk.utils.instructions_utils as _iu

    async def _safe_inject_session_state(template, context):
        result = []
        last = 0
        for m in _re.finditer(r'{+[^{}]*}+', template):
            result.append(template[last:m.start()])
            full = m.group(0)
            var_name = full.strip('{}').strip()
            try:
                val = context[var_name]
                result.append(str(val) if val is not None else full)
            except Exception:
                result.append(full)  # not a session var — leave as-is
            last = m.end()
        result.append(template[last:])
        return ''.join(result)

    _iu.inject_session_state = _safe_inject_session_state
except ImportError:
    pass  # ADK not installed yet — patch applied after pip install via START.bat
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from tools.workflow.models import ApprovalDecision, Gate, JobOptions, JobState
from tools.workflow.store import JobStore

from . import build_default_runner
from .config import load_settings
from .service import JobService

settings = load_settings()
_store = JobStore(settings.db_path)
# Real Phase 1 agents (NGREACT_LLM_MODE selects stub/apigee); phases 2–4 stub
# until M3–M5. Auto-gates off so the human approval API is exercised.
service = JobService(_store, data_dir=settings.data_dir, runner=build_default_runner(),
                     auto_gates=True)

app = FastAPI(title="NgReact V3 — Angular→React Migration Platform", version="3.0.0-m1")


# ---------------------------------------------------------------------------
# Authentication (M6) — optional shared-secret gate on the API surface.
#   AUTH_MODE=none   (default) — open, for local dev.
#   AUTH_MODE=apikey           — every /api/* call (except /api/health) must
#                                present the key via `Authorization: Bearer <k>`
#                                or `X-API-Key: <k>`. Static UI assets stay open.
# OIDC (AUTH_MODE=oidc) is the production path — adapter deferred (needs an IdP).
# ---------------------------------------------------------------------------
_OPEN_PATHS = {"/api/health"}


@app.middleware("http")
async def _auth_guard(request, call_next):
    if settings.auth_mode == "apikey":
        path = request.url.path
        if path.startswith("/api/") and path not in _OPEN_PATHS:
            presented = request.headers.get("x-api-key", "")
            authz = request.headers.get("authorization", "")
            if authz.lower().startswith("bearer "):
                presented = presented or authz[7:].strip()
            if not settings.api_key or presented != settings.api_key:
                from fastapi.responses import JSONResponse as _JSON
                return _JSON({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


def _run_async(job_id: str) -> None:
    """Drive a job on a worker thread so the request returns immediately.

    ``NGREACT_DISABLE_BG=1`` makes this a no-op so tests can drive jobs
    deterministically via the ``/resume`` and approval endpoints.
    """
    if os.getenv("NGREACT_DISABLE_BG") == "1":
        return
    asyncio.create_task(asyncio.to_thread(service.run, job_id))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "auth_mode": settings.auth_mode,
        "data_dir": settings.data_dir,
    }


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@app.post("/api/jobs")
async def create_job(body: dict = Body(...)) -> dict[str, Any]:
    """Create a job. Body: ``{source: {type, ...}, options: {...}}``.

    Binary zip payloads are passed base64-encoded under ``source.zip_b64``.
    """
    source = body.get("source") or {}
    source_type = source.get("type")
    if source_type not in ("paste", "files", "zip", "git"):
        raise HTTPException(400, f"Invalid source.type: {source_type!r}")

    payload: dict[str, Any] = {}
    if source_type == "paste":
        payload["content"] = source.get("content", "")
    elif source_type == "files":
        payload["files"] = source.get("files", [])
    elif source_type == "zip":
        if "zip_b64" not in source:
            raise HTTPException(400, "zip source requires 'zip_b64'")
        payload["zip_bytes"] = base64.b64decode(source["zip_b64"])
    elif source_type == "git":
        if "repo_url" not in source:
            raise HTTPException(400, "git source requires 'repo_url'")
        payload.update(repo_url=source["repo_url"], branch=source.get("branch"),
                       token=source.get("token"))

    options = JobOptions(**(body.get("options") or {}))
    created_by = body.get("created_by", "anonymous")
    rec = service.create_job(source_type, payload, options=options, created_by=created_by)

    if rec.state is not JobState.FAILED:
        _run_async(rec.id)
    return {"job_id": rec.id, "state": rec.state.value}


@app.get("/api/jobs")
def list_jobs(state: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    st = JobState(state) if state else None
    jobs = service.store.list_jobs(state=st, limit=limit, offset=offset)
    return {"jobs": [{"job_id": j.id, "state": j.state.value, "source_type": j.source_type,
                      "created_at": j.created_at} for j in jobs]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return service.status(job_id)
    except KeyError:
        raise HTTPException(404, f"No such job: {job_id}")


@app.get("/api/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str) -> dict[str, Any]:
    if service.store.get_job(job_id) is None:
        raise HTTPException(404, f"No such job: {job_id}")
    return {"artifacts": service.store.list_artifacts(job_id)}


@app.get("/api/jobs/{job_id}/artifacts/{key}")
def get_artifact(job_id: str, key: str) -> dict[str, Any]:
    """Return one artifact's JSON content (used by the UI to render gate reports)."""
    from tools.workflow.artifacts import read_artifact
    if service.store.get_job(job_id) is None:
        raise HTTPException(404, f"No such job: {job_id}")
    data = read_artifact(service._workspace(job_id), key)
    if data is None:
        raise HTTPException(404, f"No such artifact: {key}")
    return {"key": key, "content": data}


@app.get("/api/jobs/{job_id}/files")
def list_output_files(job_id: str) -> dict[str, Any]:
    """Return every generated output file (React + tests) with its content.

    This is the converted code the user came for: components, hooks, contexts,
    and *.test.tsx test files written to the job's output tree.
    """
    if service.store.get_job(job_id) is None:
        raise HTTPException(404, f"No such job: {job_id}")
    out = service._workspace(job_id).output_dir
    files: list[dict[str, Any]] = []
    if out.exists():
        for p in sorted(out.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(out)).replace("\\", "/")
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files.append({
                "path": rel,
                "content": content,
                "is_test": rel.endswith((".test.tsx", ".test.ts", ".spec.tsx", ".spec.ts")),
                "lines": content.count("\n") + 1,
            })
    return {"job_id": job_id, "count": len(files), "files": files}


@app.get("/api/jobs/{job_id}/deliverable")
def download_deliverable(job_id: str) -> FileResponse:
    """Download the assembled deliverable.zip (available after integration)."""
    if service.store.get_job(job_id) is None:
        raise HTTPException(404, f"No such job: {job_id}")
    zip_path = Path(service._workspace(job_id).root) / "deliverable.zip"
    if not zip_path.exists():
        raise HTTPException(404, "Deliverable not assembled yet (complete the migration first).")
    return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}_react.zip")


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str) -> StreamingResponse:
    """SSE stream of audit events + state. Polls the store and emits new rows."""
    if service.store.get_job(job_id) is None:
        raise HTTPException(404, f"No such job: {job_id}")

    async def gen():
        seen = 0
        for _ in range(600):  # ~10 min cap at 1s cadence
            events_ = service.store.get_audit(job_id)
            for ev in events_[seen:]:
                yield f"data: {json.dumps({'event': ev.event, 'detail': ev.detail, 'at': ev.created_at})}\n\n"
            seen = len(events_)
            rec = service.store.get_job(job_id)
            if rec and rec.state.value in ("completed", "failed", "rejected", "cancelled"):
                yield f"data: {json.dumps({'event': 'terminal', 'state': rec.state.value})}\n\n"
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/jobs/{job_id}/approvals/{gate}")
async def approve(job_id: str, gate: str, body: dict = Body(...)) -> dict[str, Any]:
    try:
        gate_enum = Gate(gate)
        decision = ApprovalDecision(body["decision"])
    except (ValueError, KeyError):
        raise HTTPException(400, "Invalid gate or decision")
    actor = body.get("actor", "anonymous")
    comments = body.get("comments", "")
    try:
        state = await asyncio.to_thread(
            service.submit_decision, job_id, gate_enum, decision, actor, comments)
    except KeyError:
        raise HTTPException(404, f"No such job: {job_id}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(500, f"Approval failed: {e}")
    # Drive the next phase in the background so this request returns immediately.
    if state not in (JobState.COMPLETED, JobState.REJECTED, JobState.FAILED):
        _run_async(job_id)
    return {"job_id": job_id, "state": state.value}


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str, body: dict = Body(default={})) -> dict[str, Any]:
    try:
        job = service._load(job_id)
    except KeyError:
        raise HTTPException(404, f"No such job: {job_id}")
    job.cancel(actor=body.get("actor", "anonymous"))
    return {"job_id": job_id, "state": job.state.value}


@app.post("/api/jobs/{job_id}/resume")
async def resume(job_id: str) -> dict[str, Any]:
    try:
        state = await asyncio.to_thread(service.resume, job_id)
    except KeyError:
        raise HTTPException(404, f"No such job: {job_id}")
    return {"job_id": job_id, "state": state.value}


# ===========================================================================
# UI facade — synchronous conversational endpoints for the custom web UI
# (ui/). These run the full root_agent directly (paste / upload / git), which
# is what the single-page UI talks to. Separate from the /api/jobs pipeline.
# ===========================================================================
_UI_DIR = Path(__file__).resolve().parents[1] / "ui"


def _ui_run(message: str, session_id: str | None = None) -> str:
    """Run the conversational root_agent once and return its final text.

    Imported lazily so the job API and offline tests don't require google-adk.
    Runs on FastAPI's threadpool (these endpoints are sync `def`), so the
    asyncio.run() inside _collect_final_text has no running loop to clash with.
    """
    from agent import root_agent
    from .agent_invoker import _collect_final_text

    return _collect_final_text(root_agent, message, session_id or uuid.uuid4().hex)


# Per-session conversation history for the chat popup (in-process, resets on restart).
_chat_history: dict[str, list[dict]] = {}


@app.post("/api/session")
def ui_session() -> dict[str, str]:
    """The UI tracks a session id; for the stateless facade any id works."""
    return {"session_id": uuid.uuid4().hex}


_CHAT_SCOPE = (
    "You are an Angular-to-React migration expert embedded in the NgReact platform. "
    "Help with questions about Angular-to-React migration, the provided Angular source code, "
    "transformation decisions, DHL DUIL compliance, migration risks, generated reports, "
    "React best practices, and general software engineering topics relevant to the project. "
    "If a job context is provided, use it to give informed answers about the current migration. "
    "Keep answers concise and practical.\n\n"
)


@app.post("/api/run")
def ui_run(body: dict = Body(...)) -> JSONResponse:
    raw_message = (body.get("message") or "").strip()
    session_id  = body.get("session_id") or uuid.uuid4().hex
    job_id_hint = (body.get("job_id") or "").strip()
    if not raw_message:
        raise HTTPException(400, "Empty message")

    # Optionally inject current migration job state as context
    job_context = ""
    if job_id_hint:
        try:
            from tools.workflow.artifacts import read_artifact
            status   = service.status(job_id_hint)
            phase1   = read_artifact(service._workspace(job_id_hint), "phase1_report")
            analysis = {}
            if phase1 and isinstance(phase1, dict):
                analysis = (phase1.get("analysis_report")
                            or (phase1.get("stages") or [{}])[0].get("output") or {})
            job_context = (
                f"[Current migration job: {job_id_hint} | State: {status.get('state', '?')}"
                + (f" | Angular {analysis.get('angular_version')}"
                   if analysis.get("angular_version") else "")
                + (f" | {analysis.get('component_count')} components"
                   if analysis.get("component_count") else "")
                + "]\n"
            )
        except Exception:
            pass  # job context is optional — never fail the chat

    # Build prompt: scope + optional job context + conversation history + user message
    history = _chat_history.get(session_id, [])
    parts: list[str] = [_CHAT_SCOPE]
    if job_context:
        parts.append(job_context)
    if history:
        conv = "\n\n".join(f"User: {t['q']}\nAssistant: {t['a']}" for t in history[-8:])
        parts.append(f"Previous conversation:\n{conv}\n---")
    parts.append(raw_message)
    full_prompt = "\n\n".join(parts)

    try:
        response = _ui_run(full_prompt, session_id=session_id)
    except Exception as e:
        raise HTTPException(500, str(e)) from e

    # Persist this turn so follow-up messages have context
    _chat_history.setdefault(session_id, []).append({"q": raw_message, "a": response})
    _chat_history[session_id] = _chat_history[session_id][-20:]

    return JSONResponse({"session_id": session_id, "response": response})


@app.post("/api/upload")
def ui_upload(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
) -> JSONResponse:
    """Accept a real .zip upload, save it, and run the migration pipeline."""
    filename = file.filename or "upload.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(400, "Only .zip archives are supported for upload.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="ngreact_upload_"))
    zip_path = tmp_dir / filename
    zip_path.write_bytes(file.file.read())

    message = (
        f"Migrate the Angular project in the uploaded zip at {zip_path}. "
        f"Use ingest_zip to extract it, then run the full migration pipeline."
    )
    try:
        response = _ui_run(message)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return JSONResponse({"session_id": session_id or uuid.uuid4().hex, "response": response})


@app.post("/api/git")
def ui_git(body: dict = Body(...)) -> JSONResponse:
    repo_url = (body.get("repo_url") or "").strip()
    if not repo_url:
        raise HTTPException(400, "Empty repo URL")
    branch = (body.get("branch") or "").strip()
    branch_hint = f" on branch {branch}" if branch else ""
    message = (
        f"Migrate the Angular project from the git repository {repo_url}{branch_hint}. "
        f"Use clone_git_repo to clone it, then run the full migration pipeline."
    )
    try:
        response = _ui_run(message)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return JSONResponse({"session_id": body.get("session_id") or uuid.uuid4().hex,
                         "response": response})


@app.get("/api/test-report/xlsx")
def download_test_report() -> FileResponse:
    """Download the latest XLSX test report generated by ``pytest tests/``.

    The report is written to ``test_report.xlsx`` in the project root by the
    conftest.py XLSX reporter plugin every time the test suite runs.
    """
    report_path = Path(__file__).resolve().parents[1] / "test_report.xlsx"
    if not report_path.exists():
        raise HTTPException(
            404,
            "Test report not found. Generate it by running:  pytest tests/  "
            "The conftest.py reporter writes test_report.xlsx automatically.",
        )
    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="ngreact_test_report.xlsx",
    )


@app.get("/api/jobs/{job_id}/test-report")
def download_job_test_report(job_id: str) -> StreamingResponse:
    """Download a job-specific XLSX built from the Phase 3 TestPlan + TestSuite artifacts.

    Covers positive scenarios (Smoke, Regression) and integration/E2E scenarios derived
    from the migration plan for this exact job — not the project's own unit test suite.
    Returns 404 until Phase 3 has completed and the test_plan artifact exists.
    """
    from tools.workflow.artifacts import read_artifact
    from .test_workbook import build_test_workbook

    if service.store.get_job(job_id) is None:
        raise HTTPException(404, f"No such job: {job_id}")

    ws = service._workspace(job_id)
    test_plan = read_artifact(ws, "test_plan")
    if test_plan is None:
        raise HTTPException(
            404,
            "Test plan not available yet — wait for Phase 3 (test generation) to complete.",
        )

    # Collect every test suite written during Phase 3 (keys: tests_<chunk_id>)
    all_keys = [a["key"] for a in (service.store.list_artifacts(job_id) or [])]
    suites = []
    for key in sorted(all_keys):
        if key.startswith("tests_"):
            suite = read_artifact(ws, key)
            if suite:
                suites.append(suite)

    xlsx_bytes = build_test_workbook(test_plan, suites)
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{job_id}_test_report.xlsx"'},
    )


@app.get("/")
def ui_index() -> FileResponse:
    return FileResponse(_UI_DIR / "index.html")


# Serve the UI's static assets explicitly. A catch-all StaticFiles mount at "/"
# shadows the /api routes in Starlette, so we expose only the known files.
_UI_ASSETS = {
    "app.js": "application/javascript",
    "styles.css": "text/css",
}


@app.get("/{asset}")
def ui_asset(asset: str) -> FileResponse:
    media = _UI_ASSETS.get(asset)
    path = _UI_DIR / asset
    if media is None or not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type=media)
