# NgReact V3 — Troubleshooting & FAQ

## 🔴 Common Issues & Solutions

### Issue 1: "ModuleNotFoundError: No module named 'google.adk'"

**Symptoms:**
```
ModuleNotFoundError: No module named 'google.adk'
```

**Causes:**
- Dependencies not installed
- Wrong virtual environment activated

**Solutions:**

✅ **Option A: Reinstall dependencies**
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

✅ **Option B: Verify venv is activated**
```powershell
# Check prompt — should start with (.venv)
# If not, activate:
& ".\.venv\Scripts\Activate.ps1"
```

✅ **Option C: Create fresh venv**
```bash
# Remove old one
Remove-Item .venv -Recurse -Force

# Create new
python -m venv .venv
& ".\.venv\Scripts\Activate.ps1"
pip install -r requirements.txt
pip install -e .
```

---

### Issue 2: "APIGEE_API_KEY is not set"

**Symptoms:**
```
Error: APIGEE_API_KEY is not set
```

**Causes:**
- API key not added to `.env` file
- `.env` file not found
- Typo in API key line
- Using placeholder text instead of real key

**Solutions:**

✅ **Edit .env file and add your API key**
```bash
# Open .env in your editor
# Find this line:
APIGEE_API_KEY=<paste-your-dhl-apigee-api-key-here>

# Replace with your actual key:
APIGEE_API_KEY=b0bb43fdf2fb8b2a4175cc3dc60524469f8b06f24060d636de4f67fa9c1a9c64

# Save the file
```

✅ **Verify .env file has correct settings**
```bash
# Check .env exists
ls .env
# Should return: .env

# Check API key is set
cat .env | grep APIGEE_API_KEY
# Should show: APIGEE_API_KEY=<your-actual-key>
# NOT: APIGEE_API_KEY=<paste-your-dhl...>
```

✅ **Make sure you're using the REAL API key**
```bash
# ❌ WRONG - using placeholder
APIGEE_API_KEY=<paste-your-dhl-apigee-api-key-here>

# ✅ CORRECT - using real key
APIGEE_API_KEY=b0bb43fdf2fb8b2a4175cc3dc60524469f8b06f24060d636de4f67fa9c1a9c64
```

---

### Issue 3: "Address already in use :8002"

**Symptoms:**
```
OSError: [WinError 10048] Only one usage of each socket address
Address already in use :8002
```

**Causes:**
- Another server running on port 8002
- Previous server didn't shut down cleanly
- Another application using the port

**Solutions:**

✅ **PowerShell: Kill process on port 8002**
```powershell
# Find process using port
Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue | Select-Object OwningProcess

# Kill it (replace <PID> with the process ID)
Stop-Process -Id <PID> -Force

# Or kill all Python processes (nuclear option)
Get-Process python | Stop-Process -Force

# Try starting server again
python -m uvicorn server.app:app --port 8002
```

✅ **Bash/WSL: Kill process on port 8002**
```bash
# Find process
lsof -i :8002

# Kill it (replace <PID>)
kill -9 <PID>

# Start server
python -m uvicorn server.app:app --port 8002
```

✅ **Use a different port**
```bash
python -m uvicorn server.app:app --port 8003
# Then access: http://127.0.0.1:8003
```

---

### Issue 4: "The request originated from an unauthorized network"

**Symptoms:**
```
HTTP 403 Forbidden: The request originated from an unauthorized network
```

**Causes:**
- Not connected to DHL VPN
- Not on DHL office network
- VPN connection dropped

**Solutions:**

✅ **Verify VPN connection**
```bash
# PowerShell
Get-VpnConnection

# Should show your DHL VPN with "Connected" status
```

✅ **Reconnect to VPN**
- Open VPN client
- Select DHL VPN
- Click "Connect"
- Wait for "Connected" status

✅ **Test network connectivity**
```powershell
# Ping DHL gateway
Test-NetConnection -ComputerName "apihub-sandbox.eu.dhl.com" -Port 443

# Should show: TcpTestSucceeded : True
```

✅ **Verify API key is valid**
```powershell
# Get API key from AI Champion
# Verify it's set correctly
echo $env:APIGEE_API_KEY

# Should not be empty
```

---

### Issue 5: "Request timed out (120 seconds)"

**Symptoms:**
```
Request timed out (120 seconds)
Agent did not respond within 120 seconds
```

**Causes:**
- Project is very large
- Network is slow
- API is experiencing issues
- Agent encountered an error

**Solutions:**

✅ **Try a smaller project first**
- Test with a single component
- Gradually increase size

