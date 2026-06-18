# NgReact — Startup Guide

## What Is This?

**NgReact** is a DHL AI agent that converts Angular applications to React 18+ using a 9-stage artifact-driven pipeline built on Google ADK (Agent Development Kit).

### Pipeline stages

| Stage | Agent | Responsibility |
|---|---|---|
| 1 | **Analyzer** | Extracts every component, service, module, route, pipe, guard, directive from Angular source |
| 2 | **Risk Detection** | Scores migration complexity, identifies blockers, recommends approach |
| 3 | **Migration Planner** | Builds dependency-ordered execution chunks with token estimates |
| 4 | **State Migration** | Designs the React state architecture (Context, Zustand, hooks) |
| 5 | **Transformer** | Converts Angular TypeScript → React 18+ TSX with DHL DUIL components |
| 6 | **Refactor** | Fixes anti-patterns, adds memoisation, enforces DHL DUIL compliance |
| 7 | **Test Generation** | Generates Vitest + React Testing Library test suites |
| 8 | **Validator** | Quality gate — PASS/FAIL on TypeScript, hooks rules, DHL DUIL compliance |
| 9 | **Report** | Aggregates all artifacts into a final migration report |

For single-component paste, only stages 5–8 run (no project analysis needed).

---

## Prerequisites

