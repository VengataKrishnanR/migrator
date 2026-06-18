"""MigrationJob — the deterministic, resumable heart of the V3 platform.

Control flow lives here, in code, not in an LLM prompt. The V2 root agent used
to *ask* the model to "call each tool exactly once"; V3 enforces order, retries,
gates, and resume programmatically. Agents decide content; this decides sequence.

Every transition writes an audit row (when a store is attached) and is validated
against ``TRANSITIONS`` — illegal moves raise ``IllegalTransitionError`` rather
than silently corrupting state.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from .models import (
    AuditEvent,
    JobRecord,
    JobState,
    TERMINAL_STATES,
)

if TYPE_CHECKING:  # avoid hard dependency / import cycle for offline tests
    from .store import JobStore


class IllegalTransitionError(RuntimeError):
    """Raised when a state transition is not permitted from the current state."""

    def __init__(self, frm: JobState, to: JobState):
        super().__init__(f"Illegal transition: {frm.value} -> {to.value}")
        self.frm = frm
        self.to = to


#: Allowed "forward and branch" transitions. FAILED and CANCELLED are reachable
#: from *any* non-terminal state and are handled separately in ``transition``.
TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.CREATED: frozenset({JobState.INGESTING}),
    JobState.INGESTING: frozenset({JobState.PHASE1_RUNNING}),
    JobState.PHASE1_RUNNING: frozenset({JobState.AWAITING_PLAN_APPROVAL}),
    JobState.AWAITING_PLAN_APPROVAL: frozenset({
        JobState.PHASE2_RUNNING,   # approve
        JobState.PHASE1_RUNNING,   # revise — re-run Phase 1 with feedback
        JobState.REJECTED,         # reject
    }),
    JobState.PHASE2_RUNNING: frozenset({JobState.PHASE3_RUNNING}),
    JobState.PHASE3_RUNNING: frozenset({JobState.PHASE4_RUNNING}),
    JobState.PHASE4_RUNNING: frozenset({JobState.AWAITING_FINAL_APPROVAL}),
    JobState.AWAITING_FINAL_APPROVAL: frozenset({
        JobState.INTEGRATING,      # approve
        JobState.PHASE2_RUNNING,   # revise selected chunks
        JobState.PHASE4_RUNNING,   # revise — re-validate only
        JobState.REJECTED,         # reject
    }),
    JobState.INTEGRATING: frozenset({JobState.COMPLETED}),
    # Terminal states intentionally have no outgoing transitions.
    JobState.COMPLETED: frozenset(),
    JobState.REJECTED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


#: State each interruptible phase resumes *into* if a crash happens mid-phase.
#: Used by JobService.resume() — a RUNNING phase re-enters itself idempotently.
RESUMABLE_RUNNING_STATES: frozenset[JobState] = frozenset({
    JobState.INGESTING,
    JobState.PHASE1_RUNNING,
    JobState.PHASE2_RUNNING,
    JobState.PHASE3_RUNNING,
    JobState.PHASE4_RUNNING,
    JobState.INTEGRATING,
})


def _allowed(frm: JobState, to: JobState) -> bool:
    """Whether ``frm -> to`` is permitted. FAILED/CANCELLED allowed from any
    non-terminal state; otherwise consult the TRANSITIONS table."""
    if frm in TERMINAL_STATES:
        return False
    if to in (JobState.FAILED, JobState.CANCELLED):
        return True
    return to in TRANSITIONS.get(frm, frozenset())


class MigrationJob:
    """Stateful wrapper around a :class:`JobRecord` enforcing legal transitions.

    The optional ``store`` is the persistence + audit sink. When ``None`` (unit
    tests, dry runs) the job is purely in-memory but still enforces transitions.
    """

    def __init__(self, record: JobRecord, store: "JobStore | None" = None):
        self.record = record
        self.store = store

    # -- convenience accessors -------------------------------------------------
    @property
    def id(self) -> str:
        return self.record.id

    @property
    def state(self) -> JobState:
        return self.record.state

    @property
    def is_terminal(self) -> bool:
        return self.record.state in TERMINAL_STATES

    def can_transition(self, to: JobState) -> bool:
        return _allowed(self.record.state, to)

    # -- the one mutation point ------------------------------------------------
    def transition(self, to: JobState, actor: str, reason: str = "") -> JobState:
        """Move to ``to``, persisting the change and writing an audit event.

        Raises:
            IllegalTransitionError: if the move is not permitted.
        """
        frm = self.record.state
        if not _allowed(frm, to):
            raise IllegalTransitionError(frm, to)

        self.record.state = to
        self.record.updated_at = time.time()
        if to == JobState.FAILED and reason and not self.record.error_text:
            self.record.error_text = reason

        if self.store is not None:
            self.store.save_job(self.record)
            self.store.append_audit(
                self.record.id,
                AuditEvent(
                    actor=actor,
                    event="state_transition",
                    detail={"from": frm.value, "to": to.value, "reason": reason},
                ),
            )
        return to

    def fail(self, actor: str, reason: str) -> JobState:
        """Terminal failure with an error message. No-op if already terminal."""
        if self.is_terminal:
            return self.record.state
        self.record.error_text = reason
        return self.transition(JobState.FAILED, actor, reason)

    def cancel(self, actor: str, reason: str = "user cancelled") -> JobState:
        """User-requested cancellation. No-op if already terminal."""
        if self.is_terminal:
            return self.record.state
        return self.transition(JobState.CANCELLED, actor, reason)
