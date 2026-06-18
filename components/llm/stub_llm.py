"""Stub LLM for local testing without the DHL Apigee proxy.

Returns scripted, agent-aware responses so the full pipeline can be exercised
end-to-end without real HTTP calls or API keys.

Usage:
    Set  NGREACT_LLM_MODE=stub  in your .env (or .env.test) and run as normal.
    The pipeline will execute with zero latency and deterministic outputs.
"""
from __future__ import annotations

import re
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types


# ---------------------------------------------------------------------------
# Role detection — read the system instruction to identify which agent is
# speaking, then dispatch to the right canned response.
# ---------------------------------------------------------------------------

_ROLE_HINTS: dict[str, list[str]] = {
    # Root agents checked FIRST — their prompts reference all sub-agent artifact
    # names, so they must be identified by their own unique "You are" declaration
    # before the sub-agent artifact hints are tried.
    # Root agent (v3). Detected by a phrase unique to base_agent.md — must be
    # checked before the legacy "ngreact" hint, since the v3 prompt also opens
    # with "You are **NgReact**".
    "ngreact_v3": ["orchestrator of a 9-stage", "You are **ngreact_v3**", "ngreact_v3,"],
    "ngreact":    ["You are **NgReact**", "You are NgReact"],
    # V3 sub-agents — each prompt opens with "You are **<name>**"
    "analyzer_agent_v3":          ["You are **analyzer_agent_v3**"],
    "risk_detection_agent_v3":    ["You are **risk_detection_agent_v3**"],
    "migration_planner_agent_v3": ["You are **migration_planner_agent_v3**"],
    "state_migration_agent_v3":   ["You are **state_migration_agent_v3**"],
    "transformer_agent_v3":       ["You are **transformer_agent_v3**"],
    "refactor_agent_v3":          ["You are **refactor_agent_v3**"],
    "test_planner_agent_v3":      ["You are **test_planner_agent_v3**"],
    "test_generation_agent_v3":   ["You are **test_generation_agent_v3**"],
    "validator_agent_v3":         ["You are **validator_agent_v3**"],
    "report_agent_v3":            ["You are **report_agent_v3**"],
    # Legacy sub-agents
    "parser_agent":    ["You are **parser_agent**",    "parser_agent"],
    "converter_agent": ["You are **converter_agent**", "converter_agent"],
    "fixer_agent":     ["You are **fixer_agent**",     "fixer_agent"],
    "validator_agent": ["You are **validator_agent**", "validate_react_code"],
}


def _detect_role(llm_request: LlmRequest) -> str:
    """Identify which agent is invoking the LLM from its system instruction."""
    si = getattr(llm_request.config, "system_instruction", None) if llm_request.config else None
    si_text = ""
    if si:
        if isinstance(si, str):
            si_text = si
        else:
            for part in getattr(si, "parts", []):
                if getattr(part, "text", None):
                    si_text += part.text

    for role, hints in _ROLE_HINTS.items():
        if any(hint in si_text for hint in hints):
            return role
    return "unknown"


def _extract_user_text(llm_request: LlmRequest) -> str:
    """Return the most recent user turn as a single string."""
    for content in reversed(llm_request.contents or []):
        if content.role == "user":
            return " ".join(
                getattr(p, "text", "") for p in (content.parts or []) if getattr(p, "text", None)
            )
    return ""


def _extract_component_name(text: str) -> str:
    """Try to pull an Angular/React component name from the input text."""
    m = re.search(r"export\s+class\s+(\w+?)(?:Component)?(?:\s+implements|\s+extends|\s*\{)", text)
    if m:
        name = m.group(1)
        if not name.endswith("Component"):
            name += "Component"
        return name
    m2 = re.search(r"@Component[^}]*?selector:\s*['\"]app-(\w+)['\"]", text, re.DOTALL)
    if m2:
        return "".join(w.capitalize() for w in m2.group(1).split("-")) + "Component"
    return "AppComponent"


