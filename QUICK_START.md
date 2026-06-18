# NgReact V3 — Quick Start (5 Minutes)

## 🔧 One-Time Setup

### 1. Create Virtual Environment
```powershell
python -m venv .venv
& ".\.venv\Scripts\Activate.ps1"
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
pip install -e .
```

### 3. Set API Key in .env
Open `.env` file and replace:
```env
APIGEE_API_KEY=<paste-your-dhl-apigee-api-key-here>
```
With your actual key:
```env
APIGEE_API_KEY=your-actual-key-from-ai-champion
```
Save the file.

### 4. Start Server
```bash
python -m uvicorn server.app:app --port 8002
```

### 5. Open Custom Frontend
Navigate to: **http://127.0.0.1:8002**

The custom UI is automatically served. No separate frontend server needed!

✅ **Done!** You're ready to migrate.

---

## 🎨 What You Get

The custom frontend includes:
- **Left Panel:** Paste code, upload ZIP, Git integration, chat
- **Right Panel:** Pipeline visualization, approval gates, output
- **DHL Branding:** Official DHL design system
- **Real-time Updates:** See migration progress live

---

## 🎨 What You Get

The custom frontend includes:
- **Left Panel:** Paste code, upload ZIP, Git integration, chat
- **Right Panel:** Pipeline visualization, approval gates, output
- **DHL Branding:** Official DHL design system
- **Real-time Updates:** See migration progress live

---

## 📝 Quick Usage

### Option A: Analyze a Single Component
1. Paste Angular code in "Paste" tab
2. Click "Send"
3. Get React conversion + analysis

**Time:** 30 seconds

### Option B: Migrate Full Project
1. Upload project ZIP (exclude `node_modules/` & `dist/`)
2. Click "Start Migration"
3. Approve Phase 1 & Phase 4 gates
4. Download `deliverable.zip`

**Time:** 5-15 minutes

---

## 🛡️ Safety Features

✅ **Loop Limit Safeguard** — Max 200 tool calls per pipeline  
✅ **Orchestration Checks** — Prevents infinite loops  
✅ **Gate Approvals** — No phase skipping without approval  
✅ **Error Handling** — Clear error messages if something fails  

If agent exceeds 200 tool calls, it automatically stops with an error message.

---

## ⚡ Essential Commands

| Task | Command |
|------|---------|
| Activate venv | `. .\.venv\Scripts\Activate.ps1` (PowerShell) / `source .venv/bin/activate` (Bash) |
| Start server | `python -m uvicorn server.app:app --port 8002` |
| Run tests | `pytest tests/ -v` |
| Check API health | `curl http://127.0.0.1:8002/api/health` |
| Set API key | `$env:APIGEE_API_KEY = "key"` (PowerShell) / `export APIGEE_API_KEY="key"` (Bash) |
| Deactivate venv | `deactivate` |

---

## 🆘 Quick Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: google.adk` | `pip install -r requirements.txt && pip install -e .` |
| `APIGEE_API_KEY not set` | `$env:APIGEE_API_KEY = "your-key"` |
| `Address already in use :8002` | `Stop-Process -Id <PID> -Force` |
| `Unauthorized network` | Ensure DHL VPN connected |
| `Request timeout` | Check network, project size too large, or slow API |

---

## 📊 Phase Overview

```
Upload/Paste Code
    ↓
Phase 1: Analysis (30-60s) → Gate A: Review & Approve
    ↓
Phase 2-3: Transform & Test (2-5 min)
    ↓
Phase 4: Validate (30s) → Gate B: Review & Approve
    ↓
Download Deliverable.zip
```

---

## 📚 Full Documentation

For detailed setup, troubleshooting, and best practices, see: **`STARTUP_GUIDE.md`**

---

## 💡 Pro Tips

✅ Exclude `node_modules/` and `dist/` from uploads (reduces size 80%)  
✅ Test your Angular project compiles before migration  
✅ Review Phase 1 report carefully before approving  
✅ Check generated code for DHL DUIL compliance  
✅ Run `npm test` after integration  

---

**Ready? Open http://127.0.0.1:8002 and start migrating! 🚀**
