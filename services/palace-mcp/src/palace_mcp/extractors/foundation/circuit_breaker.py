"""Hard circuit breaker for extractor budget enforcement (GIM-101a, T11).

Two checks:
  1. Per-phase boundary: called at start of each phase; raises BUDGET_EXCEEDED
     when total written so far would exceed palace_max_occurrences_total.
  2. Pre-flight resume guard: called before resuming a run; raises
     BUDGET_EXCEEDED_RESUME_BLOCKED if a previous run already hit the budget.

Both are synchronous — no I/O. Budget state is tracked by the caller via the
running total of nodes_written. Neo4j IngestRun.error_code persists the
budget_exceeded state across process restarts.
"""

from __future__ import annotations

import os

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

# Set PALACE_BUDGET_OVERRIDE=1 to bypass budget pre-flight checks.
# Use only for one-shot re-ingest when the budget ceiling must be overridden
# without raising PALACE_MAX_OCCURRENCES_TOTAL first.
_BUDGET_OVERRIDE_VAR = "PALACE_BUDGET_OVERRIDE"


def _budget_override_active() -> bool:
    return bool(os.environ.get(_BUDGET_OVERRIDE_VAR))


def check_phase_budget(
    *,
    nodes_written_so_far: int,
    max_occurrences_total: int,
    phase: str,
) -> None:
    """Raise BUDGET_EXCEEDED if nodes_written_so_far >= max_occurrences_total.

    Call this at the start of every phase before writing any nodes.
    If the budget is already exhausted, the caller should finalize the run
    with error_code=budget_exceeded and exit cleanly.

    Bypass: set PALACE_BUDGET_OVERRIDE=1 to skip this check.
    """
    if _budget_override_active():
        return
    if nodes_written_so_far >= max_occurrences_total:
        raise ExtractorError(
            error_code=ExtractorErrorCode.BUDGET_EXCEEDED,
            message=(
                f"Global budget exhausted before phase={phase}: "
                f"{nodes_written_so_far} >= {max_occurrences_total} max occurrences. "
                "Finalize run and exit. Raise PALACE_MAX_OCCURRENCES_TOTAL, "
                "or set PALACE_BUDGET_OVERRIDE=1 to bypass once."
            ),
            recoverable=False,
            action="raise_budget",
            phase=phase,
            partial_writes=nodes_written_so_far,
            context={
                "nodes_written_so_far": nodes_written_so_far,
                "max_occurrences_total": max_occurrences_total,
            },
        )


def check_resume_budget(
    *,
    previous_error_code: str | None,
) -> None:
    """Raise BUDGET_EXCEEDED_RESUME_BLOCKED if previous run ended with budget_exceeded.

    Call this at the very start of a resumed run (after reading IngestRun from Neo4j).
    Forces the operator to explicitly raise the budget cap before retrying.

    Bypass: set PALACE_BUDGET_OVERRIDE=1 to skip this check.
    """
    if _budget_override_active():
        return
    if previous_error_code == ExtractorErrorCode.BUDGET_EXCEEDED:
        raise ExtractorError(
            error_code=ExtractorErrorCode.BUDGET_EXCEEDED_RESUME_BLOCKED,
            message=(
                "Previous run ended with budget_exceeded. "
                "Raise PALACE_MAX_OCCURRENCES_TOTAL before resuming, "
                "or set PALACE_BUDGET_OVERRIDE=1 to bypass once."
            ),
            recoverable=False,
            action="raise_budget",
            context={"previous_error_code": previous_error_code},
        )