# ---------------------------------------------------------------------------
# Canned responses per agent role
# ---------------------------------------------------------------------------

def _stub_analysis_report(user_text: str) -> str:
    name = _extract_component_name(user_text)
    base = name.replace("Component", "")
    return f"""Here is the AnalysisReport for the provided Angular project:

```json
{{
  "components": [
    {{
      "name": "{name}",
      "path": "src/app/{base.lower()}/{base.lower()}.component.ts",
      "selector": "app-{base.lower()}",
      "inputs": ["data"],
      "outputs": ["itemSelected"],
      "lifecycle_hooks": ["ngOnInit", "ngOnDestroy"],
      "template_type": "external",
      "has_forms": false,
      "has_router": false,
      "dependencies": []
    }}
  ],
  "services": [
    {{
      "name": "{base}Service",
      "path": "src/app/services/{base.lower()}.service.ts",
      "injectable": true,
      "dependencies": ["HttpClient"],
      "http_calls": ["GET /api/{base.lower()}s"]
    }}
  ],
  "modules": [],
  "routes": [],
  "pipes": [],
  "guards": [],
  "directives": [],
  "project_type": "standalone",
  "angular_version": "17.0.0",
  "total_files": 3,
  "total_lines": 120
}}
```"""


def _stub_risk_report(_: str) -> str:
    return """RiskReport analysis complete:

```json
{
  "risks": [
    {
      "severity": "low",
      "category": "complexity",
      "description": "2 lifecycle hooks require mapping to useEffect",
      "affected_files": [],
      "mitigation": "ngOnInit → useEffect(fn, []), ngOnDestroy → useEffect cleanup"
    }
  ],
  "overall_risk_score": 0.15,
  "recommended_approach": "big-bang",
  "estimated_effort_hours": 4
}
```"""


def _stub_migration_plan(_: str) -> str:
    return """MigrationPlan created with dependency-ordered chunks:

```json
{
  "chunks": [
    {
      "chunk_id": "service_AppService_0",
      "type": "service",
      "source_files": ["src/app/services/app.service.ts"],
      "dependencies": [],
      "priority": 3,
      "estimated_tokens": 400
    },
    {
      "chunk_id": "component_AppComponent_0",
      "type": "component",
      "source_files": [
        "src/app/app/app.component.ts",
        "src/app/app/app.component.html",
        "src/app/app/app.component.css"
      ],
      "dependencies": ["service_AppService_0"],
      "priority": 2,
      "estimated_tokens": 800
    }
  ],
  "execution_order": ["service_AppService_0", "component_AppComponent_0"],
  "parallel_groups": [["service_AppService_0"], ["component_AppComponent_0"]],
  "total_estimated_tokens": 1200,
  "recommended_batch_size": 5
}
```"""


def _stub_state_plan(_: str) -> str:
    return """StateMigrationPlan ready:

```json
{
  "mappings": [
    {
      "angular_pattern": "service",
      "react_pattern": "context",
      "source": "AppService (holds shared state)",
      "target": "AppContext + useApp() hook",
      "notes": "Singleton service → Context provider at app root"
    },
    {
      "angular_pattern": "component-prop",
      "react_pattern": "prop",
      "source": "@Input() data",
      "target": "props.data",
      "notes": "Direct prop mapping"
    }
  ],
  "recommended_library": "context",
  "shared_state_files": ["src/contexts/AppContext.tsx"],
  "requires_refactoring": false
}
```"""


