"""Agent factories for 9-stage artifact-driven migration pipeline.

Each factory builds a specialized agent that consumes and produces strongly-typed
artifacts, operating within hierarchical context constraints for token optimization.
"""

from .analyzer import build_analyzer_agent
from .risk_detection import build_risk_detection_agent
from .migration_planner import build_migration_planner_agent
from .state_migration import build_state_migration_agent
from .transformer import build_transformer_agent
from .refactor import build_refactor_agent
from .test_planner import build_test_planner_agent
from .test_generation import build_test_generation_agent
from .validator import build_validator_agent_v3
from .report import build_report_agent

__all__ = [
    "build_analyzer_agent",
    "build_risk_detection_agent",
    "build_migration_planner_agent",
    "build_state_migration_agent",
    "build_transformer_agent",
    "build_refactor_agent",
    "build_test_planner_agent",
    "build_test_generation_agent",
    "build_validator_agent_v3",
    "build_report_agent",
]
