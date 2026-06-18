# 🚀 START HERE — NgReact V3 Setup

Welcome! This is your **complete startup guide** for NgReact V3.

## ⏱️ Choose Your Path

### 🏃 **5-Minute Quick Start**
For experienced developers who want to jump in:
→ **Read:** `QUICK_START.md`

### 📚 **15-Minute Complete Setup**  
For detailed step-by-step instructions:
→ **Read:** `STARTUP_GUIDE.md`

### 🔧 **Troubleshooting & FAQ**
When something goes wrong:
→ **Read:** `TROUBLESHOOTING.md`

---

## ⚡ The Absolute Minimum (4 Steps)

### Step 1: Create & Activate Virtual Environment
```powershell
python -m venv .venv
& ".\.venv\Scripts\Activate.ps1"
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
pip install -e .
```

### Step 3: Add API Key to `.env`
```bash
# Open .env file
# Find: APIGEE_API_KEY=<paste-your-dhl-apigee-api-key-here>
# Replace with your actual key from your DHL AI Champion
```

### Step 4: Start Server
```bash
python -m uvicorn server.app:app --port 8002
```

### 5. Open Browser
```
http://127.0.0.1:8002
```

✅ **Done!** Custom frontend loads automatically.

---

## 📋 What You Need

- ✅ Python 3.11+ (3.13 recommended)
- ✅ DHL Apigee API Key (from your AI Champion)
- ✅ DHL VPN or office network access
- ✅ Modern web browser

---

## 🛡️ Built-in Safety Features

✅ **Loop Limit Safeguard** (max 200 tool calls per pipeline)  
✅ **Strict Orchestration** (Phase 1→2→3→4, no skipping)  
✅ **Approval Gates** (Gate A after Phase 1, Gate B after Phase 4)  
✅ **Error Handling** (stops on errors, no silent failures)  
✅ **Clear Messages** (tells you what's happening at each step)  

The agent will **never loop forever** — it stops at 200 tool calls with a clear error message.

---

## 🎯 Next Steps

**New to the project?**
1. Read `STARTUP_GUIDE.md` for complete context
2. Get your API key from your DHL AI Champion
3. Follow the 4 steps above
4. Start migrating!

**Already familiar?**
1. Use `QUICK_START.md` as a reference
2. Add your API key to `.env`
3. Start the server
4. Open http://127.0.0.1:8002

**Something broken?**
1. Check `TROUBLESHOOTING.md` first (includes Issue 8 about loop limit)
2. Review error messages in terminal
3. Contact your DHL AI Champion

---

## 📚 Full Documentation

| File | Content | Read Time |
|------|---------|-----------|
| **START.md** (you are here) | Quick orientation | 2 min |
| **QUICK_START.md** | 5-minute setup | 5 min |
| **STARTUP_GUIDE.md** | Complete guide + examples | 15 min |
| **TROUBLESHOOTING.md** | FAQ + problem solving | 10 min |

---

## 🎨 What You Get

Once running, you have:

**Frontend UI** (at http://127.0.0.1:8002):
- Paste Angular code directly
- Upload ZIP files
- Clone from Git
- Ask questions about code
- See real-time migration progress
- Approve/review migration plans
- Download React results

**API Endpoints** (at http://127.0.0.1:8002/api):
- Start migrations programmatically
- Query job status
- Get artifacts
- Manage approvals

---

## ❓ FAQ

**Q: Do I need a separate UI server?**  
A: No! The custom frontend is served automatically with the API on port 8002.

**Q: Where do I get the Apigee API key?**  
A: Contact your DHL AI Champion or manager.

**Q: Can I use OpenAI instead?**  
A: Yes, but requires approval. See `STARTUP_GUIDE.md`.

**Q: How long does a migration take?**  
A: 5-15 minutes depending on project size.

**Q: Is my code secure?**  
A: Yes. Code stays on DHL infrastructure (Apigee), not shared externally.

---

## 🚨 Stuck?

1. **Check**: `TROUBLESHOOTING.md`
2. **Review**: Terminal output for error messages
3. **Verify**: API key is set in `.env`
4. **Confirm**: You're on DHL VPN
5. **Contact**: Your DHL AI Champion

---

## 🎉 You're Ready!

Your environment is clean, docs are updated, and Apigee is configured.

**Next action:** Pick your path above and follow the instructions. You'll have a working Angular→React migration platform in minutes.

**Happy migrating! ⚛️**
