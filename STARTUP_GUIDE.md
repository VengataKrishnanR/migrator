# NgReact V3 — Complete Startup Guide

## 🎯 What is NgReact V3?

**NgReact** is an AI-powered **Angular-to-React migration platform** that automates the conversion of Angular applications to React 18+ with full **DHL DUIL component compliance**.

### Key Features
✅ **Intelligent Analysis** — Understands Angular project structure, dependencies, complexity  
✅ **Full Automation** — 4-phase pipeline (Analysis → Transformation → Testing → Validation)  
✅ **DHL DUIL Compliance** — All generated code uses official DHL components  
✅ **Risk Scoring** — Identifies migration blockers and complexity  
✅ **Test Generation** — Creates Vitest + React Testing Library test suites  
✅ **Multiple Input Modes** — Paste code, upload .zip, or clone from Git  

---

## 📋 Prerequisites

### System Requirements
- **Python 3.11+** (3.13 recommended)
- **Git**
- **Node.js 18+** (for running migrated React projects)

### DHL Access Requirements
- ✅ DHL corporate network access (office LAN or DHL VPN)
- ✅ Valid **APIGEE_API_KEY** (get from your DHL AI Champion)

### Browser
- Chrome, Firefox, Safari, or Edge (any modern browser)

---

## 🚀 Installation & Setup

### Step 1: Navigate to Project Directory

```powershell
cd C:\Users\<YourUsername>\Downloads\Ang2React_2\Ang2React
```

Or clone if you don't have it:
```bash
git clone <your-repo-url>
cd Ang2React
```

### Step 2: Create Python Virtual Environment

**PowerShell:**
```powershell
python -m venv .venv
& ".\.venv\Scripts\Activate.ps1"
```

**macOS / Linux / WSL:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Verify activation:** You should see `(.venv)` in your prompt.

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

This installs:
- Google ADK (Agent Development Kit)
- FastAPI & Uvicorn (server)
- python-dotenv (environment loading)
- httpx (HTTP client)
- pydantic (data validation)

### Step 4: Configure API Key in .env

The `.env` file is already configured for Apigee. You need to add your API key:

**Edit `.env` file:**

1. Open `.env` in your editor
2. Find this line:
   ```env
   APIGEE_API_KEY=<paste-your-dhl-apigee-api-key-here>
   ```
3. Replace `<paste-your-dhl-apigee-api-key-here>` with your actual API key:
   ```env
   APIGEE_API_KEY=b0bb43fdf2fb8b2a4175cc3dc60524469f8b06f24060d636de4f67fa9c1a9c64
   ```
4. Save the file (Ctrl+S)

**Get your API key:**
- Contact your DHL AI Champion
- Ask for your APIGEE_API_KEY
- Copy the full key value

**For Testing (Stub Mode - No API Key Needed):**

If you don't have an Apigee key yet, you can test locally:

1. Edit `.env`:
   ```env
   NGREACT_LLM_MODE=stub
   ```
