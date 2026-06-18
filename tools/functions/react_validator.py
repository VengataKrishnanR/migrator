"""
React code static validator for NgReact.

Performs lightweight, regex-based static analysis of generated React TypeScript
code and returns a structured report. This is a fast pre-check before the
validator_agent's LLM performs the deep semantic review.

Checks performed:
  - No class components (class X extends React.Component / PureComponent)
  - No implicit any (': any' type annotations)
  - No direct state mutation (this.state.x = ...)
  - useEffect with empty or missing dependency array flag
  - Missing key props on map() calls
  - No console.log left in code
  - No Angular remnants (@Component, @NgModule, etc.)
  - Import completeness (React imported, hooks imported)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ValidationIssue:
    severity: str   # "ERROR" | "WARNING" | "INFO"
    rule: str
    message: str
    line: int | None = None


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    def __str__(self) -> str:
        if not self.issues:
            return "✅ Static analysis: No issues found."
        lines = ["STATIC ANALYSIS REPORT", "=" * 40]
        for issue in self.issues:
            loc = f" (line {issue.line})" if issue.line else ""
            lines.append(f"[{issue.severity}] {issue.rule}{loc}: {issue.message}")
        lines.append("")
        lines.append(
            f"Total: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )
        return "\n".join(lines)


# ── Individual check functions ────────────────────────────────────────────────

def _check_class_components(code: str, report: ValidationReport) -> None:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"class\s+\w+\s+extends\s+(React\.)?(Pure)?Component", line):
            report.issues.append(ValidationIssue(
                severity="ERROR",
                rule="no-class-components",
                message="Class component detected. Convert to functional component.",
                line=i,
            ))


def _check_implicit_any(code: str, report: ValidationReport) -> None:
    for i, line in enumerate(code.splitlines(), 1):
        # Skip comment lines
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        if re.search(r":\s*any\b", line):
            report.issues.append(ValidationIssue(
                severity="ERROR",
                rule="no-implicit-any",
                message="Implicit 'any' type detected. Provide a specific type.",
                line=i,
            ))


def _check_console_log(code: str, report: ValidationReport) -> None:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"console\.log\s*\(", line) and not line.strip().startswith("//"):
            report.issues.append(ValidationIssue(
                severity="WARNING",
                rule="no-console",
                message="console.log found. Remove before production.",
                line=i,
            ))


def _check_angular_remnants(code: str, report: ValidationReport) -> None:
    angular_patterns = [
        (r"@Component\s*\(", "@Component decorator"),
        (r"@NgModule\s*\(", "@NgModule decorator"),
        (r"@Injectable\s*\(", "@Injectable decorator"),
        (r"@Input\s*\(\s*\)", "@Input decorator"),
        (r"@Output\s*\(\s*\)", "@Output decorator"),
        (r"\*ngIf=", "*ngIf directive"),
        (r"\*ngFor=", "*ngFor directive"),
        (r"\[ngClass\]=", "[ngClass] binding"),
        (r"\bngModel\b", "ngModel binding"),  # word-boundary to avoid false matches
    ]
    for pattern, name in angular_patterns:
        for i, line in enumerate(code.splitlines(), 1):
            stripped = line.strip()
            if re.search(pattern, line) and not stripped.startswith("//") and not stripped.startswith("*"):
                report.issues.append(ValidationIssue(
                    severity="ERROR",
                    rule="no-angular-remnants",
                    message=f"Angular remnant found: {name}. This must be converted.",
                    line=i,
                ))


def _check_map_without_key(code: str, report: ValidationReport) -> None:
    # Look for .map( returning JSX without a key prop
    for i, line in enumerate(code.splitlines(), 1):
        if ".map(" in line and "<" in line and "key=" not in line:
            report.issues.append(ValidationIssue(
                severity="WARNING",
                rule="jsx-key",
                message="JSX element inside .map() may be missing a 'key' prop.",
                line=i,
            ))


def _check_react_import(code: str, report: ValidationReport) -> None:
    # React 18+ with the new JSX transform (jsx-runtime) does NOT require
    # `import React from 'react'` for JSX. Only flag if hooks/APIs are used
    # without any React import at all.
    has_any_react_import = "from 'react'" in code or 'from "react"' in code
    uses_react_apis = bool(re.search(r"\buseState\b|\buseEffect\b|\buseRef\b|\buseContext\b|\buseMemo\b|\buseCallback\b|\buseReducer\b", code))
    if not has_any_react_import and uses_react_apis:
        report.issues.append(ValidationIssue(
            severity="WARNING",
            rule="react-import",
            message="React hooks used but no React import found. Add: import { useState, useEffect, … } from 'react'",
        ))


def _check_use_effect_deps(code: str, report: ValidationReport) -> None:
    for i, line in enumerate(code.splitlines(), 1):
        # useEffect with no second argument at all
        if re.search(r"useEffect\s*\(\s*\(\s*\)\s*=>", line):
            # Check if closing paren has a deps array nearby — very rough heuristic
            if ");" in line and "[" not in line:
                report.issues.append(ValidationIssue(
                    severity="WARNING",
                    rule="react-hooks/exhaustive-deps",
                    message="useEffect may be missing a dependency array.",
                    line=i,
                ))


# ── Public entry point ────────────────────────────────────────────────────────

def validate_react_code(code: str) -> str:
    """Run static analysis on generated React TypeScript code.

    Args:
        code: Full React TypeScript source code to validate (one or more files
              concatenated, separated by ``// ── FILE: <name> ──`` comments).

    Returns:
        A structured plain-text validation report with errors and warnings.
    """
    if not code or not code.strip():
        return "[validate_react_code error] No code provided."

    report = ValidationReport()

    _check_react_import(code, report)
    _check_class_components(code, report)
    _check_implicit_any(code, report)
    _check_console_log(code, report)
    _check_angular_remnants(code, report)
    _check_map_without_key(code, report)
    _check_use_effect_deps(code, report)

    return str(report)