- Python 3.11+
- Git
- (For DHL/Apigee mode) DHL VPN connected
- (For Google AI mode) `GOOGLE_API_KEY` from [Google AI Studio](https://aistudio.google.com)

---

## First-Time Setup

### 1. Clone or open the project

```powershell
cd C:\Users\<you>\Downloads\Ang2React_2\Ang2React
```

### 2. Create the virtual environment

```powershell
python -m venv .venv
```

### 3. Activate it

**PowerShell:**
```powershell
& ".\.venv\Scripts\Activate.ps1"
```

**WSL / bash:**
```bash
source .venv/bin/activate
```

### 4. Install dependencies

```powershell
pip install -r requirements.txt
pip install -e .
```

### 5. Configure your environment

All environment files live in the `config/` folder. Copy the one that matches your setup to the project root as `.env`:

| File | Use when |
|---|---|
| `config/.env.example` | Starting fresh — fill in your credentials |
| `config/.env` | Already configured for Apigee / OpenAI |
| `config/.env.test` | No VPN, no API keys — uses the stub LLM |
| `config/.env.google_ai` | Using Google AI Studio (personal Gemini key) |
| `config/.env.apigee_backup` | Fallback Apigee config |

**PowerShell:**
```powershell
# Stub mode (no keys needed — great for local dev/testing):
Copy-Item config\.env.test .env

# DHL Apigee (requires VPN + API key):
Copy-Item config\.env .env

# Google AI Studio:
Copy-Item config\.env.google_ai .env
```

**WSL / bash:**
```bash
cp config/.env.test .env          # stub mode
cp config/.env .env               # Apigee
cp config/.env.google_ai .env     # Google AI
```

> **Never commit `.env` to Git.** It contains secrets. It is listed in `.gitignore`.

---

## LLM Modes

The agent selects its backend from the `NGREACT_LLM_MODE` env var:

| Mode | Value | Needs |
|---|---|---|
| **Stub** (offline) | `NGREACT_LLM_MODE=stub` | Nothing — scripted responses, zero latency, no keys |
| **DHL Apigee** (default) | `NGREACT_LLM_MODE=apigee` | DHL VPN + `APIGEE_API_KEY` |
| **Google AI Studio** | `NGREACT_LLM_MODE=google-ai` | `GOOGLE_API_KEY` from AI Studio |
| **OpenAI direct** | `NGREACT_LLM_MODE=openai` | `OPENAI_API_KEY` |

**Recommended for local development:** start with `stub` mode to verify the pipeline flows correctly before switching to a live LLM.

### Stub mode `.env`
```dotenv
NGREACT_LLM_MODE=stub
LOG_LEVEL=INFO
```

### DHL Apigee `.env`
```dotenv
NGREACT_LLM_MODE=apigee
APIGEE_ENVIRONMENT=production
APIGEE_API_KEY=<your-key-from-AI-Champion>
APIGEE_PROXY_URL_PRODUCTION=https://apihub-sandbox.dhl.com/genai-test
APIGEE_DEFAULT_VERTEX_MODEL=gemini-2.0-flash-001
APIGEE_STREAMING_ENABLED=false
LOG_LEVEL=WARNING
```

### Google AI Studio `.env`
```dotenv
NGREACT_LLM_MODE=google-ai
GOOGLE_API_KEY=<your-key-from-AI-Studio>
LOG_LEVEL=INFO
```

---

## Daily Startup

### ADK Web UI (recommended for development)

```powershell
# PowerShell
Set-Location "C:\Users\<you>\Downloads\Ang2React_2\Ang2React"
& ".\.venv\Scripts\Activate.ps1"
adk web . --port 8002
```

```bash
# WSL / bash
cd /mnt/c/Users/<you>/Downloads/Ang2React_2/Ang2React
source .venv/bin/activate
adk web . --port 8002
```

Opens at **http://127.0.0.1:8002**

The ADK web UI provides:
- Full conversation history
- Tool call traces (see exactly which agents and tools were called)
- Real-time streaming output
- Session management

---

## How to Use NgReact

### Mode 1 — Direct code paste (single component, no project analysis)

Just paste Angular code into the chat and hit send. The agent automatically detects Angular code and routes through the transformer → refactor → validator pipeline.

**Example prompt:**
```
Convert this Angular component to React:

@Component({
  selector: 'app-user-list',
  template: `
    <div *ngFor="let user of users">
      <button (click)="selectUser(user)">{{ user.name }}</button>
    </div>
  `
})
export class UserListComponent {
  @Input() users: User[] = [];
  @Output() userSelected = new EventEmitter<User>();

  selectUser(user: User) {
    this.userSelected.emit(user);
  }
}
```

Expected output: complete React TSX using `<DhlButton>` from `@dhl-official/react-library`.

### Mode 2 — Full project migration (project path)

Provide the path to an Angular project root. The agent runs the complete 9-stage pipeline.

**Example prompt:**
```
Migrate the Angular project at C:\projects\my-angular-app to React
```

The agent will:
1. Scan the project for all Angular files
2. Run analysis, risk detection, and planning
3. Show you a summary (components found, risk score, chunk count)
4. Transform each chunk: Angular → React with DHL DUIL components
5. Generate tests and validate the output
6. Present a final migration report

### Mode 3 — Targeted operations

| Ask | What happens |
|---|---|
| `Analyse this Angular code: [code]` | Runs analyzer only → AnalysisReport |
| `What are the migration risks for [description]?` | Runs risk detection |
| `Refactor this React code: [code]` | Runs refactor only |
| `Validate this React code: [code]` | Runs validator → ValidationReport |

---

## DHL DUIL Compliance

All generated React code uses `@dhl-official/react-library` components. Raw HTML interactive elements are never produced.

| Angular / HTML | React DUIL output |
|---|---|
| `<button>` | `<DhlButton variant={DHL_BUTTON.VARIANT.PRIMARY}>` |
| `<input type="text">` | `<DhlInputField label="..." name="...">` |
| `<select>` | `<DhlSelect>` |
| `<textarea>` | `<DhlTextareaField>` |
| `<input type="checkbox">` | `<DhlCheckbox>` |

The Validator agent **fails** any output that uses raw HTML instead of DHL components.

---

## Running the System Tests

```powershell
& ".\.venv\Scripts\Activate.ps1"
python tests\test_v2_system.py
```

The system tests validate the pipeline infrastructure (orchestration, context engine, chunking, cache) in stub mode without requiring any API keys.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `adk: command not found` | Run `pip install google-adk>=2.1.0` and ensure the venv is activated |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt && pip install -e .` in the activated venv |
| `ConnectError` / `401 Unauthorized` | Check DHL VPN is connected (Apigee mode) or verify your API key in `config/.env` |
| Agent responds but doesn't convert code | Confirm `NGREACT_LLM_MODE` is set correctly — `stub` mode returns scripted responses only |
| `KeyError` on `{` in prompt | Brace-escaping issue; report to the team with the exact agent name |
| Port already in use | `netstat -ano \| Select-String ":8002"` → `Stop-Process -Id <PID> -Force` |
| `.env` settings not picked up | Ensure `.env` is at the project root (not inside `config/`). Settings load from `config/.env` first, then project root `.env`. |
| Context level escalation errors | Pipeline tried to escalate past Level 4. Usually caused by very large source files. Split into smaller files and retry. |

---

## Project Structure

```
Ang2React/
├── agent.py                        # ADK entry point — root NgReact agent
├── pyproject.toml                  # Package metadata
├── requirements.txt                # Python dependencies
├── .env                            # Active config (copy from config/) — NOT in Git
│
├── config/                         # All environment templates
│   ├── .env                        # Current working config
│   ├── .env.example                # Template — fill in and copy to project root
│   ├── .env.test                   # Stub mode — no keys needed
│   ├── .env.google_ai              # Google AI Studio config
│   └── .env.apigee_backup          # Backup Apigee config
│
├── prompts/
│   ├── v2_root_agent.md            # Root orchestrator system prompt
│   └── base_agent.md               # Shared guidelines (reference)
│
├── components/                     # Shared infrastructure
│   ├── tracing.py                  # ADK web trace display fix
│   ├── llm/                        # LLM factories (Apigee, Google AI, stub)
│   │   ├── rest_llm.py             # Apigee REST client (Vertex AI + Azure OpenAI)
│   │   ├── stub_llm.py             # Offline stub for testing
│   │   ├── llm.py                  # Google GenAI SDK factory
│   │   ├── models_registry.py      # Model ID registry
│   │   ├── models.prod.yaml        # Production model deployments
│   │   ├── models.test.yaml        # Test/sandbox model deployments
│   │   └── settings.py             # Env var loader (reads config/.env → .env)
│   └── logging/                    # Logging config (LOG_LEVEL env var)
│
├── tools/
│   ├── agents/                     # 9 sub-agent factories
│   │   ├── analyzer.py             # Stage 1 — Angular structure extraction
│   │   ├── risk_detection.py       # Stage 2 — Migration risk scoring
│   │   ├── migration_planner.py    # Stage 3 — Chunk-based execution plan
│   │   ├── state_migration.py      # Stage 4 — React state architecture
│   │   ├── transformer.py          # Stage 5 — Angular → React conversion
│   │   ├── refactor.py             # Stage 6 — Code quality + DHL DUIL
│   │   ├── test_generation.py      # Stage 7 — Vitest test suites
│   │   ├── validator.py            # Stage 8 — Quality gate
│   │   ├── report.py               # Stage 9 — Final migration report
│   │   ├── orchestration_tools.py  # Pipeline FunctionTools (chunks, artifacts, context)
│   │   └── prompts/                # System prompt for each agent (one .md per agent)
│   │
│   ├── functions/                  # Deterministic FunctionTools (no LLM)
│   │   ├── angular_parser.py       # Angular source pre-processor
│   │   ├── react_validator.py      # React static analysis (regex-based)
│   │   └── pipeline_tools.py       # Project scanner, file reader, complexity estimator
│   │
│   ├── pipeline/                   # Pipeline infrastructure
│   │   ├── models.py               # Typed artifact dataclasses (AnalysisReport, etc.)
│   │   ├── contracts.py            # Agent protocol + execution spec
│   │   ├── orchestrator.py         # MigrationOrchestrator (context + cache)
│   │   ├── context_engine.py       # Hierarchical context projection + escalation
│   │   ├── chunking.py             # MigrationChunker (dependency-ordered chunks)
│   │   └── cache.py                # In-memory result cache
│   │
│   └── knowledge/                  # Knowledge base search (Qdrant, optional)
│
├── ui/
│   └── app.js                      # Custom DHL-branded frontend
│
├── docs/
│   ├── STARTUP_GUIDE.md            # This file
│   └── V2_ARCHITECTURE.md          # Pipeline architecture deep-dive
│
└── tests/
    └── test_v2_system.py           # Pipeline infrastructure tests (stub mode)
```

---

## Port Reference

| Port | Service |
|---|---|
| `8002` | ADK Web UI — `http://127.0.0.1:8002` |

---

## Contact & Resources

| Resource | Link / Contact |
|---|---|
| DHL GenAI Gateway API key | Contact your **AI Champion** |
| DHL DUIL component docs | [docs.uilibrary.dhl](https://docs.uilibrary.dhl) |
| Google ADK documentation | [google.github.io/adk-docs](https://google.github.io/adk-docs) |
| Vitest documentation | [vitest.dev](https://vitest.dev) |
| React Testing Library | [testing-library.com/react](https://testing-library.com/docs/react-testing-library/intro) |