def _stub_react_source(user_text: str) -> str:
    name = _extract_component_name(user_text)
    base = name.replace("Component", "")
    return f"""Converted Angular component to React 18+:

```json
{{
  "file_path": "src/components/{base}.tsx",
  "content": "import React, {{ useEffect, useState }} from 'react';\\nimport {{ DhlButton }} from '@dhl-official/react-library';\\nimport {{ DHL_BUTTON }} from '@dhl-official/stencil-library';\\n\\ninterface {base}Props {{\\n  data?: unknown[];\\n  onItemSelected?: (item: unknown) => void;\\n}}\\n\\nexport const {base}: React.FC<{base}Props> = ({{ data = [], onItemSelected }}) => {{\\n  useEffect(() => {{\\n    // ngOnInit\\n  }}, []);\\n\\n  useEffect(() => {{\\n    return () => {{\\n      // ngOnDestroy cleanup\\n    }};\\n  }}, []);\\n\\n  return (\\n    <div>\\n      <h1>{base}</h1>\\n      {{data.map((item, i) => (\\n        <div key={{i}}>{{String(item)}}</div>\\n      ))}}\\n      <DhlButton variant={{DHL_BUTTON.VARIANT.PRIMARY}} onDhlClick={{() => onItemSelected?.(data[0])}}>\\n        Select\\n      </DhlButton>\\n    </div>\\n  );\\n}};",
  "component_name": "{base}",
  "imports": ["react", "@dhl-official/react-library", "@dhl-official/stencil-library"],
  "exports": ["{base}"],
  "uses_hooks": ["useState", "useEffect"],
  "has_typescript_errors": false
}}
```"""


def _stub_refactored_source(user_text: str) -> str:
    name = _extract_component_name(user_text)
    base = name.replace("Component", "")
    return f"""Refactored React code — anti-patterns removed, memoisation applied:

```json
{{
  "file_path": "src/components/{base}.tsx",
  "content": "import React, {{ useCallback, useEffect, memo }} from 'react';\\nimport {{ DhlButton }} from '@dhl-official/react-library';\\nimport {{ DHL_BUTTON }} from '@dhl-official/stencil-library';\\n\\ninterface {base}Props {{\\n  data?: unknown[];\\n  onItemSelected?: (item: unknown) => void;\\n}}\\n\\nexport const {base}: React.FC<{base}Props> = memo(({{ data = [], onItemSelected }}) => {{\\n  useEffect(() => {{\\n    // mount\\n    return () => {{\\n      // cleanup\\n    }};\\n  }}, []);\\n\\n  const handleSelect = useCallback(() => {{\\n    onItemSelected?.(data[0]);\\n  }}, [data, onItemSelected]);\\n\\n  return (\\n    <div>\\n      <h1>{base}</h1>\\n      {{data.map((item, i) => (\\n        <div key={{i}}>{{String(item)}}</div>\\n      ))}}\\n      <DhlButton variant={{DHL_BUTTON.VARIANT.PRIMARY}} onDhlClick={{handleSelect}}>\\n        Select\\n      </DhlButton>\\n    </div>\\n  );\\n}});",
  "optimizations_applied": ["Added React.memo for performance", "Converted inline handler to useCallback"],
  "removed_anti_patterns": ["Removed inline arrow function in JSX prop"],
  "performance_improvements": ["Memoised component with React.memo"]
}}
```"""


def _stub_test_plan(user_text: str) -> str:
    name = _extract_component_name(user_text)
    base = name.replace("Component", "")
    return f"""TestPlan ready for the migrated app:

```json
{{
  "strategy_summary": "Unit-first with React Testing Library; integration tests for service hooks and routed flows; a manual pass for visual regression and accessibility.",
  "framework": "vitest",
  "coverage_target_pct": 80,
  "matrix": [
    {{
      "target": "{base}",
      "type": "unit",
      "scenarios": [
        "renders without crashing",
        "renders one entry per item in props.data",
        "calls onItemSelected via onDhlClick when the DHL button is clicked"
      ],
      "priority": "high"
    }},
    {{
      "target": "{base}Service → use{base}() hook",
      "type": "integration",
      "scenarios": ["fetches data on mount", "surfaces error state on HTTP failure"],
      "priority": "high"
    }}
  ],
  "mocking_strategy": "Mock fetch/HttpClient calls with vi.fn(); wrap providers in a test harness; stub routing with MemoryRouter.",
  "manual_checklist": [
    "Visual regression vs. the original Angular screens",
    "Keyboard navigation and screen-reader labels on DHL components",
    "Cross-browser smoke (Chrome, Firefox, Safari)"
  ]
}}
```"""