✅ **Optimize project size**
```bash
# Exclude large directories
# Don't include:
# - node_modules/ (usually 500+ MB)
# - dist/ (build output)
# - .git/ (version history)
# - .venv/ (dependencies)

# Create clean zip
zip -r my-app.zip . \
  --exclude "node_modules/*" \
  "dist/*" \
  ".git/*" \
  ".venv/*" \
  "*.log"
```

✅ **Check network**
```powershell
# Test connection to Apigee
Invoke-WebRequest -Uri "https://apihub-sandbox.eu.dhl.com/genai-sensitive" `
  -Headers @{"Authorization"="Bearer $env:APIGEE_API_KEY"} `
  -TimeoutSec 10

# Should get 404 or successful response (not timeout)
```

✅ **Increase timeout**
Edit `.env`:
```env
APIGEE_TIMEOUT_SECONDS=300  # 5 minutes instead of 60 seconds
```

✅ **Check server logs**
- Look at terminal running server
- See if agent returned an error
- Common issues: Invalid Angular project, syntax errors

---

### Issue 6: "No such file or directory: '.venv/Scripts/Activate.ps1'"

**Symptoms:**
```
No such file or directory: '.venv/Scripts/Activate.ps1'
```

**Causes:**
- Venv not created yet
- Wrong path/directory

**Solutions:**

✅ **Create venv first**
```powershell
# Verify you're in project root
pwd
# Should show: .../Ang2React

# Create venv
python -m venv .venv

# Activate
& ".\.venv\Scripts\Activate.ps1"
```

✅ **Verify venv exists**
```powershell
ls .venv\Scripts\
# Should list: Activate.ps1, python.exe, pip.exe, etc.
```

---

### Issue 7: "Invalid deployment ID"

**Symptoms:**
```
Error: Deployment ID 'gpt-4o-mini-2024-07-18-eudz' not found in registry
```

**Causes:**
- Model registry is out of date
- Deployment ID doesn't exist
- Wrong environment setting

**Solutions:**

✅ **Check model registry**
```bash
cat models.prod.yaml  # or models.test.yaml
# Should list available deployment IDs
```

✅ **Verify APIGEE_ENVIRONMENT setting**
```bash
echo $env:APIGEE_ENVIRONMENT
# Should be: production or testing
```

✅ **Use correct model ID**
Edit `.env`:
```env
# Check which models are available in your environment
# Common ones:
APIGEE_DEFAULT_AZURE_OPENAI_MODEL=gpt-4o-mini-2024-07-18-eudz
APIGEE_DEFAULT_EMBEDDING_MODEL=text-embedding-3-large-1-eudz
```

---

### Issue 8: "SAFETY LIMIT REACHED: Tool called 201 times (max 200)"

**Symptoms:**
```
⚠️ SAFETY LIMIT REACHED: Tool called 201 times (max 200).
This usually means the agent is stuck in a loop.
STOPPING to prevent runaway execution.
```

**Causes:**
- Phase 2 chunk loop not terminating properly
- Agent stuck calling tools repeatedly
- Project has too many chunks (>50)
- Orchestration error in agent flow

**Solutions:**

✅ **Understand the limit**
```
Expected tool calls per scenario:
- Small project (1-10 components): ~30 calls ✅
- Medium project (10-30 components): ~60 calls ✅
- Large project (30-50 components): ~150 calls ✅
- Very large project (50+ components): May hit limit
```

✅ **Restart with smaller project**
```bash
# Start with a single component first
# Verify it works
# Then try the full project
```

✅ **Check chunk completion**
If using API directly, verify `mark_chunk_done()` is being called:
```python
# Each chunk must be marked as done
mark_chunk_done(chunk_id, result_json)

# Then get_next_chunk() should return the next chunk
# Or {'done': True} when finished
```

✅ **Review server logs**
Look at terminal output for:
- Which phase is running
- How many chunks are being processed
- Whether chunks are completing properly

✅ **If problem persists**
- Check your Angular project for issues
- Verify it compiles without errors
- Try with a simpler Angular project first
- Contact your DHL AI Champion

**The loop limit is a safety feature** — it prevents runaway execution but indicates something went wrong in the pipeline. Always investigate the root cause.

---

## ❓ FAQ (Frequently Asked Questions)

### Q: What's the minimum Angular version I need?
**A:** Angular 12+. Older versions (1.x-5.x) are not supported.

### Q: Can I use my own OpenAI key instead of Apigee?
**A:** Yes, but requires special setup. Contact your DHL AI Champion for approval. Instructions in `STARTUP_GUIDE.md`.

### Q: How much does migration cost?
**A:** Using DHL Apigee is free (included in DHL infrastructure). If using external OpenAI, costs ~$0.02-$0.10 per project.

