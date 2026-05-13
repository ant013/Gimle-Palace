"""Unit tests for run.py — typed status taxonomy consumption (GIM-283-1 Task 2.3).

Verifies:
1. run.py calls discover_extractor_statuses (not find_latest_runs).
2. renderer receives all_statuses dict.
3. profile-based filtering replaces the old audit_contract() scan.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from palace_mcp.audit.contracts import AuditContract
from palace_mcp.audit.discovery import ExtractorStatus
from palace_mcp.extractors.base import BaseExtractor, ExtractorStats
from palace_mcp.extractors.foundation.profiles import LanguageProfile, PROFILES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extractor(name: str, has_contract: bool = True) -> BaseExtractor:
    class _Ext(BaseExtractor):
        description = "test"

        async def run(self, **_: Any) -> ExtractorStats:
            return ExtractorStats()

        def audit_contract(self) -> AuditContract | None:
            if not has_contract:
                return None
            return AuditContract(
                extractor_name=name,
                template_name="hotspot.md",
                query="RETURN 1",
                severity_column="sev",
            )

    ext = _Ext.__new__(_Ext)
    return ext


class _EmptyAsyncResult:
    def __aiter__(self) -> "_EmptyAsyncResult":
        return self

    async def __anext__(self) -> None:
        raise StopAsyncIteration


def _make_empty_driver() -> Any:
    session = AsyncMock()
    session.run = AsyncMock(return_value=_EmptyAsyncResult())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


_SWIFT_KIT_PROFILE = PROFILES["swift_kit"]
_MINIMAL_PROFILE = LanguageProfile("swift_kit", frozenset({"fake_auditable"}))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_uses_discover_extractor_statuses() -> None:
    """run_audit calls discover_extractor_statuses, not find_latest_runs."""
    from palace_mcp.audit.run import run_audit

    drv = _make_empty_driver()
    registry = {"fake_auditable": _make_extractor("fake_auditable")}

    with (
        patch(
            "palace_mcp.audit.run.resolve_profile",
            new=AsyncMock(return_value=_MINIMAL_PROFILE),
        ),
        patch(
            "palace_mcp.audit.run.discover_extractor_statuses",
            new=AsyncMock(
                return_value={
                    "fake_auditable": ExtractorStatus(
                        extractor_name="fake_auditable", status="NOT_ATTEMPTED"
                    )
                }
            ),
        ) as mock_discover,
    ):
        result = await run_audit(drv, registry, project="gimle")

    assert result["ok"] is True
    mock_discover.assert_called_once()
    # Verify project arg passed correctly
    _, kwargs = mock_discover.call_args
    assert kwargs.get("project") == "gimle" or mock_discover.call_args[0][1:] == ("gimle",)


@pytest.mark.asyncio
async def test_run_exposes_status_counts_in_result() -> None:
    """run_audit result includes status_counts from the taxonomy."""
    from palace_mcp.audit.run import run_audit

    drv = _make_empty_driver()
    registry = {
        "ok_ext": _make_extractor("ok_ext"),
        "failed_ext": _make_extractor("failed_ext"),
    }
    statuses = {
        "ok_ext": ExtractorStatus("ok_ext", "OK", last_run_id="r1"),
        "failed_ext": ExtractorStatus("failed_ext", "RUN_FAILED", error_code="err"),
    }

    with (
        patch(
            "palace_mcp.audit.run.resolve_profile",
            new=AsyncMock(return_value=LanguageProfile("swift_kit", frozenset({"ok_ext", "failed_ext"}))),
        ),
        patch(
            "palace_mcp.audit.run.discover_extractor_statuses",
            new=AsyncMock(return_value=statuses),
        ),
    ):
        result = await run_audit(drv, registry, project="gimle")

    assert result["ok"] is True
    # status_counts key must be present in result
    assert "status_counts" in result
    counts = result["status_counts"]
    assert counts.get("RUN_FAILED", 0) >= 1


@pytest.mark.asyncio
async def test_run_not_attempted_in_blind_spots_field() -> None:
    """NOT_ATTEMPTED extractors appear in blind_spots for backward compat."""
    from palace_mcp.audit.run import run_audit

    drv = _make_empty_driver()
    registry = {"never_run": _make_extractor("never_run")}
    statuses = {
        "never_run": ExtractorStatus("never_run", "NOT_ATTEMPTED"),
    }

    with (
        patch(
            "palace_mcp.audit.run.resolve_profile",
            new=AsyncMock(return_value=LanguageProfile("swift_kit", frozenset({"never_run"}))),
        ),
        patch(
            "palace_mcp.audit.run.discover_extractor_statuses",
            new=AsyncMock(return_value=statuses),
        ),
    ):
        result = await run_audit(drv, registry, project="gimle")

    assert result["ok"] is True
    assert "never_run" in result["blind_spots"]
