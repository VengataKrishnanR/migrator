"""Agent contract protocols for V2 pipeline.

Defines base abstractions for consistent agent I/O contracts and execution
metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from .models import ContextLevel

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class AgentContract(Protocol[TInput, TOutput]):
    """Protocol for agent input/output contracts.

    Each V2 agent implements this protocol with specific input and output
    artifact types, ensuring type-safe handoffs between pipeline stages.
    """

    async def execute(self, input_artifact: TInput, context: dict[str, Any]) -> TOutput:
        """Execute agent logic with typed input/output.

        Args:
            input_artifact: Typed input from previous stage
            context: MigrationContext projected to agent's required level

        Returns:
            Typed output artifact for next stage
        """
        ...


@dataclass
class AgentExecutionSpec:
    """Runtime metadata for agent stage execution.

    Defines context requirements, escalation policy, and performance bounds
    for a single agent in the V2 pipeline.
    """

    agent_name: str
    min_context_level: ContextLevel = ContextLevel.METADATA_ONLY
    max_context_level: ContextLevel = ContextLevel.FULL_SOURCE
    allow_escalation: bool = True
    max_retries: int = 2
    timeout_seconds: int = 120
    cache_key_prefix: str = ""

    def __post_init__(self):
        """Set default cache key from agent name."""
        if not self.cache_key_prefix:
            self.cache_key_prefix = f"v3_{self.agent_name}"
