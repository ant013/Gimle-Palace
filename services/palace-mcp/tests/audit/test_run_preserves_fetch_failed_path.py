"""Unit tests — run.py preserves fetcher out-parameter mechanism (GIM-283-1 Task 2.3).

Verifies that when a fetcher Cypher query raises, the extractor name is appended
to the failed_extractors out-list AND the typed status classification maps it to
FETCH_FAILED.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.audit.contracts import AuditContract
from palace_mcp.audit.discovery import ExtractorStatus
from palace_mcp.extractors.base import BaseExtractor, ExtractorStats
from palace_mcp.extractors.foundation.profiles import LanguageProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extractor(name: str) -> BaseExtractor:
    class _Ext(BaseExtractor):
        description = "test"

        async def run(self, **_: Any) -> ExtractorStats:
            return ExtractorStats()

        def audit_contract(self) -> AuditContract | None:
            return AuditContract(
                extractor_name=name,
                template_name="hotspot.md",
                query="MATCH (n) RETURN n LIMIT 1",
                severity_column="sev",
            )

    ext = _Ext.__new__(_Ext)
    return ext


def _make_failing_driver() -> Any:
    """Driver whose session.run always raises RuntimeError.

    resolve_profile and discover_extractor_statuses are patched in the test,
    so this driver is only called by the fetcher — which should receive the error.
    """

    class _FailingSession:
        async def __aenter__(self) -> "_FailingSession":
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def run(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Neo4j query failed")

    drv = MagicMock()
    drv.session = MagicMock(return_value=_FailingSession())
    return drv


@pytest.mark.asyncio
async def test_fetcher_out_parameter_still_populated() -> None:
    """Extractor that raises in fetcher → FETCH_FAILED in status_counts."""
    from palace_mcp.audit.run import run_audit

    registry = {"flaky_ext": _make_extractor("flaky_ext")}
    # discover says flaky_ext = OK (so fetcher will try to fetch it)
    ok_status = ExtractorStatus("flaky_ext", "OK", last_run_id="r1")

    with (
        patch(
            "palace_mcp.audit.run.resolve_profile",
            new=AsyncMock(
                return_value=LanguageProfile("swift_kit", frozenset({"flaky_ext"}))
            ),
        ),
        patch(
            "palace_mcp.audit.run.discover_extractor_statuses",
            new=AsyncMock(return_value={"flaky_ext": ok_status}),
        ),
    ):
        drv = _make_failing_driver()
        result = await run_audit(drv, registry, project="gimle")

    assert result["ok"] is True
    # FETCH_FAILED must be counted
    counts = result.get("status_counts", {})
    assert counts.get("FETCH_FAILED", 0) >= 1, (
        f"Expected FETCH_FAILED in status_counts; got: {counts}"
    )
    # flaky_ext should NOT appear in fetched_extractors
    assert "flaky_ext" not in result["fetched_extractors"]
