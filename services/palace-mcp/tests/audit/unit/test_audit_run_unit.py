"""Unit tests for palace.audit.run (S1.8).

Uses in-process FastMCP test client pattern (W5: CI-compatible, no live stack).
Tests via mcp.call_tool() with a fake driver and registry.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock


from palace_mcp.audit.contracts import AuditContract
from palace_mcp.extractors.base import BaseExtractor, ExtractorStats


# ---------------------------------------------------------------------------
# Minimal fake extractor with a known AuditContract
# ---------------------------------------------------------------------------

class FakeAuditExtractor(BaseExtractor):
    name = "fake_auditable"
    description = "test only"

    def __init__(self, *, has_contract: bool = True) -> None:
        self._has_contract = has_contract

    async def run(self, *, graphiti: Any, ctx: Any) -> ExtractorStats:
        return ExtractorStats()

    def audit_contract(self) -> AuditContract | None:
        if not self._has_contract:
            return None
        return AuditContract(
            extractor_name="fake_auditable",
            template_name="hotspot.md",
            query="MATCH (n) RETURN n LIMIT 0",
            severity_column="sev",
        )


# ---------------------------------------------------------------------------
# Helpers: build a fake driver + fake discovery
# ---------------------------------------------------------------------------


class _EmptyAsyncResult:
    """Async-iterable result that yields no rows."""

    def __aiter__(self) -> "_EmptyAsyncResult":
        return self

    async def __anext__(self) -> None:
        raise StopAsyncIteration


def _make_empty_driver() -> Any:
    """Driver that returns no rows for any query."""
    session = AsyncMock()
    session.run = AsyncMock(return_value=_EmptyAsyncResult())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


def _register_and_call_run() -> Any:
    from mcp.server.fastmcp import FastMCP
    from palace_mcp.audit.run import run_audit

    mcp = FastMCP("test-audit")

    @mcp.tool(name="palace.audit.run", description="Run audit report")
    async def palace_audit_run(
        project: str | None = None,
        bundle: str | None = None,
        depth: str = "full",
    ) -> dict[str, Any]:
        drv = _make_empty_driver()
        registry: dict[str, BaseExtractor] = {
            "fake_auditable": FakeAuditExtractor(has_contract=True),
        }
        return await run_audit(drv, registry, project=project, bundle=bundle, depth=depth)

    return mcp


class TestPalaceAuditRunMCPTool:
    async def test_tool_listed_in_registry(self) -> None:
        mcp = _register_and_call_run()
        tools = await mcp.list_tools()
        names = [t.name for t in tools]
        assert "palace.audit.run" in names

    async def test_valid_project_returns_ok(self) -> None:
        mcp = _register_and_call_run()
        result = await mcp.call_tool("palace.audit.run", {"project": "gimle"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert "report_markdown" in payload
        assert "fetched_extractors" in payload
        assert "blind_spots" in payload
        assert "provenance" in payload

    async def test_project_xor_bundle_required(self) -> None:
        mcp = _register_and_call_run()
        result = await mcp.call_tool("palace.audit.run", {})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False
        assert "invalid_args" in payload["error_code"]

    async def test_both_project_and_bundle_errors(self) -> None:
        mcp = _register_and_call_run()
        result = await mcp.call_tool("palace.audit.run", {"project": "a", "bundle": "b"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False

    async def test_invalid_slug_errors(self) -> None:
        mcp = _register_and_call_run()
        result = await mcp.call_tool("palace.audit.run", {"project": "INVALID SLUG!"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False
        assert "invalid_slug" in payload["error_code"]

    async def test_invalid_depth_errors(self) -> None:
        mcp = _register_and_call_run()
        result = await mcp.call_tool("palace.audit.run", {"project": "gimle", "depth": "ultra"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False
        assert "invalid_depth" in payload["error_code"]

    async def test_blind_spots_includes_unrun_extractors(self) -> None:
        mcp = _register_and_call_run()
        result = await mcp.call_tool("palace.audit.run", {"project": "gimle"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        # fake_auditable has a contract but no IngestRun → in blind_spots
        assert "fake_auditable" in payload["blind_spots"]

    async def test_empty_graph_returns_all_blind_spots_and_report(self) -> None:
        mcp = _register_and_call_run()
        result = await mcp.call_tool("palace.audit.run", {"project": "test-project"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert "# Audit Report" in payload["report_markdown"]
        assert payload["fetched_extractors"] == []
