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

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode


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
    """
    if nodes_written_so_far >= max_occurrences_total:
        raise ExtractorError(
            error_code=ExtractorErrorCode.BUDGET_EXCEEDED,
            message=(
                f"Global budget exhausted before phase={phase}: "
                f"{nodes_written_so_far} >= {max_occurrences_total} max occurrences. "
                "Finalize run and exit. Set PALACE_MAX_OCCURRENCES_TOTAL higher to continue."
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
    """
    if previous_error_code == ExtractorErrorCode.BUDGET_EXCEEDED:
        raise ExtractorError(
            error_code=ExtractorErrorCode.BUDGET_EXCEEDED_RESUME_BLOCKED,
            message=(
                "Previous run ended with budget_exceeded. "
                "Raise PALACE_MAX_OCCURRENCES_TOTAL before resuming, "
                "or set PALACE_FORCE_REINGEST=1 to start fresh."
            ),
            recoverable=False,
            action="raise_budget",
            context={"previous_error_code": previous_error_code},
        )
