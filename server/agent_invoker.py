from __future__ import annotations

import asyncio
from typing import Any, Callable

from google.adk.runners import InMemoryRunner
from google.genai import types

from .json_utils import AgentInvocationError, extract_json  # noqa: F401 — re-exported

_APP = "ngreact_v3"


# ✅ FIXED: robust extractor for ADK responses
def _collect_final_text(agent, prompt: str, session_id: str) -> str:
    import sys
    import asyncio as aio

    async def _run() -> str:
        runner = InMemoryRunner(agent=agent, app_name=_APP)

        await runner.session_service.create_session(
            app_name=_APP,
            user_id="job",
            session_id=session_id
        )

        msg = types.Content(role="user", parts=[types.Part(text=prompt)])

        final = ""
        event_count = 0

        try:
            async for ev in runner.run_async(
                user_id="job",
                session_id=session_id,
                new_message=msg
            ):
                event_count += 1
                ev_type = type(ev).__name__
                is_final = ev.is_final_response()
                print(f"[EV#{event_count}] type={ev_type} final={is_final}", file=sys.stderr)

                # ── Check for LLM-level errors FIRST ──────────────────────────
                error_code = getattr(ev, "error_code", None)
                error_msg = getattr(ev, "error_message", None)
                if error_code:
                    print(f"[EV#{event_count}] LLM ERROR code={error_code} msg={error_msg}", file=sys.stderr)
                    raise AgentInvocationError(
                        f"LLM returned HTTP {error_code}: {error_msg}. "
                        f"Check your APIGEE_API_KEY and APIGEE_PROXY_URL in .env."
                    )

                # ✅ 1. Direct text (rare but keep)
                if hasattr(ev, "text") and ev.text:
                    print(f"[EV#{event_count}] extracted from .text", file=sys.stderr)
                    final = ev.text

                # ✅ 2. Content parts (PRIMARY SOURCE)
                if hasattr(ev, "content") and ev.content:
                    parts = getattr(ev.content, "parts", None)
                    print(f"[EV#{event_count}] has content, parts={type(parts).__name__} len={len(parts) if parts else 0}", file=sys.stderr)

                    if parts:
                        for i, part in enumerate(parts):
                            part_type = type(part).__name__
                            print(f"[EV#{event_count}] part[{i}] type={part_type}", file=sys.stderr)

                            # ✅ plain text
                            if hasattr(part, "text") and part.text:
                                print(f"[EV#{event_count}] part[{i}] extracted .text, len={len(part.text)}", file=sys.stderr)
                                final = part.text

                            # ✅ structured payload (don't stringify — this is likely the issue)
                            elif hasattr(part, "inline_data") and part.inline_data:
                                inline_type = type(part.inline_data).__name__
                                print(f"[EV#{event_count}] part[{i}] has inline_data type={inline_type}", file=sys.stderr)
                                if hasattr(part.inline_data, "to_json"):
                                    final = part.inline_data.to_json()
                                    print(f"[EV#{event_count}] part[{i}] used .to_json()", file=sys.stderr)
                                elif isinstance(part.inline_data, str):
                                    final = part.inline_data
                                    print(f"[EV#{event_count}] part[{i}] is already string", file=sys.stderr)
                                else:
                                    final = str(part.inline_data)
                                    print(f"[EV#{event_count}] part[{i}] stringified (fallback)", file=sys.stderr)

                            # ✅ function/tool output
                            elif hasattr(part, "function_call") and part.function_call:
                                print(f"[EV#{event_count}] part[{i}] has function_call", file=sys.stderr)
                                final = str(part.function_call)

                # Do NOT fall back to ev.actions — stringifying ADK metadata produces
                # text like "skip_summarization=None state_delta={}" which passes
                # JSON extraction but fails schema validation with misleading errors.

        except AgentInvocationError:
            # Surface auth/HTTP errors immediately — no point retrying
            raise
        except Exception as e:
            print(f"[AGENT_ERROR] {type(e).__name__}: {e}", file=sys.stderr)
            raise

        print(f"[AGENT_COMPLETE] session={session_id} events={event_count} final_len={len(final)}", file=sys.stderr)
        print(f"[AGENT_COMPLETE] first 300 chars: {final[:300]}", file=sys.stderr)

        return final

    try:
        return asyncio.run(asyncio.wait_for(_run(), timeout=120))
    except asyncio.TimeoutError:
        raise AgentInvocationError("Agent invocation timeout (>120s)")


# ✅ IMPROVED invoke logic
def invoke_agent(
    agent,
    prompt: str,
    *,
    session_id: str,
    validate: Callable[[dict], Any] | None = None
) -> Any:
    import sys

    last_err: Exception | None = None
    attempt_prompt = prompt

    for attempt in range(2):
        print(f"[INVOKE_AGENT] attempt={attempt+1}/2 session={session_id}", file=sys.stderr)

        try:
            text = _collect_final_text(
                agent,
                attempt_prompt,
                f"{session_id}_a{attempt}"
            )
        except AgentInvocationError:
            # Auth/HTTP errors from the LLM — don't retry, surface immediately
            raise

        print(f"[INVOKE_AGENT] response length={len(text)}", file=sys.stderr)

        # ✅ IMPORTANT: log raw response for debugging
        if text:
            print(f"[RAW RESPONSE PREVIEW]\n{text[:500]}", file=sys.stderr)

        if not text.strip():
            last_err = AgentInvocationError("empty agent response")

        else:
            try:
                data = extract_json(text)
                result = validate(data) if validate else data
                print("[INVOKE_AGENT] SUCCESS", file=sys.stderr)
                return result

            except Exception as e:
                last_err = e
                print(f"[INVOKE_AGENT] JSON ERROR: {e}", file=sys.stderr)

        # Repair prompt: include the exact validation error so the LLM knows what failed
        attempt_prompt = (
            f"{prompt}\n\n"
            f"IMPORTANT — your previous response was rejected with this error: {last_err}\n"
            "Please respond ONLY with a valid JSON object inside a ```json code block. "
            "All required fields must be present. Arrays such as 'chunks' and 'execution_order' "
            "must contain actual items — empty arrays are not accepted."
        )

    raise AgentInvocationError(f"Agent failed after retry: {last_err}")