def _stub_test_suite(user_text: str) -> str:
    name = _extract_component_name(user_text)
    base = name.replace("Component", "")
    return f"""TestSuite generated for {base}:

```json
{{
  "tests": [
    {{
      "name": "{base} renders without crashing",
      "type": "unit",
      "file_path": "src/components/__tests__/{base}.test.tsx",
      "content": "import {{ describe, it, expect, vi }} from 'vitest';\\nimport {{ render, screen }} from '@testing-library/react';\\nimport {{ {base} }} from '../{base}';\\n\\ndescribe('{base}', () => {{\\n  it('renders without crashing', () => {{\\n    render(<{base} />);\\n    expect(screen.getByText('{base}')).toBeInTheDocument();\\n  }});\\n\\n  it('calls onItemSelected when button clicked', async () => {{\\n    const handler = vi.fn();\\n    render(<{base} data={{[{{id: 1}}]}} onItemSelected={{handler}} />);\\n    await userEvent.click(screen.getByRole('button', {{ name: /select/i }}));\\n    expect(handler).toHaveBeenCalledWith({{id: 1}});\\n  }});\\n}});",
      "covers": ["{base} rendering", "onItemSelected callback"]
    }}
  ],
  "coverage_targets": ["{base}"],
  "framework": "vitest",
  "total_tests": 2
}}
```"""


def _stub_validation_report(_: str) -> str:
    return """Validation complete — code passes all quality checks:

```json
{
  "passed": true,
  "issues": [
    {
      "severity": "info",
      "category": "best-practice",
      "file_path": "src/components/App.tsx",
      "line": null,
      "message": "Consider adding aria-label to interactive elements",
      "suggestion": "Add aria-label for screen reader accessibility"
    }
  ],
  "typescript_errors": 0,
  "eslint_warnings": 0,
  "react_violations": 0,
  "overall_score": 97.0
}
```

✅ PASS — migration output meets all React 18+ and DHL DUIL standards."""


def _stub_migration_report(_: str) -> str:
    return """
╔════════════════════════════════════════╗
║   Angular → React Migration Report    ║
╚════════════════════════════════════════╝

Status: ✅ SUCCESS

Metrics:
  • Files migrated:     3
  • Components created: 1
  • Custom hooks:       1
  • Tests generated:    2
  • Duration:           1.2s
  • Context escalations: 0

Validation:
  • TypeScript errors:  0
  • ESLint warnings:    0
  • React violations:   0
  • Quality score:      97/100

Next Steps:
  1. Run test suite: npm test
  2. Add @dhl-official/react-library to package.json
  3. Configure Vite build system
  4. Review Context provider placement

```json
{
  "success": true,
  "metrics": {
    "files_migrated": 3,
    "components_created": 1,
    "hooks_generated": 1,
    "tests_written": 2,
    "total_tokens_used": 0,
    "duration_seconds": 1.2
  },
  "output_files": ["src/components/App.tsx", "src/contexts/AppContext.tsx"],
  "next_steps": ["npm test", "update package.json", "configure Vite"],
  "warnings": []
}
```"""


def _stub_parser_response(user_text: str) -> str:
    name = _extract_component_name(user_text)
    return f"""[STUB] Angular parser analysis:

**Component:** {name}
**Selector:** app-{name.replace("Component", "").lower()}
**Lifecycle hooks:** ngOnInit, ngOnDestroy
**Inputs:** data
**Outputs:** itemSelected
**Dependencies:** none detected
**Forms:** none
**Router:** none
**Template:** external (.html)

Ready for conversion to React."""


