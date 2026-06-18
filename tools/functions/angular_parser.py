"""
Angular source parser tool for NgReact.

Accepts Angular TypeScript / HTML source code and returns a structured
text analysis of all Angular artefacts found (components, services, modules,
routes, inputs, outputs, lifecycle hooks, directives, forms, guards).

This is a **LLM-assisted** analysis: the raw source is passed directly to
the parser_agent's LLM; this function is the FunctionTool entry-point that
validates input and formats the request.
"""
from __future__ import annotations

import re


# ── Supported Angular artefact patterns (for pre-flight sanity check) ─────────
_ANGULAR_MARKERS = [
    r"@Component\s*\(",
    r"@Injectable\s*\(",
    r"@NgModule\s*\(",
    r"@Input\s*\(",
    r"@Output\s*\(",
    r"@Directive\s*\(",
    r"@Pipe\s*\(",
]

_MAX_SOURCE_LENGTH = 200_000  # chars — guard against accidental huge pastes


def parse_angular_source(source_code: str, file_name: str = "unknown.ts") -> str:
    """Parse Angular TypeScript source and return a structured analysis.

    This function validates the input and returns a structured prompt for the
    parser_agent's LLM to analyse. The agent itself produces the final
    structured analysis; this tool handles input hygiene.

    Args:
        source_code: Full content of one or more Angular source files.
                     Multiple files can be separated by:
                     ``// ── FILE: <filename> ──`` comment headers.
        file_name:   Name of the primary file being parsed (for context).

    Returns:
        The source code with a pre-analysis header, ready for LLM parsing,
        or an error message if the input is invalid.
    """
    if not source_code or not source_code.strip():
        return "[parse_angular_source error] No source code provided."

    if len(source_code) > _MAX_SOURCE_LENGTH:
        return (
            f"[parse_angular_source error] Source code is too large "
            f"({len(source_code):,} chars). Split into smaller files and parse each separately."
        )

    # Detect Angular markers — warn if none found but still proceed.
    found_markers = [m for m in _ANGULAR_MARKERS if re.search(m, source_code)]
    if not found_markers:
        warning = (
            "⚠️  WARNING: No Angular decorators detected in the provided source. "
            "Verify this is Angular TypeScript code.\n\n"
        )
    else:
        warning = ""

    detected = ", ".join(
        m.replace(r"\s*\(", "()").replace("\\", "") for m in found_markers
    ) or "none detected"

    header = (
        f"FILE: {file_name}\n"
        f"Angular artefacts detected: {detected}\n"
        f"Source length: {len(source_code):,} characters\n"
        "──────────────────────────────────────────────────────────\n\n"
    )

    return f"{warning}{header}{source_code}"