2. Set a placeholder API key (stub mode doesn't validate it):
   ```env
   APIGEE_API_KEY=test-key
   ```
3. The app will use scripted responses instead of real LLM calls

### Step 5: Start the Server

The server includes both the **API** and the **custom frontend UI**.

**PowerShell:**
```powershell
& ".\.venv\Scripts\Activate.ps1"
python -m uvicorn server.app:app --port 8002 --host 127.0.0.1
```

**Bash / WSL / macOS:**
```bash
source .venv/bin/activate
python -m uvicorn server.app:app --port 8002 --host 127.0.0.1
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8002
INFO:     Application startup complete
```

### Step 6: Open the Custom Frontend in Browser

Navigate to: **http://127.0.0.1:8002**

The custom UI is automatically served from the `/ui` directory. You should see:

**Left Panel:**
- 📋 Paste Angular code
- 📁 Upload ZIP projects
- 🔗 Clone from Git
- 💬 Chat section (unlocks after providing code)

**Right Panel:**
- Pipeline visualization (4 phases + 2 gates)
- Output area (reports, approvals, results)

**No separate UI server needed** — everything runs from the same port 8002

---

## 🎨 Custom Frontend UI

The NgReact application includes a **built-in custom frontend** that's automatically served along with the API.

### What's Included

**Frontend Files (in `/ui` directory):**
- `index.html` — Main UI template (DHL-branded, responsive)
- `app.js` — Interactive frontend logic (paste, upload, chat, pipeline)
- `styles.css` — DHL design system styling

### Access the Frontend

Once the server is running:
1. Open browser: **http://127.0.0.1:8002**
2. The custom UI loads automatically
3. No separate frontend server needed

### Features

✅ **Real-time pipeline visualization** — See all 4 phases + 2 gates
✅ **Multi-input modes** — Paste, upload ZIP, or clone from Git
✅ **Interactive chat** — Ask questions about your code
✅ **Approval gates** — Review plans before proceeding
✅ **File viewer** — Preview generated React components
✅ **Download results** — Get deliverable.zip directly

---

## 🛡️ Safety & Orchestration

### Agent Orchestration
The root agent follows a **strict orchestration protocol** (defined in `prompts/root_agent_v3.md`):

- **Phase 1:** Analysis & planning (16 sequential steps)
- **Gate A:** Human approval required
- **Phase 2:** Transformation loop (get chunk → transform → mark done)
- **Phase 3:** Validation & reporting (5 sequential steps)
- **Gate B:** Human approval required
- **Phase 4:** Delivery & completion

### Loop Safeguard
**Max 200 tool calls per pipeline:**
- Prevents infinite loops
- Automatically stops and reports error if exceeded
- Typical projects use 30-70 tool calls
- Large projects (50+ chunks) may use 150-200

**If limit exceeded:**
```
⚠️ SAFETY LIMIT REACHED: Tool called 201 times (max 200).
This usually means the agent is stuck in a loop.
STOPPING to prevent runaway execution.
```

### Error Handling
- ✅ Clear error messages if something fails
- ✅ No silent failures or retries
- ✅ Stops at gate approvals (no auto-proceeding)
- ✅ Reports blockers immediately

---

## ✨ Quick Start Examples

### Example 1: Analyze a Single Component (30 seconds)

1. **Paste Angular code** in the "Paste" tab:
```typescript
import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-hello',
  template: `<h1>Hello {{ name }}!</h1>`
})
export class HelloComponent {
  @Input() name: string = 'World';
}
```

2. **Press Enter** or click "Send"

3. **Agent analyzes and converts to React:**
```typescript
export interface HelloProps {
  name?: string;
}

export const Hello: React.FC<HelloProps> = ({ name = 'World' }) => {
  return <h1>Hello {name}!</h1>;
};
```

### Example 2: Full Project Migration (5-15 minutes)

1. **Prepare your Angular project:**
   - Exclude `node_modules/` and `dist/` to reduce file size
   - Create a `.zip` file of your project

2. **Click "Upload" tab** and drag/drop the ZIP

3. **Click "Start Migration"** button

4. **Pipeline runs automatically:**
   - Phase 1: Analyzes structure (30-60s)
   - **Gate A:** Review plan, click "Approve"
   - Phase 2: Converts code chunks (2-5 min)
   - Phase 3: Generates tests (1-2 min)
   - Phase 4: Validates output (30s)
   - **Gate B:** Review results, click "Approve"

5. **Download the results** as `deliverable.zip`

---

## 🔧 Configuration Files

### `.env` (Current Configuration)

Located in project root. Already configured for Apigee:

```env
# ── LLM mode ──────────────────────────────────────────
NGREACT_LLM_MODE=apigee

# ── DHL GenAI Gateway (Apigee) ────────────────────────
# API key is read from environment variable (for security)
APIGEE_PROXY_URL_PRODUCTION=https://apihub-sandbox.eu.dhl.com/genai-sensitive
APIGEE_PROXY_URL_TESTING=https://apihub-sandbox.eu.dhl.com/genai-sensitive
APIGEE_ENVIRONMENT=testing

# ── Model deployment IDs ──────────────────────────────
APIGEE_DEFAULT_AZURE_OPENAI_MODEL=gpt-4o-mini-2024-07-18-eudz
APIGEE_DEFAULT_EMBEDDING_MODEL=text-embedding-3-large-1-eudz
APIGEE_DEFAULT_VERTEX_MODEL=

# ── API settings ──────────────────────────────────────
AZURE_API_VERSION=2025-03-01-preview
APIGEE_STREAMING_ENABLED=false
APIGEE_TIMEOUT_SECONDS=60

# ── Logging ───────────────────────────────────────────
LOG_LEVEL=INFO

# ── Optional: Qdrant knowledge base ───────────────────
QDRANT_URL=
QDRANT_API_KEY=
```

### Project Structure

```
Ang2React/
├── agent.py                    # Root ADK agent entry point
├── server/                     # FastAPI server
│   ├── app.py                 # Main application
│   ├── config.py              # Server config
│   ├── phase_runner.py        # Migration pipeline executor
│   └── agent_invoker.py       # Agent invocation logic
├── components/                # Shared components
│   ├── llm/                   # LLM configuration & factories
│   │   ├── settings.py        # Apigee settings loader
│   │   ├── rest_llm.py        # REST-based LLM client
│   │   └── models_registry.py # Model deployment registry
│   ├── logging/               # Logging setup
│   └── tracing/               # Tracing/observability
├── tools/                     # Migration tools
│   ├── agents/                # 9 specialized migration agents
│   ├── pipeline/              # Pipeline orchestration
│   ├── functions/             # Helper functions
│   └── workflow/              # Workflow state machine
├── prompts/                   # Agent system prompts
│   └── base_agent.md          # Shared guidelines
├── config/                    # Environment configs
│   ├── .env.apigee           # Apigee template
│   └── .env.example          # Example config
├── tests/                     # Test suite (V3 tests)
├── docs/                      # Documentation
└── requirements.txt           # Python dependencies
```

---

## 🏃 Common Commands

### Start the Server
```bash
python -m uvicorn server.app:app --port 8002
```

### Run Tests
```bash
pytest tests/ -v
```

### Check API Health
```bash
curl http://127.0.0.1:8002/api/health
```

### View Application Logs
Logs appear in the terminal where you ran the server. Look for:
- ✅ `INFO` — Normal operations
- ⚠️ `WARNING` — Configuration issues
- ❌ `ERROR` — Problems that need fixing

### Deactivate Virtual Environment
```bash
deactivate
```

---

## 🔑 Getting Your DHL Apigee API Key

### Step 1: Contact Your DHL AI Champion

Ask your manager or AI lead for:
- **APIGEE_API_KEY** — The Bearer token for DHL GenAI Gateway

### Step 2: Add Key to `.env`

Once you have the key, add it to the `.env` file:

**Edit `.env`:**
```env
APIGEE_API_KEY=your-actual-key-here
```

Example:
```env
APIGEE_API_KEY=b0bb43fdf2fb8b2a4175cc3dc60524469f8b06f24060d636de4f67fa9c1a9c64
```

Save the file.

### Step 3: Verify Network Access (Optional)

Test that you can reach the gateway:

**PowerShell:**
```powershell
$key = Get-Content .env | Select-String "APIGEE_API_KEY=" | ForEach-Object { $_.Line.Split('=')[1] }
Invoke-WebRequest -Uri "https://apihub-sandbox.eu.dhl.com/genai-sensitive" -Headers @{"Authorization"="Bearer $key"} -ErrorAction SilentlyContinue
```

If you get a 404 or 200, you have network access. ✅

### Step 4: Start the Server

```bash
python -m uvicorn server.app:app --port 8002
```

The app will read the API key from `.env` automatically.

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'google.adk'"

**Cause:** Dependencies not installed  
**Fix:**
```bash
pip install -r requirements.txt
pip install -e .
```

### "APIGEE_API_KEY environment variable is not set"

**Cause:** API key not in environment  
**Fix:**

**PowerShell:**
```powershell
$env:APIGEE_API_KEY = "your-key"
echo $env:APIGEE_API_KEY  # Verify it's set
```

**Bash:**
```bash
export APIGEE_API_KEY="your-key"
echo $APIGEE_API_KEY  # Verify it's set
```

### "Address already in use :8002"

**Cause:** Another process is using port 8002  
**Fix:**

**PowerShell:**
```powershell
# Find process
Get-NetTCPConnection -LocalPort 8002 | Select OwningProcess
# Kill it
Stop-Process -Id <PID> -Force
```

**Bash:**
```bash
lsof -i :8002
kill -9 <PID>
```

### "The request originated from an unauthorized network"

**Cause:** Not on DHL VPN  
**Fix:**
- Ensure you're connected to DHL corporate VPN or office LAN
- Check with your IT team if the issue persists

### "Timeout: Request took longer than 120 seconds"

**Cause:** Large project or network slowness  
**Fix:**
- Exclude `node_modules/` from uploads
- Retry with a smaller subset of files first
- Check network connectivity

### Server won't respond to requests

**Cause:** Server crashed or port binding failed  
**Fix:**
```bash
# Stop current server (Ctrl+C in terminal)
# Check logs for errors
# Verify port is free
# Restart server
python -m uvicorn server.app:app --port 8002 --reload
```

---

## 📊 Understanding the Migration Phases

### Phase 1: Discovery & Planning (30-60 seconds)

**What happens:**
- Analyzes Angular project structure
- Identifies components, services, routes, pipes, guards
- Scores migration risks (forms, lazy loading, custom directives, etc.)
- Estimates effort and complexity
- Designs React state management strategy

**Output:** Phase 1 Report with:
- Components found: N
- Services found: N
- Risk score: X.X (low/medium/high)
- Estimated effort: ~N hours
- State strategy: Context API / Zustand / hooks

**Gate A:** You review and approve to proceed to Phase 2

### Phase 2: Transformation & Testing (2-5 minutes per chunk)

**What happens:**
- Converts Angular components → React components
- Migrates services → custom hooks
- Converts templates → JSX
- Applies DHL DUIL components (no raw HTML)
- Generates test suites (Vitest + React Testing Library)

**Output:** React source files + test files

**No gate here** — Pipeline continues automatically

### Phase 3: Validation (30-60 seconds)

**What happens:**
- Validates TypeScript compilation
- Checks React hooks rules
- Verifies DHL DUIL compliance
- Generates quality score

**Output:** Validation Report with:
- TypeScript errors: 0
- ESLint warnings: N
- React violations: 0
- Quality score: 95/100

### Phase 4: Final Report

**What happens:**
- Aggregates all artifacts
- Generates migration summary
- Lists all generated files
- Provides next steps

**Gate B:** Final approval before download

---

## 📝 Best Practices

### Before Migration
✅ **DO:**
- Ensure Angular project compiles without errors
- Test project locally
- Commit changes to Git (backup)
- Exclude `node_modules/` and `dist/` from uploads
- Note any custom third-party dependencies

❌ **DON'T:**
- Migrate Angular 1.x projects (too old)
- Migrate without backing up
- Upload projects > 200 MB compressed

### During Migration
✅ **DO:**
- Review Phase 1 report carefully
- Read agent notes at gates
- Monitor the terminal for errors

❌ **DON'T:**
- Close browser mid-migration
- Restart server during migration
- Ignore validation warnings

### After Migration
✅ **DO:**
- Extract deliverable.zip
- Run `npm install`
- Run tests: `npm test`
- Review generated code
- Test all features manually
- Update package.json dependencies

❌ **DON'T:**
- Deploy without testing
- Ignore ESLint warnings
- Skip code review

---

## 🎓 Example: Migrate a Real Project

### Step-by-Step Example

1. **Prepare project**
   ```bash
   cd my-angular-app
   npm ci  # Install deps
   ng build  # Verify it compiles
   # Exclude node_modules and dist
   zip -r ../my-app.zip . -x "node_modules/*" "dist/*"
   ```

2. **Upload to NgReact**
   - Open http://127.0.0.1:8002
   - Click "Upload" tab
   - Drag & drop `my-app.zip`

3. **Start migration**
   - Click "Start Migration" button
   - Wait for Phase 1 (30-60 seconds)

4. **Review Phase 1**
   - Read the report
   - Check: Components found, risk score, effort estimate
   - Click "Approve" button

5. **Wait for Phase 2-4**
   - Automation runs (2-5 minutes for medium projects)
   - Terminal shows progress

6. **Review & Approve Phase 4**
   - Click "Approve" after seeing validation results

7. **Download results**
   - Click "Download deliverable.zip"

8. **Integrate into React project**
   ```bash
   cd my-react-app
   unzip ../deliverable.zip
   npm install
   npm test
   npm run dev
   ```

---

## 📚 Next Steps

### 1. Verify Setup (2 minutes)
```bash
# Activate venv
& ".\.venv\Scripts\Activate.ps1"

# Start server
python -m uvicorn server.app:app --port 8002

# Open browser
# Navigate to http://127.0.0.1:8002
```

### 2. Test with Sample Code (5 minutes)
- Paste a small Angular component
- Ask the agent to analyze it
- Review the React conversion

### 3. Migrate Your First Project (15 minutes)
- Upload a real Angular project
- Go through all 4 phases
- Download and review results

### 4. Integrate Results (30+ minutes)
- Extract deliverable.zip
- Install dependencies
- Run tests
- Deploy to your React app

---

## 🆘 Getting Help

### Check These First
1. ✅ Is the server running? (check terminal)
2. ✅ Is the API key set? (`echo $env:APIGEE_API_KEY`)
3. ✅ Are you on DHL VPN? (if using Apigee)
4. ✅ Is the port available? (not already in use)

### Review Documentation
- **Architecture:** `docs/V3_ARCHITECTURE_PLAN.md`
- **Build Status:** `docs/V3_BUILD_STATUS.md`
- **Troubleshooting:** This guide (section above)

### Common Questions

**Q: Can I use OpenAI instead of Apigee?**  
A: Yes, but it requires additional setup. Contact your manager for approval.

**Q: How long does a migration take?**  
A: Depends on project size:
- Small (1-10 components): 5 minutes
- Medium (10-50 components): 10-15 minutes
- Large (50+ components): 20-30 minutes

**Q: Can I migrate TypeScript to JavaScript?**  
A: Generated code is TypeScript. You can convert after if needed.

**Q: What if the agent makes mistakes?**  
A: Review the generated code. The agent is 95%+ accurate but review is recommended.

**Q: Is my code secure?**  
A: Code goes only to DHL Apigee (controlled by DHL). Not shared externally.

---

## 🛑 Shutting Down the Application

When you're done using NgReact, follow these steps to properly shut down the application:

### Step 1: Stop the Server

**If running in PowerShell or terminal:**
Press `Ctrl+C` in the terminal window where the server is running.

**Expected output:**
```
INFO:     Shutdown complete.
```

### Step 2: Deactivate Virtual Environment (Optional)

If you activated the virtual environment, you can deactivate it:

**PowerShell:**
```powershell
deactivate
```

**Bash / WSL / macOS:**
```bash
deactivate
```

### Step 3: Verify Shutdown

Check that no Python processes are running:

**PowerShell:**
```powershell
Get-Process | Where-Object { $_.ProcessName -eq "python" }
```

**Bash / Linux / macOS:**
```bash
ps aux | grep python
```

If no processes are shown, the application is fully shut down. ✅

### Cleanup (Optional - To Free Disk Space)

Remove the virtual environment when you don't need it:

**PowerShell:**
```powershell
Remove-Item -Recurse -Force .venv
```

**Bash / macOS / Linux:**
```bash
rm -rf .venv
```

To reinstall later, just run `python -m venv .venv` again.

---

## 🎉 You're Ready!

Your NgReact setup is complete. Start migrating Angular to React today! 

**Questions?** Check the troubleshooting section or contact your DHL AI Champion.

**Happy migrating! 🚀**
