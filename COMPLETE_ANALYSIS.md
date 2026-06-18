# Complete Analysis: Agent Orchestration Data Type Mismatch

## Executive Summary

The agent invocation is **partially working** — it successfully calls the agent and extracts JSON, but the JSON doesn't contain the expected `components` and `services` fields. This is a **multi-layered problem** with both prompt/schema issues AND potential event extraction issues.

---

## Layer 1: The Immediate Problem (FIXED)

### What Was Wrong
The agent prompts didn't explicitly show the required JSON schema, only naming the type. The validator then rejected responses that didn't have the required fields.

### What I Fixed
✅ Updated all 9 agent stage prompts in `server/phase_runner.py` to include explicit JSON schema examples  
✅ Improved repair prompt in `server/agent_invoker.py` with clearer formatting directives  
✅ Enhanced `analyzer_agent.md` instructions with **MANDATORY STRUCTURE** section and examples  
✅ Improved `extract_json()` function with detailed diagnostic logging

**Result**: Agents now have the schema embedded in the runtime prompt, not just in instructions.

---

## Layer 2: The Deeper Problem (NEEDS INVESTIGATION)

### The Evidence

Looking at the actual log output:
```
[RAW RESPONSE PREVIEW]
skip_summarization=None state_delta={} artifact_delta={} transfer_to_agent=None ...
[JSON_EXTRACT] Raw JSON parsed successfully
```

This is **NOT** the model's actual response. It's metadata from the Google ADK event object.

### The Question

**Why is the wrong thing being extracted?**

Three possible causes:

#### Possibility A: Agent Response Format Issue
The model IS returning the correct response, but it's not being extracted from the event stream correctly.
- **Symptom**: Event properties like `content.parts[0].text` contain the real response, but they're not being accessed
- **Root cause**: Google ADK event structure might differ from what the code expects, especially with custom REST LLM backend
- **Evidence**: Event object has properties that stringify to metadata, not the actual response

#### Possibility B: Model Not Following Instructions
The model receives the prompt but doesn't follow it.
- **Symptom**: Model returns something else instead of the JSON schema
- **Root cause**: The model isn't being "instructed" properly via Google ADK, or the instruction field isn't being used as a system prompt
- **Evidence**: Both attempts (1/2 and 2/2) fail identically, suggesting the repair didn't provide new context

#### Possibility C: Prompt Not Reaching the Model
The prompt with the schema isn't being passed to the model correctly.
- **Symptom**: The model responds to a generic request instead of the specific prompt
- **Root cause**: The `invoke_agent()` call isn't properly forwarding the prompt to the agent, or the Agent class isn't using it
- **Evidence**: Hard to determine without seeing what the model actually receives

### Diagnostic Steps Added

I've added comprehensive logging to identify which possibility is true:

```python
# In _collect_final_text():
print(f"[EV#{event_count}] attributes={attrs}")  # What's on the event?
print(f"[EV#{event_count}] raw_str={str(ev)[:400]}")  # String representation
print(f"[EV#{event_count}] has content, parts=...")  # Is content there?
print(f"[EV#{event_count}] part[i] extracted .text")  # Was text found?

# In extract_json():
print(f"[JSON_EXTRACT] Fenced JSON parsed successfully")  # Which method worked?
print(f"[JSON_EXTRACT] Raw JSON parsed successfully")
print(f"[AGENT_COMPLETE] first 300 chars: {final[:300]}")  # What's being returned?
```

---

## What You Need to Do

### Step 1: Run the Server with Enhanced Logging

```bash
# Activate venv
& C:\Users\jmlrg1\Downloads\Ang2React_18\Ang2React\.venv\Scripts\Activate.ps1

# Run with logging visible
python -m uvicorn server.app:app --port 8002 --host 127.0.0.1
```

### Step 2: Trigger a Job and Observe Logs

Create a new job via the API and watch the **stderr output** carefully.

### Step 3: Interpret the Diagnostic Output

Look for these patterns:

**🟢 Good Sign - Case A:**
```
[EV#1] attributes=[..., 'content', 'text', ...]
[EV#1] part[0] extracted .text, len=1500
[JSON_EXTRACT] Fenced JSON parsed successfully
[AGENT_COMPLETE] first 300 chars: {
  "components": [
```
→ **Interpretation**: The event has proper content with text, we're extracting it, and the response looks good.  
→ **Next step**: Problem is the model not following the schema. Need to debug the model or try a different one.

