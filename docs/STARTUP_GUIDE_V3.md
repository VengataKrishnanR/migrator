# NgReact V3 — Startup Guide

## ⚠️ Updated Documentation

This guide has been **updated and moved** to the project root.

### 📖 Read These Instead:

1. **START.md** — Quick orientation (2 min)
2. **QUICK_START.md** — 5-minute setup
3. **STARTUP_GUIDE.md** — Complete guide with examples
4. **TROUBLESHOOTING.md** — FAQ & problem solving

All documentation now reflects:
- ✅ V3-only architecture (v2 removed)
- ✅ DHL Apigee as primary LLM backend
- ✅ API key in `.env` file (not environment variables)
- ✅ Custom frontend UI included with server
- ✅ No separate UI server needed

---

## 🚀 Quick Start

```powershell
# 1. Create venv
python -m venv .venv
& ".\.venv\Scripts\Activate.ps1"

# 2. Install deps
pip install -r requirements.txt
pip install -e .

# 3. Add API key to .env
# Edit .env and replace: APIGEE_API_KEY=your-key-here

# 4. Start server
python -m uvicorn server.app:app --port 8002

# 5. Open browser
# http://127.0.0.1:8002
```

---

## 📚 For Complete Instructions

→ **Open `STARTUP_GUIDE.md` in the project root**

---

Last Updated: 2026-06-11  
Version: V3 (Apigee)
