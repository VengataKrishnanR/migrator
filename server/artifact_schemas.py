"""Lightweight shape validators for Phase 1 agent outputs.

Each validator checks that the parsed dict has the fields downstream stages and
the chunker depend on, then returns the dict unchanged (we persist the raw JSON
as the artifact). A raised exception triggers the invoker's one repair retry.
These are intentionally permissive about *content* (the LLM owns that) and strict
only about *structure*.
"""
from __future__ import annotations

from typing import Any


def _require(d: Any, keys: tuple[str, ...], name: str) -> dict:
    if not isinstance(d, dict):
        raise TypeError(f"{name} must be a JSON object, got {type(d).__name__}")
    missing = [k for k in keys if k not in d]
    if missing:
        raise KeyError(f"{name} missing required field(s): {', '.join(missing)}")
    return d


def validate_analysis(d: Any) -> dict:
    d = _require(d, ("components", "services"), "AnalysisReport")
    if not isinstance(d["components"], list) or not isinstance(d["services"], list):
        raise TypeError("AnalysisReport.components and .services must be arrays")
    return d


def validate_risk(d: Any) -> dict:
    d = _require(d, ("risks", "overall_risk_score"), "RiskReport")
    if not isinstance(d["risks"], list):
        raise TypeError("RiskReport.risks must be an array")
    return d


def validate_plan(d: Any) -> dict:
    d = _require(d, ("chunks", "execution_order"), "MigrationPlan")
    if not isinstance(d["chunks"], list) or not isinstance(d["execution_order"], list):
        raise TypeError("MigrationPlan.chunks and .execution_order must be arrays")
    if not d["chunks"]:
        raise ValueError("MigrationPlan has no chunks")
    return d


def validate_state(d: Any) -> dict:
    d = _require(d, ("mappings",), "StateMigrationPlan")
    if not isinstance(d["mappings"], list):
        raise TypeError("StateMigrationPlan.mappings must be an array")
    return d


def validate_react_source(d: Any) -> dict:
    d = _require(d, ("file_path", "content"), "ReactSource")
    if not str(d["content"]).strip():
        raise ValueError("ReactSource.content is empty")
    return d


def validate_refactored(d: Any) -> dict:
    d = _require(d, ("file_path", "content"), "RefactoredReactSource")
    if not str(d["content"]).strip():
        raise ValueError("RefactoredReactSource.content is empty")
    return d


def validate_test_plan(d: Any) -> dict:
    d = _require(d, ("strategy_summary", "matrix"), "TestPlan")
    if not isinstance(d["matrix"], list) or not d["matrix"]:
        raise ValueError("TestPlan.matrix must be a non-empty array")
    return d


def validate_test_suite(d: Any) -> dict:
    d = _require(d, ("tests",), "TestSuite")
    if not isinstance(d["tests"], list):
        raise TypeError("TestSuite.tests must be an array")
    return d


def validate_validation(d: Any) -> dict:
    d = _require(d, ("passed", "issues"), "ValidationReport")
    if not isinstance(d["passed"], bool):
        raise TypeError("ValidationReport.passed must be a boolean")
    if not isinstance(d["issues"], list):
        raise TypeError("ValidationReport.issues must be an array")
    return d


def validate_report(d: Any) -> dict:
    d = _require(d, ("success", "metrics"), "MigrationReport")
    if not isinstance(d["success"], bool):
        raise TypeError("MigrationReport.success must be a boolean")
    return d