**🟡 Warning Sign - Case B:**
```
[EV#1] has content, parts=NoneType len=0
[EV#1] fallback to actions type=dict
[JSON_EXTRACT] Raw JSON parsed successfully
[AGENT_COMPLETE] first 300 chars: {'skip_summarization': None, 'state_delta': {...}}
```
→ **Interpretation**: Content has no parts. We're extracting from actions, which is metadata.  
→ **Next step**: The REST LLM backend isn't populating `content.parts` correctly. Need to debug the LLM integration or switch backends.

**🔴 Bad Sign - Case C:**
```
[EV#1] attributes=[..., NO TEXT/CONTENT FIELDS ...]
[EV#1] fallback to actions
```
→ **Interpretation**: The event object structure is completely different from what we expect.  
→ **Next step**: Google ADK might not be compatible with the custom REST LLM backend. Consider bypassing ADK entirely.

---

## Files Modified

### Core Fixes
1. **`server/agent_invoker.py`**
   - Enhanced `extract_json()` with strategy logging
   - Added detailed `_collect_final_text()` diagnostics
   - Improved repair prompt with clearer directives

2. **`server/phase_runner.py`**
   - Updated 9 stage prompts with explicit schemas:
     - Phase 1 (4 stages): analyzer, risk_detection, migration_planner, state_migration_planner
     - Phase 2 (2 stages): transformer, refactor_optimizer
     - Phase 3 (2 stages): test_planner, test_generator
     - Phase 4 (2 stages): validator, report

3. **`tools/agents/prompts/analyzer_agent.md`**
   - Rewrote with **MANDATORY STRUCTURE** section
   - Added explicit examples
   - Emphasized `components` and `services` fields

### Documentation
1. **`DEBUGGING_GUIDE.md`** — How to interpret the diagnostic logs
2. **`GAP_ANALYSIS_AND_FIX.md`** — Original gap analysis
3. **`COMPLETE_ANALYSIS.md`** — This file

---

## Architecture Decision: Why This Approach?

**Why make the prompt more explicit instead of fixing the framework?**

1. **Schema-as-prompt** is more robust than relying on agent instructions
2. It works regardless of how the Agent class integrates instructions
3. It's the most direct way to align prompt + validator
4. It can work even if the model isn't using the agent instruction as a system prompt

**Why add so much logging?**

1. **The problem is unclear** — We don't know if it's:
   - Prompt not reaching the model
   - Model not following the prompt
   - Response not being extracted correctly
2. **Logging isolates each concern** — We can now tell which layer is broken
3. **Provides evidence** — Logs show exactly what's in the event stream and response

---

## Next Actions After Diagnostics

### If Case A (Event has content, text exists):
The response is being extracted correctly, but doesn't have the right fields.
- **Root cause**: Model isn't following the schema instruction
- **Solutions**:
  1. Try a different/better model (gpt-4 instead of gpt-4o-mini)
  2. Add tool definitions to force JSON output
  3. Use a structured output / JSON mode if the model supports it

### If Case B (No content.parts, falling back to actions):
The LLM response isn't being properly populated into the event structure.
- **Root cause**: Mismatch between custom REST LLM backend and Google ADK expectations
- **Solutions**:
  1. Debug the REST LLM's response format
  2. Add custom event parsing for this specific backend
  3. Switch to native Google LLM or OpenAI integration
  4. Bypass Google ADK and call the REST LLM directly

### If Case C (Event structure completely different):
Fundamental incompatibility between Google ADK and the custom backend.
- **Root cause**: Google ADK assumes a specific LLM response format that isn't being met
- **Solutions**:
  1. Replace Google ADK agent with a simpler prompt + response handler
  2. Use a different agent framework (LangChain, Anthropic SDK, etc.)
  3. Call the REST LLM directly with standard HTTP requests

---

## Testing Strategy

```python
# Once you've diagnosed which case applies, test the fix:

# Case A Test:
response = model.generate("Give me JSON: {\"test\": true}")
# If response has the right structure, the model is fine; maybe it's just the analyzer schema

# Case B/C Test:
# Call the REST LLM directly without Google ADK
# If that works, ADK is the problem
```

---

## Summary

✅ **Done**: Made prompts more explicit and improved diagnostics  
⏳ **Pending**: Run diagnostics to identify which layer is broken  
🔧 **After diagnostics**: Apply appropriate fix (model change, backend change, or framework change)

The enhanced logging should now clearly show what's happening in the event stream and where the response is coming from (or not coming from).
