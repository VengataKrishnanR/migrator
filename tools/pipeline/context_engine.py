"""Hierarchical context engine for token-optimized agent execution.

Manages context level escalation, projection, and caching to minimize token
usage while maintaining agent effectiveness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import ContextLevel, MigrationContext


class EscalationTrigger(Enum):
    """Reasons for escalating context level."""

    AGENT_REQUEST = "agent_request"         # Agent explicitly requested more context
    RETRY_AFTER_FAILURE = "retry_failure"   # Retry after validation failure
    INSUFFICIENT_INFO = "insufficient_info" # Agent indicated missing information
    MANUAL = "manual"                       # Manual escalation


@dataclass
class EscalationEvent:
    """Record of a context level escalation."""

    agent_name: str
    from_level: ContextLevel
    to_level: ContextLevel
    trigger: EscalationTrigger
    reason: str = ""
    timestamp: float = 0.0


@dataclass
class ContextEscalationPolicy:
    """Policy for controlling context level escalation.

    Defines when and how context can escalate to higher (more expensive)
    levels during agent execution.
    """

    max_escalations_per_agent: int = 2
    allow_skip_levels: bool = False  # If True, can jump L1->L3; if False, must go L1->L2->L3
    auto_escalate_on_retry: bool = True
    record_escalations: bool = True
    escalation_log: list[EscalationEvent] = field(default_factory=list)

    def can_escalate(
        self,
        agent_name: str,
        current_level: ContextLevel,
        target_level: ContextLevel,
    ) -> tuple[bool, str]:
        """Check if escalation is permitted by policy.

        Args:
            agent_name: Name of requesting agent
            current_level: Current context level
            target_level: Desired context level

        Returns:
            (allowed, reason) tuple
        """
        # Count previous escalations for this agent
        agent_escalations = [
            e for e in self.escalation_log if e.agent_name == agent_name
        ]

        if len(agent_escalations) >= self.max_escalations_per_agent:
            return False, f"Max escalations ({self.max_escalations_per_agent}) reached"

        # Check level skipping policy
        if not self.allow_skip_levels:
            level_diff = target_level - current_level
            if level_diff > 1:
                return False, "Level skipping disabled; must escalate incrementally"

        # Check bounds
        if target_level > ContextLevel.FULL_SOURCE:
            return False, "Cannot escalate beyond FULL_SOURCE level"

        if target_level <= current_level:
            return False, "Target level must be higher than current"

        return True, "Escalation allowed"

    def record_escalation(
        self,
        agent_name: str,
        from_level: ContextLevel,
        to_level: ContextLevel,
        trigger: EscalationTrigger,
        reason: str = "",
    ) -> None:
        """Record an escalation event."""
        if self.record_escalations:
            import time

            self.escalation_log.append(
                EscalationEvent(
                    agent_name=agent_name,
                    from_level=from_level,
                    to_level=to_level,
                    trigger=trigger,
                    reason=reason,
                    timestamp=time.time(),
                )
            )


class ContextEngine:
    """Context projection and escalation engine.

    Manages MigrationContext projection to appropriate levels for each agent
    stage and handles escalation requests.
    """

    def __init__(
        self,
        context: MigrationContext,
        policy: ContextEscalationPolicy | None = None,
    ):
        """Initialize context engine.

        Args:
            context: Full migration context
            policy: Escalation policy (defaults to permissive)
        """
        self.context = context
        self.policy = policy or ContextEscalationPolicy()
        self.current_level = ContextLevel.METADATA_ONLY

    def project(self, level: ContextLevel) -> dict[str, Any]:
        """Project context to specified level.

        Args:
            level: Target context level

        Returns:
            Context payload at requested level
        """
        return self.context.to_level_payload(level)

    def escalate(
        self,
        agent_name: str,
        target_level: ContextLevel,
        trigger: EscalationTrigger = EscalationTrigger.AGENT_REQUEST,
        reason: str = "",
    ) -> tuple[bool, dict[str, Any] | None]:
        """Attempt to escalate context level.

        Args:
            agent_name: Name of requesting agent
            target_level: Desired context level
            trigger: Escalation trigger
            reason: Optional reason for escalation

        Returns:
            (success, projected_context) tuple
        """
        allowed, message = self.policy.can_escalate(
            agent_name, self.current_level, target_level
        )

        if not allowed:
            return False, None

        # Record escalation
        self.policy.record_escalation(
            agent_name=agent_name,
            from_level=self.current_level,
            to_level=target_level,
            trigger=trigger,
            reason=reason or message,
        )

        # Update level and project
        old_level = self.current_level
        self.current_level = target_level
        projected = self.project(target_level)

        return True, projected

    def get_escalation_summary(self) -> dict[str, Any]:
        """Get summary of escalation history.

        Returns:
            Dict with escalation statistics
        """
        return {
            "total_escalations": len(self.policy.escalation_log),
            "current_level": self.current_level.name,
            "escalations_by_agent": {
                agent: sum(1 for e in self.policy.escalation_log if e.agent_name == agent)
                for agent in set(e.agent_name for e in self.policy.escalation_log)
            },
            "events": [
                {
                    "agent": e.agent_name,
                    "from": e.from_level.name,
                    "to": e.to_level.name,
                    "trigger": e.trigger.value,
                    "reason": e.reason,
                }
                for e in self.policy.escalation_log
            ],
        }
