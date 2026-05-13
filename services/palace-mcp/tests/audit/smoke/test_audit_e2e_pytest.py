"""S1.10 — E2E smoke harness pytest wrapper + paved-path regression test.

Two test classes:

1. TestAuditSmokeBash (W4 wrapper):
   - Runs test_audit_e2e.sh when palace-mcp is reachable; skips otherwise.
   - Marked @pytest.mark.integration so CI can gate it separately.

2. TestPavedPathRegression (in-process, always runs in CI):
   - Verifies that adding a new extractor with audit_contract() to the
     registry causes a new section to appear in the report WITHOUT any
     orchestrator code changes.
   - Uses the same in-process FastMCP + _EmptyAsyncResult pattern as S1.8.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.audit.contracts import AuditContract
from palace_mcp.audit.run import run_audit
from palace_mcp.extractors.base import BaseExtractor, ExtractorStats

_SMOKE_SCRIPT = Path(__file__).parent / "test_audit_e2e.sh"


# ---------------------------------------------------------------------------
# Shared helpers (same as S1.8 unit tests)
# ---------------------------------------------------------------------------


class _EmptyAsyncResult:
    def __aiter__(self) -> "_EmptyAsyncResult":
        return self

    async def __anext__(self) -> None:
        raise StopAsyncIteration

    async def single(self) -> None:
        return None


class _RowAsyncResult:
    """Async-iterable result that yields a fixed list of row dicts."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = list(rows)
        self._iter = iter(self._rows)

    def __aiter__(self) -> "_RowAsyncResult":
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


def _make_empty_driver() -> Any:
    session = AsyncMock()
    session.run = AsyncMock(return_value=_EmptyAsyncResult())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


def _make_data_driver(extractor_name: str) -> Any:
    """Driver that returns one IngestRun row for discovery, then one finding row for fetch.

    Ordered by call sequence: first session.run call = discovery, second = fetch.
    Both calls share the same session object (the mock reuses the same session instance).
    """
    discovery_row = {
        "extractor_name": extractor_name,
        "run_id": "run-test-001",
        "completed_at": None,
        "success": True,
        "error_code": None,
        "error_message": None,
    }
    # Hotspot-shaped row so hotspot.md template renders without error
    finding_row = {
        "path": "src/foo.py",
        "ccn_total": 25,
        "churn_count": 10,
        "hotspot_score": 5.5,
        "window_days": 90,
    }
    call_results = [
        _EmptyAsyncResult(),  # resolve_profile: returns None → ValueError → fallback profile
        _RowAsyncResult([discovery_row]),  # discover_extractor_statuses: success run
        _RowAsyncResult([finding_row]),  # fetch_audit_data: findings
    ]
    session = AsyncMock()
    session.run = AsyncMock(side_effect=call_results)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


# ---------------------------------------------------------------------------
# Minimal fake extractors for paved-path test
# ---------------------------------------------------------------------------


class _FakeExtractor(BaseExtractor):
    def __init__(self, name: str, *, has_contract: bool = True) -> None:
        self._name = name
        self._has_contract = has_contract

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._name

    description = "test"

    async def run(self, *, graphiti: Any, ctx: Any) -> ExtractorStats:
        return ExtractorStats()

    def audit_contract(self) -> AuditContract | None:
        if not self._has_contract:
            return None
        return AuditContract(
            extractor_name=self._name,
            # Use extractor name as template filename so unknown names trigger the
            # TemplateNotFound fallback path in render_report, exercising Finding 1 fix.
            template_name=f"{self._name}.md",
            query="MATCH (n) RETURN n LIMIT 0",
            severity_column="hotspot_score",
        )


