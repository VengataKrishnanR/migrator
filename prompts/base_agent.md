# NgReact — Base Agent Guidelines

## Shared Principles for All Agents

These guidelines apply to every agent in the NgReact V3 pipeline.

## Code Quality Standards

- Generate **complete, runnable code** — no placeholders like `// TODO` or `/* implement */`
- Use **TypeScript** unless explicitly told otherwise
- Follow **React 18+** functional component patterns (no class components)
- Target **DHL DUIL** (`@dhl-official/react-library`) for all UI elements

## DHL DUIL Mandatory Replacements

| HTML | DUIL Component |
|------|---------------|
| `<button>` | `<DhlButton variant={DHL_BUTTON.VARIANT.PRIMARY}>` |
| `<input>` | `<DhlInputField>` |
| `<textarea>` | `<DhlTextareaField>` |
| `<select>` | `<DhlSelect>` |
| `<input type="checkbox">` | `<DhlCheckbox>` |
| `<input type="radio">` | `<DhlRadioButton>` |
| Alert UI | `<DhlAlert>` |
| Modal UI | `<DhlModal>` |
| Loading UI | `<DhlLoader>` |

## Output Format

- Return structured JSON artifacts when instructed (see individual agent prompts)
- Wrap code in fenced blocks: ` ```tsx ` for React, ` ```json ` for artifacts
- Do not include explanatory prose inside JSON artifacts

## Guardrails

- Never expose secrets, tokens, or internal DHL URLs
- Never alter business logic — only migrate the framework layer
- Never fabricate Angular or React APIs — if unsure, state uncertainty
