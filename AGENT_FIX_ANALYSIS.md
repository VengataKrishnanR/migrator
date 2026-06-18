# NgReact V3 Agent Orchestration — Complete Analysis & Fix

## 🔴 CRITICAL ISSUES IDENTIFIED

### 1. Sub-Agent Prompts Reference V2
```
analyzer_agent.md:    "You are **analyzer_agent_v2**" ❌
risk_detection_agent.md: "You are **risk_detection_agent_v2**" ❌
state_migration_agent.md: "You are **state_migration_agent_v2**" ❌
```
**Impact:** Agents confused about their version, inconsistent behavior

### 2. Sub-Agent Prompts Are 100+ Lines (Too Verbose)
- **analyzer_agent.md:** 100+ lines of explanation → Agent gets confused
- **risk_detection_agent.md:** 80+ lines of explanation → Unclear what to do
- **migration_planner_agent.md:** Complex instructions
- **state_migration_agent.md:** Too much context
- **transformer_agent.md:** 150+ lines

**Impact:** Agent overthinks, loops, makes wrong decisions

### 3. Root Agent Doesn't Show Exact Sub-Agent Inputs
Root agent says: "Call analyzer_agent_v3"
But doesn't show: What exact parameters? What format?

**Impact:** Agent guesses at parameters, causes errors

### 4. Sub-Agents Don't Have Clear Output Contracts
- No explicit JSON schema
- Multiple acceptable formats
- Agent produces "close enough" output that fails validation

**Impact:** Validation fails, repair retries loop

### 5. Context Not Passed Correctly
Root agent says: "Call analyzer_agent_v3 with [project files + context]"
But agents don't know:
- How to parse project files input
- What "context" actually is
- What fields are required in output

**Impact:** Agent confused, produces wrong output

---

## ✅ SOLUTION

### Phase 1: Simplify Sub-Agent Prompts
**Rule:** Each prompt must be ≤30 lines

Format:
```markdown
# Agent Name V3

One-line description.

## Your Job
What you do (1 sentence)

## Input You Get
What you receive (bullet points)

## Output Format (REQUIRED)
```json
{ JSON schema exactly }
```

## Process
1. Step 1
2. Step 2
3. Output JSON

## CRITICAL
- ONLY JSON output
- NO markdown
- REQUIRED fields: [list]
- Value constraints: [list]
```

### Phase 2: Update Root Agent to Show Exact Inputs
Instead of:
```
PHASE 1 STEP 1: Call analyzer_agent_v3
Input: project files + context
```

Write:
```
PHASE 1 STEP 1: Call analyzer_agent_v3 with:
{
  "files": ["src/app/user.component.ts", ...],
  "content": "// ── FILE: user.component.ts ──\n@Component(...) export class UserComponent { ... }",
  "instruction": "Analyze this Angular code"
}
```

### Phase 3: Create Sub-Agent Input/Output Contract
Each sub-agent defines:
- **Input Schema:** Exact JSON structure root agent sends
- **Output Schema:** Exact JSON structure sub-agent must return
- **Validation Rules:** What makes valid output

### Phase 4: Add Validation to Agent Invoker
In `server/agent_invoker.py`:
- Validate JSON schema BEFORE accepting
- Clear error message if invalid
- Show expected format in error

---

## 📋 FILES TO UPDATE

### Sub-Agent Prompts (SIMPLIFY ≤30 LINES EACH)
1. ✅ `tools/agents/prompts/analyzer_agent.md` — DONE
2. `tools/agents/prompts/risk_detection_agent.md` — TODO
3. `tools/agents/prompts/migration_planner_agent.md` — TODO
4. `tools/agents/prompts/state_migration_agent.md` — TODO
5. `tools/agents/prompts/transformer_agent.md` — TODO
6. `tools/agents/prompts/refactor_agent.md` — TODO
7. `tools/agents/prompts/test_generation_agent.md` — TODO
8. `tools/agents/prompts/validator_agent.md` — TODO
9. `tools/agents/prompts/report_agent.md` — TODO

### Root Agent Prompt
- `prompts/root_agent_v3.md` — Show exact input/output formats

### Infrastructure
- `server/agent_invoker.py` — Add schema validation
- `tools/agents/__init__.py` — All agents point to v3 prompts

---

## 🎯 EXPECTED BEHAVIOR AFTER FIX

**Before:**
```
User: "start migration"
Agent: Calls analyzer_agent_v3
Agent: Stuck waiting for response / loops in Phase 1
```

**After:**
```
User: "start migration"  
Agent: Calls analyzer_agent_v3 with exact input {files: [...], content: "..."}
analyzer_agent_v3: Analyzes code, returns JSON
Agent: Validates JSON schema
Agent: Proceeds to Step 2 ✅
```

---

## 🔧 Key Changes Summary

| Component | Old Problem | New Fix |
|-----------|------------|---------|
| Analyzer prompt | 100 lines, v2 ref | ≤30 lines, v3, JSON only |
| Risk detection | 80 lines, unclear | ≤30 lines, clear schema |
| Root agent | Implicit inputs | Explicit input/output examples |
| Validation | Retry on any error | Clear schema validation |
| Agent names | v2 references | All v3 |

---

## ✨ After This Fix

1. ✅ All prompts are short and clear (≤30 lines)
2. ✅ All agent names are v3
3. ✅ All inputs/outputs are explicit
4. ✅ No more loops or confusion
5. ✅ Clear error messages on validation failure
6. ✅ Agent orchestration works smoothly

---

## Implementation Order

1. Simplify ALL sub-agent prompts (analyzer done, 8 remaining)
2. Update root agent with explicit input/output examples
3. Add schema validation to agent_invoker.py
4. Test Phase 1 orchestration
5. Test full 4-phase pipeline
6. Document the contract

---

**Status:** In progress. Analyzer prompt simplified. 8 more prompts to update.
