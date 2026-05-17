"""Unit tests for audit/discovery.py — typed ExtractorStatus (GIM-283-1 Task 2.2).

RED tests: verify discover_extractor_statuses classifies correctly and
respects last-attempt-wins (CR C2 fix).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.audit.contracts import AuditContract
from palace_mcp.extractors.base import BaseExtractor, ExtractorStats
from palace_mcp.extractors.foundation.profiles import LanguageProfile


# ---------------------------------------------------------------------------
# Minimal fake extractors
# ---------------------------------------------------------------------------


def _make_extractor(name: str, has_contract: bool = True) -> BaseExtractor:
    class _Ext(BaseExtractor):
        _name = name
        description = "test"

        async def run(self, **_: Any) -> ExtractorStats:
            return ExtractorStats()

        def audit_contract(self) -> AuditContract | None:
            if not has_contract:
                return None
            return AuditContract(
                extractor_name=self._name,
                template_name=f"{self._name}.md",
                query="RETURN 1",
                severity_column="sev",
            )

    ext = _Ext.__new__(_Ext)
    ext._name = name
    return ext


# ---------------------------------------------------------------------------
# Driver helpers
# ---------------------------------------------------------------------------

_T1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_T2 = _T1 + timedelta(hours=1)  # T2 > T1


def _make_driver_with_rows(rows: list[dict[str, Any]]) -> Any:
    """Return a mock driver whose session.run returns the given rows."""

    class _AsyncIter:
        def __init__(self, data: list[dict[str, Any]]) -> None:
            self._iter = iter(data)

        def __aiter__(self) -> "_AsyncIter":
            return self

        async def __anext__(self) -> dict[str, Any]:
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    session = AsyncMock()
    session.run = AsyncMock(return_value=_AsyncIter(rows))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


def _row(
    extractor_name: str,
    *,
    run_id: str = "run-1",
    success: bool = True,
    started_at: datetime = _T1,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "extractor_name": extractor_name,
        "run_id": run_id,
        "started_at": started_at,
        "success": success,
        "error_code": error_code,
        "error_message": error_message,
    }


# ---------------------------------------------------------------------------
# Tests: discover_extractor_statuses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discovery_classifies_each_status() -> None:
    """Five extractors each map to a distinct status type."""
    from palace_mcp.audit.discovery import discover_extractor_statuses

    # Profile includes: ok_ext, run_failed_ext, not_attempted_ext
    # Not in profile: not_applicable_ext
    # FETCH_FAILED is set by run.py after discovery → skip here, tested in run tests
    profile = LanguageProfile(
        "swift_kit",
        frozenset({"ok_ext", "run_failed_ext", "not_attempted_ext"}),
    )
    registry = {
        "ok_ext": _make_extractor("ok_ext"),
        "run_failed_ext": _make_extractor("run_failed_ext"),
        "not_attempted_ext": _make_extractor("not_attempted_ext"),
        "not_applicable_ext": _make_extractor("not_applicable_ext"),
        "no_contract_ext": _make_extractor("no_contract_ext", has_contract=False),
    }
    driver = _make_driver_with_rows(
        [
            _row("ok_ext", run_id="r1", success=True),
            _row("run_failed_ext", run_id="r2", success=False, error_code="some_err"),
            # not_attempted_ext — no row in driver
        ]
    )

    statuses = await discover_extractor_statuses(
        driver, project="tron-kit", profile=profile, registry=registry
    )

    assert statuses["ok_ext"].status == "OK"
    assert statuses["ok_ext"].last_run_id == "r1"

    assert statuses["run_failed_ext"].status == "RUN_FAILED"
    assert statuses["run_failed_ext"].error_code == "some_err"

    assert statuses["not_attempted_ext"].status == "NOT_ATTEMPTED"
    assert statuses["not_attempted_ext"].last_run_id is None

    assert statuses["not_applicable_ext"].status == "NOT_APPLICABLE"

    # no_contract_ext has no audit_contract() → not in output
    assert "no_contract_ext" not in statuses


@pytest.mark.asyncio
async def test_latest_failed_overrides_earlier_success() -> None:
    """Last-attempt-wins: second run (failed, T2>T1) overrides first (success, T1).

    CR C2 fix — the Cypher must NOT filter on success=true; it must ORDER BY
    started_at DESC and take the latest row regardless of success flag.
    """
    from palace_mcp.audit.discovery import discover_extractor_statuses

    profile = LanguageProfile("swift_kit", frozenset({"multi_run_ext"}))
    registry = {"multi_run_ext": _make_extractor("multi_run_ext")}

    # Two rows for same extractor; T2 is later and has success=False
    # discover_extractor_statuses must pick T2 (the last attempt)
    driver = _make_driver_with_rows(
        [
            _row("multi_run_ext", run_id="r2", success=False, started_at=_T2),
        ]
    )

    statuses = await discover_extractor_statuses(
        driver, project="tron-kit", profile=profile, registry=registry
    )

    assert statuses["multi_run_ext"].status == "RUN_FAILED", (
        "Expected RUN_FAILED because the latest run (T2) failed, "
        "even though an earlier run (T1) succeeded"
    )


@pytest.mark.asyncio
async def test_empty_registry_returns_empty() -> None:
    """No audit extractors → empty status dict."""
    from palace_mcp.audit.discovery import discover_extractor_statuses

    profile = LanguageProfile("swift_kit", frozenset())
    registry: dict[str, Any] = {}
    driver = _make_driver_with_rows([])

    statuses = await discover_extractor_statuses(
        driver, project="gimle", profile=profile, registry=registry
    )
    assert statuses == {}


@pytest.mark.asyncio
async def test_all_not_attempted_when_no_runs() -> None:
    """In-profile extractors with no :IngestRun rows → NOT_ATTEMPTED."""
    from palace_mcp.audit.discovery import discover_extractor_statuses

    profile = LanguageProfile("swift_kit", frozenset({"ext_a", "ext_b"}))
    registry = {"ext_a": _make_extractor("ext_a"), "ext_b": _make_extractor("ext_b")}
    driver = _make_driver_with_rows([])  # no rows

    statuses = await discover_extractor_statuses(
        driver, project="tron-kit", profile=profile, registry=registry
    )

    assert statuses["ext_a"].status == "NOT_ATTEMPTED"
    assert statuses["ext_b"].status == "NOT_ATTEMPTED"


@pytest.mark.asyncio
async def test_ok_status_carries_run_id() -> None:
    """OK status preserves last_run_id for provenance."""
    from palace_mcp.audit.discovery import discover_extractor_statuses

    profile = LanguageProfile("swift_kit", frozenset({"hotspot"}))
    registry = {"hotspot": _make_extractor("hotspot")}
    driver = _make_driver_with_rows([_row("hotspot", run_id="hs-run-42", success=True)])

    statuses = await discover_extractor_statuses(
        driver, project="tron-kit", profile=profile, registry=registry
    )
    assert statuses["hotspot"].status == "OK"
    assert statuses["hotspot"].last_run_id == "hs-run-42"
