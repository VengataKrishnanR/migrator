# Agent Orchestration Debugging Guide

## The Real Problem

The error shows the agent is returning **some** JSON, but it's not the expected `AnalysisReport` structure:

```
[RAW RESPONSE PREVIEW]
skip_summarization=None state_delta={} artifact_delta={} ...
[JSON_EXTRACT] Raw JSON parsed successfully
[INVOKE_AGENT] JSON ERROR: 'AnalysisReport missing required field(s): components, services'
```

This indicates:
1. ✅ JSON extraction succeeds (something is being parsed)
2. ❌ But that JSON is **not** the agent's response - it's event metadata
3. ❌ The actual model response is not being extracted from the event stream

## Root Cause Hypothesis

The `_collect_final_text` function in `server/agent_invoker.py` is not correctly extracting the LLM response from the Google ADK event stream. It's extracting event metadata instead of the actual model output.

**Specifically**: The event object has properties like `skip_summarization`, `state_delta`, etc., and when these are stringified, they produce text that happens to parse as JSON but isn't the model's response.

## New Diagnostic Logging

I've added comprehensive logging to `server/agent_invoker.py`:

### What to look for in logs:

```
[EV#N] attributes=[list of event properties]
[EV#N] raw_str=<string representation of event>
[EV#N] extracted from .text
[EV#N] has content, parts=<type> len=<number>
[EV#N] part[i] type=<PartType>
[EV#N] part[i] extracted .text, len=<length>
[JSON_EXTRACT] Fenced JSON parsed successfully
[JSON_EXTRACT] Raw JSON parsed successfully
[AGENT_COMPLETE] first 300 chars: <response_start>
```

### What each log means:

- `[EV#N] attributes=[...]` — Shows all attributes on the event object
- `[EV#N] raw_str=...` — The string representation (shows if it's metadata or actual content)
- `[EV#N] extracted from .text` — Good! Found text directly on event
- `[EV#N] has content, parts=...` — Event has content with parts (likely path to actual response)
- `[EV#N] part[i] extracted .text, len=...` — Good! Extracted text from part
- `[JSON_EXTRACT] ... parsed successfully` — Shows which parsing strategy worked
- `[AGENT_COMPLETE] first 300 chars: ...` — The actual response text being returned

## How to Run

1. Start the server with the updated code:
```bash
python -m uvicorn server.app:app --port 8002 --host 127.0.0.1
```

2. Trigger a job via the API

3. **Watch stderr carefully** for the diagnostic logs

4. Look for which of these is happening:
   - **Case A**: `extracted from .text` appears → Good, we're getting text
   - **Case B**: `has content, parts=...` appears → Response is in parts
   - **Case C**: Neither appears, fallback to actions → Problem! Event structure is wrong
   - **Case D**: `first 300 chars:` shows event metadata → We're getting the wrong thing

## Expected vs. Actual

### Expected behavior:
```
[EV#1] has content, parts=ContentType len=1
[EV#1] part[0] type=Part
[EV#1] part[0] extracted .text, len=<large>
[JSON_EXTRACT] Fenced JSON parsed successfully
[AGENT_COMPLETE] first 300 chars: ```json
{
  "components": [...]
```

### Current behavior:
```
[EV#1] type=Event final=True
[RAW RESPONSE PREVIEW]
skip_summarization=None state_delta={}...
[JSON_EXTRACT] Raw JSON parsed successfully
[AGENT_COMPLETE] first 300 chars: {'skip_summarization': None, ...}
```

## Next Steps Based on Findings

### If Case A or B (text found):
- The prompt is being passed correctly
- The model is returning something
- The problem is that the **model isn't following the schema in the prompt**
- **Fix**: Improve model instruction or try a different model

### If Case C or D (wrong thing extracted):
- The event stream structure from Google ADK isn't what we expect
- The REST LLM backend (Azure via Apigee) might return responses in a different format
- **Fix**: 
  - Option 1: Investigate the exact event/part structure and extract the right field
  - Option 2: Bypass Google ADK and call the REST LLM directly
  - Option 3: Check if there's an incompatibility between Google ADK and the custom REST backend

## Files Modified for Diagnostics

- `server/agent_invoker.py`: Added detailed logging to `_collect_final_text()` and JSON extraction
- Prompts in `server/phase_runner.py`: Added explicit schema to all 9 agent stages

## Quick Reference: Event Structure

When you see logs, look for the pattern:

```
[EV#1] attributes=[...]              ← What properties exist on this event
[EV#N] raw_str=...                   ← String version (metadata or content?)
[EV#N] has content, parts=...        ← Does it have content.parts array
[EV#N] part[i] extracted .text       ← Was text extracted from a part
[JSON_EXTRACT] ... parsed            ← How was JSON extracted
[AGENT_COMPLETE] first 300 chars: .. ← What's in the response
```

If any of this shows event metadata instead of actual model output, we have a fundamental issue with how Google ADK is integrating with the custom REST LLM backend.