def _stub_converter_response(user_text: str) -> str:
    name = _extract_component_name(user_text)
    base = name.replace("Component", "")
    return f"""[STUB] Converted to React 18+:

```tsx
import React, {{ useEffect }} from 'react';
import {{ DhlButton }} from '@dhl-official/react-library';
import {{ DHL_BUTTON }} from '@dhl-official/stencil-library';

interface {base}Props {{
  data?: unknown[];
  onItemSelected?: (item: unknown) => void;
}}

export const {base}: React.FC<{base}Props> = ({{ data = [], onItemSelected }}) => {{
  useEffect(() => {{
    // ngOnInit
  }}, []);

  return (
    <div>
      <h1>{base}</h1>
      {{data.map((item, i) => (
        <div key={{i}}>{{String(item)}}</div>
      ))}}
      <DhlButton
        variant={{DHL_BUTTON.VARIANT.PRIMARY}}
        onDhlClick={{() => onItemSelected?.(data[0])}}
      >
        Select
      </DhlButton>
    </div>
  );
}};
```"""


def _stub_fixer_response(user_text: str) -> str:
    return f"""[STUB] Code review — no issues found.

Static analysis: ✅ No errors, no warnings.
- No class components
- No implicit `any` types
- No Angular remnants
- React import present
- All hooks at top level

{user_text if "```" in user_text else _stub_converter_response(user_text)}"""


def _stub_validator_response(_: str) -> str:
    return """[STUB] Validation result:

✅ PASS

Checks performed:
- ✅ No class components
- ✅ No TypeScript errors
- ✅ No Angular remnants
- ✅ All hooks used correctly
- ✅ DHL DUIL components used (no raw HTML)
- ✅ React import present

Quality score: 97/100
No blocking issues found."""


# These patterns only match actual Angular source code, not conversational mentions
_ANGULAR_CODE_PATTERNS = [
    r"@Component\s*\(",
    r"@Injectable\s*\(",
    r"@NgModule\s*\(",
    r"@Directive\s*\(",
    r"@Pipe\s*\(",
    r"export\s+class\s+\w+\s+implements\s+On(Init|Destroy|Changes)",
    r"export\s+class\s+\w+(Component|Service|Module|Guard|Pipe|Directive)",
]


def _stub_root_response(user_text: str) -> str:
    # Only treat as Angular code if actual decorator/class syntax is present
    if any(re.search(pat, user_text) for pat in _ANGULAR_CODE_PATTERNS):
        return _stub_converter_response(user_text)
    return (
        "Hello! I'm **NgReact**, your Angular-to-React migration assistant.\n\n"
        "Here's what I can do:\n"
        "- **Convert** a pasted Angular component → React 18+ (paste your code directly)\n"
        "- **Migrate** a full Angular project → `Migrate C:\\projects\\my-app`\n"
        "- **Answer** Angular or React questions\n\n"
        "What would you like to convert today?"
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_DISPATCHERS: dict[str, object] = {
    "analyzer_agent_v3":          _stub_analysis_report,
    "risk_detection_agent_v3":    _stub_risk_report,
    "migration_planner_agent_v3": _stub_migration_plan,
    "state_migration_agent_v3":   _stub_state_plan,
    "transformer_agent_v3":       _stub_react_source,
    "refactor_agent_v3":          _stub_refactored_source,
    "test_planner_agent_v3":      _stub_test_plan,
    "test_generation_agent_v3":   _stub_test_suite,
    "validator_agent_v3":         _stub_validation_report,
    "report_agent_v3":            _stub_migration_report,
    "parser_agent":               _stub_parser_response,
    "converter_agent":            _stub_converter_response,
    "fixer_agent":                _stub_fixer_response,
    "validator_agent":            _stub_validator_response,
    "ngreact_v3":                 _stub_root_response,
    "ngreact":                    _stub_root_response,
    "unknown":                    _stub_root_response,
}


# ---------------------------------------------------------------------------
# Multi-turn helpers for root agent orchestration
# ---------------------------------------------------------------------------

def _get_first_user_text(llm_request: LlmRequest) -> str:
    """Return the FIRST user message in the conversation (the original request)."""
    for content in llm_request.contents or []:
        if getattr(content, "role", "") == "user":
            for part in getattr(content, "parts", None) or []:
                text = getattr(part, "text", None)
                if text and text.strip():
                    return text
    return ""


def _get_function_calls_in_history(llm_request: LlmRequest) -> list[str]:
    """Return names of every functionCall already made in the conversation."""
    called: list[str] = []
    for content in llm_request.contents or []:
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            if fc:
                name = getattr(fc, "name", None)
                if name:
                    called.append(name)
    return called


def _make_function_call_response(fn_name: str, arg_text: str) -> LlmResponse:
    """Build an LlmResponse that contains a single functionCall part."""
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(
                function_call=types.FunctionCall(
                    name=fn_name,
                    args={"request": arg_text[:2000]},
                )
            )],
        ),
        finish_reason=types.FinishReason.STOP,
        turn_complete=True,
    )


