"""Tools package for the NgReact ADK agent.

Sub-packages
------------
agents/      — Sub-agents (9-stage artifact-driven pipeline)
functions/   — Plain FunctionTool callables
pipeline/    — Pipeline infrastructure (models, contracts, orchestration)
knowledge/   — Knowledge base FunctionTools built from the registry
mcp/         — MCP tool integrations (future)
"""
from .functions.angular_parser import parse_angular_source
from .functions.react_validator import validate_react_code
from .functions.pipeline_tools import (
    analyze_project_structure,
    estimate_migration_complexity,
    validate_chunk_dependencies,
    read_angular_file,
    ingest_zip,
    clone_git_repo,
)

__all__ = [
    "parse_angular_source",
    "validate_react_code",
    "analyze_project_structure",
    "estimate_migration_complexity",
    "validate_chunk_dependencies",
    "read_angular_file",
    "ingest_zip",
    "clone_git_repo",
]
