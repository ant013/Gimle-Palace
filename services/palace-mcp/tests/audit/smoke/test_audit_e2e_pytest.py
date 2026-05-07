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


def _make_empty_driver() -> Any:
    session = AsyncMock()
    session.run = AsyncMock(return_value=_EmptyAsyncResult())
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
            template_name="hotspot.md",
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