# ---------------------------------------------------------------------------
# Bash smoke wrapper (W4 — requires live palace-mcp)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAuditSmokeBash:
    """Runs test_audit_e2e.sh when palace-mcp is reachable; skips if not."""

    def test_e2e_bash_smoke(self) -> None:
        mcp_url = os.environ.get("PALACE_MCP_URL", "http://localhost:8000/mcp")
        try:
            import urllib.request

            urllib.request.urlopen(mcp_url.replace("/mcp", "/healthz"), timeout=2)
        except Exception:
            pytest.skip(f"palace-mcp not reachable at {mcp_url}; skipping bash smoke")

        result = subprocess.run(
            ["bash", str(_SMOKE_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 2:
            pytest.skip(f"palace-mcp not reachable (exit 2): {result.stderr[:200]}")

        assert result.returncode == 0, (
            f"test_audit_e2e.sh failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Paved-path regression — in-process, no Docker (always runs in CI)
# ---------------------------------------------------------------------------


class TestPavedPathRegression:
    """Verifies that adding an extractor to the registry auto-adds its section.

    The invariant: palace.audit.run is driven purely by extractor_registry
    contents. No orchestrator code changes are needed to add a new section.
    """

    async def test_one_extractor_one_section(self) -> None:
        """Registry with 1 auditable extractor → report has 1 fetched extractor."""
        registry: dict[str, BaseExtractor] = {
            "extractor_a": _FakeExtractor("extractor_a"),
        }
        result = await run_audit(
            _make_empty_driver(),
            registry,
            project="paved-path-test",
        )
        assert result["ok"] is True
        # With empty graph, no data is fetched, so fetched_extractors is empty
        # but blind_spots has the extractor
        assert "extractor_a" in result["blind_spots"]

    async def test_two_extractors_two_blind_spots(self) -> None:
        """Registry with 2 auditable extractors → both in blind_spots if no IngestRun."""
        registry: dict[str, BaseExtractor] = {
            "extractor_a": _FakeExtractor("extractor_a"),
            "extractor_b": _FakeExtractor("extractor_b"),
        }
        result = await run_audit(
            _make_empty_driver(),
            registry,
            project="paved-path-test",
        )
        assert result["ok"] is True
        assert "extractor_a" in result["blind_spots"]
        assert "extractor_b" in result["blind_spots"]

    async def test_third_extractor_appears_without_code_change(self) -> None:
        """Core paved-path invariant: adding extractor_c to registry adds a blind spot.

        No changes to run_audit(), renderer.py, fetcher.py, or discovery.py needed.
        The new section (or blind spot) appears automatically.
        """
        registry_v1: dict[str, BaseExtractor] = {
            "extractor_a": _FakeExtractor("extractor_a"),
            "extractor_b": _FakeExtractor("extractor_b"),
        }
        result_v1 = await run_audit(
            _make_empty_driver(),
            registry_v1,
            project="paved-path-test",
        )
        assert len(result_v1["blind_spots"]) == 2

        # Add extractor_c — simulates adding a new extractor plugin
        registry_v2: dict[str, BaseExtractor] = {
            **registry_v1,
            "extractor_c": _FakeExtractor("extractor_c"),
        }
        result_v2 = await run_audit(
            _make_empty_driver(),
            registry_v2,
            project="paved-path-test",
        )
        assert result_v2["ok"] is True
        assert len(result_v2["blind_spots"]) == 3
        assert "extractor_c" in result_v2["blind_spots"]

    async def test_no_contract_extractor_not_in_blind_spots(self) -> None:
        """Extractor without audit_contract() is excluded from blind_spots."""
        registry: dict[str, BaseExtractor] = {
            "auditable": _FakeExtractor("auditable", has_contract=True),
            "no_contract": _FakeExtractor("no_contract", has_contract=False),
        }
        result = await run_audit(
            _make_empty_driver(),
            registry,
            project="paved-path-test",
        )
        assert result["ok"] is True
        assert "auditable" in result["blind_spots"]
        assert "no_contract" not in result["blind_spots"]

    async def test_report_markdown_contains_report_header(self) -> None:
        """Any audit run produces a markdown report with the standard header."""
        registry: dict[str, BaseExtractor] = {
            "extractor_a": _FakeExtractor("extractor_a"),
        }
        result = await run_audit(
            _make_empty_driver(),
            registry,
            project="paved-path-test",
        )
        assert result["ok"] is True
        assert "# Audit Report" in result["report_markdown"]
        assert "paved-path-test" in result["report_markdown"]

    async def test_new_extractor_with_data_uses_fallback_section(self) -> None:
        """Core rendering invariant (Finding 1): extractor not in _SECTION_ORDER renders.

        A new extractor with no matching template gets a fallback section rather than
        being silently dropped.  Data-backed driver so discovery + fetch both succeed.
        """
        registry: dict[str, BaseExtractor] = {
            "brand_new_extractor": _FakeExtractor("brand_new_extractor"),
        }
        result = await run_audit(
            _make_data_driver("brand_new_extractor"),
            registry,
            project="paved-path-test",
        )
        assert result["ok"] is True
        # The extractor had data → in fetched_extractors, not blind_spots
        assert "brand_new_extractor" in result["fetched_extractors"]
        assert "brand_new_extractor" not in result["blind_spots"]
        # Fallback section (TemplateNotFound path) must appear in report
        assert (
            "brand_new_extractor" in result["report_markdown"].lower()
            or "brand new extractor" in result["report_markdown"].lower()
        )

    async def test_known_extractor_with_data_renders_full_section(self) -> None:
        """Known extractor with data renders its full template section.

        Uses the real HotspotExtractor so _build_summary_stats produces
        hotspot-compatible stats and the hotspot.md template renders correctly.
        """
        from palace_mcp.extractors.hotspot.extractor import HotspotExtractor

        registry: dict[str, BaseExtractor] = {
            "hotspot": HotspotExtractor(),
        }
        result = await run_audit(
            _make_data_driver("hotspot"),
            registry,
            project="paved-path-test",
        )
        assert result["ok"] is True
        assert "hotspot" in result["fetched_extractors"]
        # Full hotspot.md section must include the finding path
        assert "src/foo.py" in result["report_markdown"]

    async def test_severity_mapper_produces_non_informational_severity(self) -> None:
        """Finding 2 fix: extractor with severity_mapper classifies domain values correctly.

        hotspot_score=5.5 → CRITICAL via HotspotExtractor.severity_mapper.
        The executive summary must warn about critical/high findings.
        """
        from palace_mcp.extractors.hotspot.extractor import HotspotExtractor

        registry: dict[str, BaseExtractor] = {
            "hotspot": HotspotExtractor(),
        }
        result = await run_audit(
            _make_data_driver("hotspot"),
            registry,
            project="paved-path-test",
        )
        assert result["ok"] is True
        assert "hotspot" in result["fetched_extractors"]
        # hotspot_score=5.5 → CRITICAL → executive summary warns
        assert (
            "critical/high" in result["report_markdown"].lower()
            or "critical" in result["report_markdown"].lower()
        )