### Q: What file types are supported?
**A:** 
- ✅ `.ts` (TypeScript)
- ✅ `.js` (JavaScript)
- ✅ `.html` (Templates)
- ✅ `.css` / `.scss` (Styles)

### Q: Can I cancel a migration in progress?
**A:** 
- ✅ **Before Gate A:** Click "Cancel migration"
- ✅ **After Gate A, before Gate B:** Click "Cancel" button
- ❌ **After Gate B:** Migration is locked; no cancellation

### Q: Can I re-run a migration?
**A:** Yes! Each migration gets a unique job ID. Start a new migration to re-process.

### Q: Where are migration results stored?
**A:** In `.ngreact_data/jobs/<job-id>/artifacts/`. Automatically cleaned after 30 days.

### Q: Can I customize DHL DUIL components?
**A:** Generated code uses `@dhl-official/react-library`. Customize in your React app after migration.

### Q: Is my code sent to any external service?
**A:** No. Code stays on DHL Apigee (DHL-controlled). Not shared with OpenAI or external services.

### Q: Can I migrate React to anything else?
**A:** No, this is Angular → React only. Not for other frameworks.

### Q: How accurate is the migration?
**A:** ~95% automated accuracy. Always review and test generated code before deployment.

### Q: Can I migrate Angular 1.x?
**A:** No, not supported. Minimum is Angular 12+.

### Q: What if I get an ESLint error after migration?
**A:** 
1. Review the error message
2. Check the generated code
3. Fix manually if needed (usually simple style issues)
4. Run `npm run lint:fix` to auto-fix many issues

### Q: How do I integrate generated code into my React app?
**A:**
```bash
# Extract deliverable
unzip deliverable.zip -d react-app/

# Install deps
cd react-app
npm install

# Run tests
npm test

# Verify it works
npm run dev
```

### Q: Can I use the generated code in production immediately?
**A:** Not recommended. Always:
1. Review code for compliance
2. Run full test suite
3. Integration test with your system
4. Get code review approval
5. Then deploy

### Q: What's the difference between Phase 1 and Phase 2?
**A:** 
- Phase 1: Planning/Analysis (figuring out what to do)
- Phase 2: Implementation (actually doing the conversion)

### Q: Do I need to approve at every gate?
**A:** Yes, both gates:
- **Gate A (Phase 1):** Approve the plan
- **Gate B (Phase 4):** Approve the final results

You can request changes at each gate instead of approving.

---

## 🔍 Debugging Tips

### Enable Debug Logging
```bash
# Set log level to DEBUG
export LOG_LEVEL=DEBUG

# Or in .env
LOG_LEVEL=DEBUG

# Restart server
python -m uvicorn server.app:app --port 8002
```

### Check Server Logs
Look at the terminal where you started the server:
```
INFO:     Application startup complete
INFO:     Phase 1 starting...
WARNING:  Component has complex directives
ERROR:    TypeScript compilation failed
```

### Test API Directly
```powershell
# Check health
Invoke-RestMethod -Uri "http://127.0.0.1:8002/api/health"

# Create a test job
$body = @{"project_path" = "/path/to/project"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8002/api/jobs" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

### Check Environment
```bash
# Verify Python version
python --version
# Should be 3.11+

# Verify venv
which python  # (Unix) or where python (Windows)
# Should show .venv path

# Verify packages
pip list | grep -E "(adk|fastapi|httpx)"
```

---

## 📞 Getting Further Help

### Before contacting support:
1. ✅ Check this troubleshooting guide
2. ✅ Review `STARTUP_GUIDE.md`
3. ✅ Check server terminal for error messages
4. ✅ Verify `.env` configuration
5. ✅ Test with a simple Angular component first

### When reporting issues:
Provide:
1. Error message (exact text)
2. What you were trying to do
3. Environment: Windows/Mac/Linux
4. Python version: `python --version`
5. Server logs (last 20 lines)
6. Project size and type

### Contact:
- Your DHL AI Champion
- Team Slack channel
- Internal IT support

---

## 💾 Data & Privacy

### What data is stored?
- Migration job artifacts (reports, code, tests)
- Job metadata (start time, duration, status)
- Chat history (if using UI)

### How long is data kept?
- Default: 30 days
- Configure via: `DATA_RETENTION_DAYS` in `.env`

### How do I delete job data?
```bash
# Delete specific job
rm -rf .ngreact_data/jobs/<job-id>

# Clear all jobs
rm -rf .ngreact_data/jobs/
```

### Is my code secure?
✅ Yes:
- Code stays on DHL infrastructure
- Not shared with external services
- Uses DHL Apigee (controlled access)
- Delete jobs anytime

---

**Still stuck? Check `STARTUP_GUIDE.md` or contact your DHL AI Champion! 🚀**
