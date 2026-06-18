# Phase 2 Fix: Google ADK Template Injection Conflict

## Problem Identified

When Phase 2 agents (transformer, refactor, etc.) are invoked, Google ADK tries to process the agent instruction file as a template and replace `{variable}` patterns with context variables.

Error:
```
KeyError: 'Context variable not found: `onSubmit`.'
```

The transformer agent's instruction file contains code examples with JSX syntax that uses curly braces like `{onSubmit}`, which Google ADK interprets as a template variable placeholder.

---

## Root Cause

Google ADK's instruction preprocessing (in `instructions_utils.py`) uses regex pattern:
```
{+[^{}]*}+
```

This matches patterns like `{varname}` and tries to replace them with context variables. The transformer agent's instruction examples have:
- `{onSubmit}` — looks like a variable reference
- `{pageSize = 10, onUserSelected}` — destructuring syntax
- etc.

Google ADK finds these and fails when the context doesn't have those variables.

---

## Solution Applied

Escaped curly braces in code examples by doubling them:
- `{variable}` → `{{variable}}`
- `{pageSize}` → `{{pageSize}}`

This prevents Google ADK from interpreting them as template variables while still being recognizable in documentation (double braces typically indicate "escaped").

---

## Files Fixed

### ✅ `tools/agents/prompts/transformer_agent.md`

**Line 92** — Component signature:
```typescript
// Before
export const UserForm: React.FC<{ onSubmit: (data: UserFormFields) => void }> = ({ onSubmit }) => {

// After
export const UserForm: React.FC<{{ onSubmit: (data: UserFormFields) => void }}> = ({{ onSubmit }}) => {
```

**Line 175** — Component destructuring:
```typescript
// Before
export const UserList: React.FC<UserListProps> = ({ pageSize = 10, onUserSelected }) => {

// After
export const UserList: React.FC<UserListProps> = ({{ pageSize = 10, onUserSelected }}) => {
```

**Lines 102-108** — DhlInputField example:
```typescript
// Before
name={field.name}
value={field.value ?? ''}
onDhlChange={(e) => field.onChange(e.detail?.value ?? e.target?.value)}
errorMessage={errors.email?.message}

// After
name={{field.name}}
value={{field.value ?? ''}}
onDhlChange={{(e) => field.onChange(e.detail?.value ?? e.target?.value)}}
errorMessage={{errors.email?.message}}
```

**Lines 177-197** — useUser and JSX example:
```typescript
// Before
const { users, loading } = useUser();
...
navigate(`/users/${user.id}`);
...
{users.slice(0, pageSize).map((user) => (
  <div key={user.id}>
    <span>{user.name}</span>
    ...onDhlClick={() => handleSelectUser(user)}

// After
const {{ users, loading }} = useUser();
...
navigate(`/users/${{user.id}}`);
...
{{users.slice(0, pageSize).map((user) => (
  <div key={{user.id}}>
    <span>{{user.name}}</span>
    ...onDhlClick={{() => handleSelectUser(user)}}
```

---

## Why This Works

When Google ADK processes the instruction file:
1. Regex `{+[^{}]*}+` looks for patterns like `{varname}`
2. Escaped double braces `{{varname}}` don't match the pattern (first `{` matches, but then it encounters another `{` which breaks the `[^{}]*` part)
3. The code examples are left untouched
4. Agent receives unmodified instruction with proper JSX syntax

---

## Other Agents to Check

⚠️ **Potential issues in other agents** (if they have similar code examples):
- `refactor_agent.md` — likely has JSX examples
- `test_generation_agent.md` — likely has test code examples
- `state_migration_agent.md` — has TypeScript examples

**Status**: Not yet fixed (Phase 2 transformer was priority; if other agents trigger, they need same fix)

---

## Testing

After this fix, Phase 2 should work:

1. **Phase 1** (analysis) → ✅ Working (confirmed in logs)
2. **Approve Phase 1** → Proceed to Phase 2
3. **Phase 2** (transformer) → Should now work (template injection fixed)
4. **Refactor stage** → May need same fix if it fails

---

## Prevention for Future

When creating agent instruction files with code examples:
- Always escape JSX curly braces: `{var}` → `{{var}}`
- Use markdown code fences (````typescript`...```) to make intent clear
- Document the escaping: "Examples use `{{double braces}}` due to Google ADK template processing"

---

## Relevant Code Paths

- **Instruction processing**: `google/adk/flows/llm_flows/instructions.py`
- **Template injection**: `google/adk/utils/instructions_utils.py` (line 124: `inject_session_state`)
- **Regex pattern**: `{+[^{}]*}+` matches template variables
- **Agent invocation**: `server/agent_invoker.py` → `_collect_final_text()` → agent instruction is used

---

## Next Phase Issues to Watch

When Phase 3 & 4 agents are invoked, watch for similar KeyError:
```
KeyError: 'Context variable not found: `<something>`.'
```

If it happens, apply same fix to that agent's instruction file.
