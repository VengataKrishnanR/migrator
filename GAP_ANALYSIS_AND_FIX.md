# Gap Analysis: Orchestration Type Mismatch & Agent Response Structure

## Problem Summary

The agent orchestration failed with:
```
[INVOKEAGENT] JSON ERROR: 'AnalysisReport missing required field(s): components, services'
AgentInvocationError: Agent failed after retry: 'AnalysisReport missing required field(s): components, services'
```

The analyzer agent was returning JSON, but it didn't include the required `components` and `services` fields that downstream validators expected.

---

## Root Cause Analysis

### 1. **Weak Prompt Coupling**
- **Issue**: The stage prompt in `phase_runner.py` only said "Analyze this Angular project and produce the AnalysisReport" without showing the exact JSON schema
- **Impact**: The agent's instruction file (`analyzer_agent.md`) defined the schema, but the runtime stage prompt didn't reinforce it
- **Result**: Agent could interpret "AnalysisReport" differently or return partial/incomplete JSON

### 2. **Agent Instruction Isolation**
- **Issue**: The agent's detailed instruction (analyzer_agent.md) is decoupled from the stage prompt
- **Impact**: Agent configuration and runtime invocation were not synchronized
- **Result**: If agent didn't fully integrate the instruction, the stage prompt alone wasn't enough to enforce the schema

### 3. **Ineffective Repair Mechanism**
- **Issue**: The retry prompt (agent_invoker.py) appended instructions but didn't explicitly show the required schema
- **Impact**: Second attempt would fail for the same reason without new information
- **Result**: Both attempts (attempt 1/2 and 2/2) failed with identical error

### 4. **Poor Error Diagnostics**
- **Issue**: The JSON extraction function provided minimal debugging info about what was actually returned
- **Impact**: Difficult to diagnose what the agent actually produced vs. what was expected
- **Result**: Debugging cycle requires extensive log analysis

---

## The Fix: Explicit Schema-Driven Prompts

### Changes Made

#### 1. **Enhanced Agent Invoker (`server/agent_invoker.py`)**

**A. Improved Repair Prompt**
```python
# Before:
attempt_prompt = (
    f"{prompt}\n\n## Output correction required\n"
    f"Respond ONLY with a single ```json fenced block containing valid JSON."
)

# After:
attempt_prompt = (
    f"{prompt}\n\n"
    f"## CRITICAL: Your previous response was invalid.\n"
    f"You MUST respond with ONLY a single JSON object in a ```json fenced block.\n"
    f"NO other text before or after the code block.\n"
    f"Ensure all required fields are present and arrays are valid JSON.\n"
    f"Do not include markdown, explanations, or any text outside the code block."
)
```

**B. Enhanced JSON Extraction with Diagnostics**
- Added debug logging for each extraction strategy
- Distinguishes between "no JSON found" vs. "invalid JSON"
- Shows first 200 chars of response when extraction fails
- Logs which extraction method succeeded (fenced vs. raw)

#### 2. **Explicit Schema in All Stage Prompts (`server/phase_runner.py`)**

Updated all 9 agent invocations to include:
1. Clear statement of output requirement (JSON + type name)
2. **Explicit schema definition** showing exact structure
3. **Format directive**: "Output ONLY the JSON in a ```json fenced block"
4. **No explanations** warning

**Example - Analyzer (Phase 1, Stage 1)**:
```python
lambda arts: (
    f"{feedback}Analyze this Angular project and produce a JSON AnalysisReport.\n\n"
    f"Your output MUST be a JSON object with this exact structure:\n"
    f"{{\n"
    f'  "components": [{{"name": "ComponentName", "path": "src/...", "has_forms": true/false, "has_router": true/false, "dependencies": []}}],\n'
    f'  "services": [{{"name": "ServiceName", "path": "src/...", "http_calls": []}}],\n'
    f'  "modules": [],\n'
    f'  "routes": [],\n'
    f'  "pipes": [],\n'
    f'  "guards": [],\n'
    f'  "directives": [],\n'
    f'  "total_files": 0\n'
    f"}}\n\n"
    f"Output ONLY the JSON in a ```json fenced block. No explanations.\n\n"
    f"Source code to analyze:\n{source}"
)
```

This pattern was applied to all 9 stages across 4 phases:
- **Phase 1**: analyzer, risk_detection, migration_planner, state_migration_planner
- **Phase 2**: transformer, refactor_optimizer
- **Phase 3**: test_planner, test_generator
- **Phase 4**: validator, report

---

## Key Improvements

### 1. **Type Safety**
- ✅ Schema now embedded in runtime prompt, not just in agent instructions
- ✅ Agent sees exact structure expected, not just a type name
- ✅ Less room for interpretation or partial implementations

### 2. **Fault Tolerance**
- ✅ Repair mechanism now repeats the full schema, giving agent context for fixing
- ✅ Explicit "no other text" directive prevents markdown wrapper issues
- ✅ Better error messages aid debugging

### 3. **Observability**
- ✅ Enhanced JSON extraction logs which strategy worked
- ✅ Shows actual response start when extraction fails
- ✅ Distinguishes between "no JSON" and "invalid JSON" errors

### 4. **Orchestration Clarity**
- ✅ Prompt + validator are now aligned on expected structure
- ✅ No implicit assumptions between agent instruction and stage invocation
- ✅ Schema is canonical source of truth in the runtime prompt

---

## Validation

The fix ensures:

1. **First Attempt Success**: Agent sees full schema in prompt, much more likely to comply
2. **Repair Success**: If it fails, retry gets same context plus explicit error signal
3. **Clear Failure**: If retry fails, JSON extraction now tells us what was actually returned
4. **Propagation**: Schema now consistent across all 9 agent stages

---

## Testing Recommendations

1. **Run Phase 1 Analysis**: Verify analyzer returns `AnalysisReport` with `components` and `services`
2. **Check Subsequent Stages**: Risk detection, planner, state migration should all return valid schemas
3. **Monitor Logs**: 
   - Look for `[JSON_EXTRACT] ... parsed successfully` (good sign)
   - Look for `[JSON_EXTRACT] No JSON found` or `[JSON_EXTRACT] ... invalid` (debug info)
4. **Verify End-to-End**: Run a full migration job (all 4 phases) to ensure all 9 stages work

---

## Files Modified

1. `server/agent_invoker.py`
   - Enhanced repair prompt with explicit formatting directives
   - Improved JSON extraction with debug logging

2. `server/phase_runner.py`
   - Updated 9 stage prompts (lines 123-512)
   - All now include explicit schema definition
   - All now include format directives

---

## Architecture Notes

This fix does **not** change the validator schemas or agent definitions. It only strengthens the contract between the stage prompt and the agent output by:
- Making the prompt the canonical source of schema truth
- Synchronizing agent instruction (static) with stage invocation (dynamic)
- Improving the repair mechanism to actually help the agent recover

The approach is **backwards compatible**: existing valid responses still validate, and new prompts are stricter but correct.
