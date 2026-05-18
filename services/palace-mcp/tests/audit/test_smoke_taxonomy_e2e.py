"""Task 2.8 — E2E regression: full status taxonomy pipeline in one run.

Verifies that the complete run_audit() pipeline correctly handles all five
status states and produces the right result dict / rendered report sections.

Patches:
- resolve_profile → returns a test profile (avoids Neo4j profile lookup)
- discover_extractor_statuses → returns pre-built ExtractorStatus dict (pure taxonomy)
The fetcher path is exercised live against a lightweight driver mock.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


from palace_mcp.audit.contracts import AuditContract
from palace_mcp.audit.discovery import ExtractorStatus
from palace_mcp.audit.run import run_audit
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.profiles import LanguageProfile


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

_PROFILE = LanguageProfile(
    "swift_kit",
    frozenset(
        {
            "ok_extractor",
            "failed_extractor",
            "not_attempted_extractor",
            "fetch_fail_extractor",
        }
    ),
    # not_applicable_extractor deliberately NOT in profile
)


class _Auditable(BaseExtractor):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._name

    @property
    def description(self) -> str:  # type: ignore[override]
        return f"Fake {self._name}"

    @property
    def constraints(self) -> list[str]:  # type: ignore[override]
        return []

    @property
    def indexes(self) -> list[str]:  # type: ignore[override]
        return []

    async def run(
        self, *, graphiti: object, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        return ExtractorStats()

    def audit_contract(self) -> AuditContract:
        from palace_mcp.audit.contracts import AuditContract

        return AuditContract(
            extractor_name=self._name,
            template_name=None,
            query="RETURN 1",
            severity_column="_severity",
        )


class _NonAuditable(BaseExtractor):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._name

    @property
    def description(self) -> str:  # type: ignore[override]
        return f"Non-auditable {self._name}"

    @property
    def constraints(self) -> list[str]:  # type: ignore[override]
        return []

    @property
    def indexes(self) -> list[str]:  # type: ignore[override]
        return []

    async def run(
        self, *, graphiti: object, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        return ExtractorStats()

    def audit_contract(self) -> None:
        return None


_REGISTRY: dict[str, Any] = {
    "ok_extractor": _Auditable("ok_extractor"),
    "failed_extractor": _Auditable("failed_extractor"),
    "not_attempted_extractor": _Auditable("not_attempted_extractor"),
    "fetch_fail_extractor": _Auditable("fetch_fail_extractor"),
    "not_applicable_extractor": _Auditable(
        "not_applicable_extractor"
    ),  # NOT in profile
    "non_auditable": _NonAuditable("non_auditable"),
}

# Pre-built status dict returned by patched discover_extractor_statuses
_STATUSES: dict[str, ExtractorStatus] = {
    "ok_extractor": ExtractorStatus("ok_extractor", "OK", last_run_id="r-ok"),
    "failed_extractor": ExtractorStatus(
        "failed_extractor",
        "RUN_FAILED",
        last_run_id="r-fail",
        error_code="extractor_runtime_error",
        error_message="timeout after 30s",
    ),
    "not_attempted_extractor": ExtractorStatus(
        "not_attempted_extractor", "NOT_ATTEMPTED"
    ),
    "fetch_fail_extractor": ExtractorStatus(
        "fetch_fail_extractor", "OK", last_run_id="r-ff"
    ),
    "not_applicable_extractor": ExtractorStatus(
        "not_applicable_extractor", "NOT_APPLICABLE"
    ),
}


def _make_fetch_driver() -> Any:
    """Driver that:
    - Succeeds on the first fetch call (ok_extractor → empty findings)
    - Raises RuntimeError on the second fetch call (fetch_fail_extractor → FETCH_FAILED)
    """
    call_count = 0

    async def _run_side_effect(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # ok_extractor audit query — return empty findings
            class _EmptyResult:
                def __aiter__(self) -> "_EmptyResult":
                    return self

                async def __anext__(self) -> None:
                    raise StopAsyncIteration

            return _EmptyResult()
        # fetch_fail_extractor audit query — simulate Cypher error
        raise RuntimeError("simulated neo4j timeout")

    session = AsyncMock()
    session.run = _run_side_effect
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_taxonomy_status_counts_correct() -> None:
    """status_counts: OK=1, RUN_FAILED=1, NOT_ATTEMPTED=1, FETCH_FAILED=1, NOT_APPLICABLE=1."""
    with (
        patch(
            "palace_mcp.audit.run.resolve_profile", new=AsyncMock(return_value=_PROFILE)
        ),
        patch(
            "palace_mcp.audit.run.discover_extractor_statuses",
            new=AsyncMock(return_value=_STATUSES),
        ),
    ):
        result = await run_audit(_make_fetch_driver(), _REGISTRY, project="tron-kit")

    counts = result["status_counts"]
    assert counts.get("OK", 0) == 1, f"OK: {counts}"
    assert counts.get("RUN_FAILED", 0) == 1, f"RUN_FAILED: {counts}"
    assert counts.get("NOT_ATTEMPTED", 0) == 1, f"NOT_ATTEMPTED: {counts}"
    assert counts.get("NOT_APPLICABLE", 0) == 1, f"NOT_APPLICABLE: {counts}"
    assert counts.get("FETCH_FAILED", 0) == 1, f"FETCH_FAILED: {counts}"


async def test_taxonomy_run_failed_in_report() -> None:
    """RUN_FAILED extractor surfaces in §Failed Extractors section."""
    with (
        patch(
            "palace_mcp.audit.run.resolve_profile", new=AsyncMock(return_value=_PROFILE)
        ),
        patch(
            "palace_mcp.audit.run.discover_extractor_statuses",
            new=AsyncMock(return_value=_STATUSES),
        ),
    ):
        result = await run_audit(_make_fetch_driver(), _REGISTRY, project="tron-kit")

    report = result["report_markdown"]
    assert "Failed Extractors" in report or "failed_extractor" in report.lower()


async def test_taxonomy_blind_spots_only_not_attempted_and_fetch_failed() -> None:
    """blind_spots contains NOT_ATTEMPTED and FETCH_FAILED; NOT_APPLICABLE excluded."""
    with (
        patch(
            "palace_mcp.audit.run.resolve_profile", new=AsyncMock(return_value=_PROFILE)
        ),
        patch(
            "palace_mcp.audit.run.discover_extractor_statuses",
            new=AsyncMock(return_value=_STATUSES),
        ),
    ):
        result = await run_audit(_make_fetch_driver(), _REGISTRY, project="tron-kit")

    blind = result["blind_spots"]
    assert "not_attempted_extractor" in blind
    assert "fetch_fail_extractor" in blind
    assert "not_applicable_extractor" not in blind
    assert "non_auditable" not in blind


async def test_taxonomy_profile_coverage_in_report() -> None:
    """Profile Coverage appendix present with NOT_APPLICABLE and NOT_ATTEMPTED rows."""
    with (
        patch(
            "palace_mcp.audit.run.resolve_profile", new=AsyncMock(return_value=_PROFILE)
        ),
        patch(
            "palace_mcp.audit.run.discover_extractor_statuses",
            new=AsyncMock(return_value=_STATUSES),
        ),
    ):
        result = await run_audit(_make_fetch_driver(), _REGISTRY, project="tron-kit")

    report = result["report_markdown"]
    assert "Profile Coverage" in report
    assert "NOT_APPLICABLE" in report
    assert "NOT_ATTEMPTED" in report