def _make_text_response(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        finish_reason=types.FinishReason.STOP,
        turn_complete=True,
    )


# ---------------------------------------------------------------------------
# StubLlm class
# ---------------------------------------------------------------------------

class StubLlm(BaseLlm):
    """Stub LLM — returns scripted, agent-aware responses without any HTTP calls.

    Root agents (ngreact_v3 / ngreact) generate real functionCall parts so that
    ADK actually invokes the sub-agents, each of which returns its own canned
    response via its own StubLlm call.

    Useful for:
      - CI/CD pipeline testing
      - Local development without DHL VPN
      - Debugging the pipeline flow without spending API tokens
    """

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"stub\/.*"]

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        role = _detect_role(llm_request)

        # ── Sub-agents: return their canned text response immediately ──────────
        if role not in ("ngreact_v3", "ngreact", "unknown"):
            user_text = _extract_user_text(llm_request)
            dispatcher = _DISPATCHERS.get(role, _stub_root_response)
            yield _make_text_response(dispatcher(user_text))  # type: ignore[arg-type]
            return

        # ── Root agents: drive the pipeline via actual functionCall parts ──────
        first_text = _get_first_user_text(llm_request)
        called     = _get_function_calls_in_history(llm_request)
        has_angular = any(re.search(pat, first_text) for pat in _ANGULAR_CODE_PATTERNS)

        if not has_angular:
            # Conversational message — reply directly, no sub-agents
            yield _make_text_response(_stub_root_response(first_text))
            return

        # V3 single-component pipeline: transformer → refactor → validator
        # Legacy pipeline: parser → converter → fixer → validator
        if role == "ngreact_v3":
            pipeline = [
                "transformer_agent_v3",
                "refactor_agent_v3",
                "validator_agent_v3",
            ]
            final_msg = (
                "✅ **Migration complete** (stub run)\n\n"
                "Pipeline executed:\n"
                "1. `transformer_agent_v3` — Angular → React 18+\n"
                "2. `refactor_agent_v3` — Optimised, DHL DUIL applied\n"
                "3. `validator_agent_v3` — Quality gate: **PASS** (97/100)\n\n"
                "Your converted component is ready. "
                "Switch to `NGREACT_LLM_MODE=openai` with a real key for a full-quality migration."
            )
        else:  # ngreact (legacy)
            pipeline = [
                "parser_agent",
                "converter_agent",
                "fixer_agent",
                "validator_agent",
            ]
            final_msg = (
                "✅ **Migration complete** (stub run)\n\n"
                "Legacy pipeline executed: Parse → Convert → Fix → Validate.\n"
                "The React component is ready above."
            )

        # Find the next uncalled step and call it
        for step in pipeline:
            if step not in called:
                yield _make_function_call_response(step, first_text)
                return

        # All pipeline steps done — return final summary
        yield _make_text_response(final_msg)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_stub_model() -> StubLlm:
    """Return a StubLlm instance. No env vars or API keys required."""
    return StubLlm(model="stub/test")
