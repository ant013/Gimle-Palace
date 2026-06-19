"""Unit tests for palace.code.find_idiom MCP tool."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mcp_and_register() -> Any:
    from mcp.server.fastmcp import FastMCP

    from palace_mcp.code_idiom import register_code_idiom_tools

    mcp = FastMCP("test")
    register_code_idiom_tools(
        lambda name, desc: mcp.tool(name=name, description=desc),
        default_project="repos-gimle",
    )
    return mcp


async def _call(mcp: Any, **kwargs: Any) -> dict[str, Any]:
    result = await mcp.call_tool("palace.code.find_idiom", kwargs)
    return json.loads(result[0][0].text)  # type: ignore[index]


def _mock_driver_with_data(
    conv_records: list[dict[str, Any]],
    viol_records: list[dict[str, Any]],
    total_violations: int,
) -> AsyncMock:
    """Build an AsyncMock Neo4j driver that returns canned query results."""
    driver = AsyncMock()
    session = AsyncMock()

    conv_result = AsyncMock()
    conv_result.data = AsyncMock(return_value=conv_records)

    count_result = AsyncMock()
    count_result.single = AsyncMock(return_value={"total": total_violations})

    viol_result = AsyncMock()
    viol_result.data = AsyncMock(return_value=viol_records)

    # session.run returns in order: conventions, count, violations
    session.run = AsyncMock(side_effect=[conv_result, count_result, viol_result])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver.session = MagicMock(return_value=session)
    return driver


_CONV_ROW = {
    "module": "GimleApp",
    "kind": "idiom.collection_init",
    "dominant": "Array(repeating:count:)",
    "confidence": "high",
    "sample_count": 42,
    "outliers": 3,
    "source_context": "Swift collection initialisation",
}

_VIOL_ROW = {
    "module": "GimleApp",
    "kind": "idiom.collection_init",
    "file": "Sources/GimleApp/Foo.swift",
    "start_line": 10,
    "end_line": 10,
    "message": "Used [T](repeating:) instead of Array(repeating:count:)",
    "severity": "warning",
}


# ---------------------------------------------------------------------------
# Test 1: Happy path — conventions and outlier samples returned
# ---------------------------------------------------------------------------


class TestFindIdiomHappyPath:
    @pytest.mark.asyncio
    async def test_full_response(self) -> None:
        driver = _mock_driver_with_data(
            conv_records=[_CONV_ROW],
            viol_records=[_VIOL_ROW],
            total_violations=1,
        )

        with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, kind="idiom.collection_init")

        assert payload["ok"] is True
        assert payload["kind"] == "idiom.collection_init"
        assert payload["project"] == "gimle"
        assert len(payload["conventions"]) == 1
        conv = payload["conventions"][0]
        assert conv["module"] == "GimleApp"
        assert conv["dominant"] == "Array(repeating:count:)"
        assert conv["confidence"] == "high"
        assert conv["sample_count"] == 42
        assert conv["outliers"] == 3
        assert len(payload["outlier_samples"]) == 1
        samp = payload["outlier_samples"][0]
        assert samp["file"] == "Sources/GimleApp/Foo.swift"
        assert samp["start_line"] == 10
        assert samp["severity"] == "warning"
        assert payload["total_outlier_samples"] == 1
        assert payload["truncated"] is False


# ---------------------------------------------------------------------------
# Test 2: No conventions found → ok=False, error_code=no_conventions_found
# ---------------------------------------------------------------------------


class TestFindIdiomNoConventions:
    @pytest.mark.asyncio
    async def test_no_conventions(self) -> None:
        driver = AsyncMock()
        session = AsyncMock()

        conv_result = AsyncMock()
        conv_result.data = AsyncMock(return_value=[])
        session.run = AsyncMock(return_value=conv_result)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        driver.session = MagicMock(return_value=session)

        with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, kind="idiom.nonexistent")

        assert payload["ok"] is False
        assert payload["error_code"] == "no_conventions_found"
        assert payload["kind"] == "idiom.nonexistent"
        assert "project" in payload


# ---------------------------------------------------------------------------
# Test 3: Driver not initialised → ToolError raised
# ---------------------------------------------------------------------------


class TestFindIdiomDriverNone:
    @pytest.mark.asyncio
    async def test_driver_not_initialised(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with patch("palace_mcp.mcp_server.get_driver", return_value=None):
            mcp = _make_mcp_and_register()
            with pytest.raises(ToolError):
                await mcp.call_tool(
                    "palace.code.find_idiom", {"kind": "idiom.collection_init"}
                )


# ---------------------------------------------------------------------------
# Test 4: Validation error — empty kind
# ---------------------------------------------------------------------------


class TestFindIdiomValidation:
    @pytest.mark.asyncio
    async def test_empty_kind_returns_validation_error(self) -> None:
        driver = AsyncMock()

        with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, kind="")

        assert payload["ok"] is False
        assert payload["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_max_outliers_out_of_range(self) -> None:
        driver = AsyncMock()

        with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, kind="idiom.foo", max_outliers=0)

        assert payload["ok"] is False
        assert payload["error_code"] == "validation_error"


# ---------------------------------------------------------------------------
# Test 5: Module filter — only matching module conventions returned
# ---------------------------------------------------------------------------


class TestFindIdiomModuleFilter:
    @pytest.mark.asyncio
    async def test_module_filter_passed_through(self) -> None:
        driver = _mock_driver_with_data(
            conv_records=[_CONV_ROW],
            viol_records=[],
            total_violations=0,
        )

        with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, kind="idiom.collection_init", module="GimleApp")

        assert payload["ok"] is True
        # Verify module param was passed (driver.session.run was called with module="GimleApp")
        session = driver.session.return_value.__aenter__.return_value
        first_call_kwargs = session.run.call_args_list[0]
        assert first_call_kwargs.kwargs.get("module") == "GimleApp"

    @pytest.mark.asyncio
    async def test_truncated_when_total_exceeds_max(self) -> None:
        driver = _mock_driver_with_data(
            conv_records=[_CONV_ROW],
            viol_records=[_VIOL_ROW] * 5,
            total_violations=50,
        )

        with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, kind="idiom.collection_init", max_outliers=5)

        assert payload["ok"] is True
        assert payload["total_outlier_samples"] == 50
        assert payload["truncated"] is True
        assert len(payload["outlier_samples"]) == 5


# ---------------------------------------------------------------------------
# Test 6: project_id key — must match what coding_convention writes (bare slug)
# ---------------------------------------------------------------------------


class TestFindIdiomProjectIdKey:
    """Regression (dogfood W-skill rec #19): the coding_convention extractor
    writes :Convention nodes with project_id = bare slug (ctx.project_slug);
    its own audit_contract query matches the same bare-slug key. find_idiom
    previously prefixed 'project/', so it silently matched zero nodes even
    after the extractor wrote 1229 of them. Every query must use the bare slug.
    """

    @pytest.mark.asyncio
    async def test_queries_bare_slug_project_id(self) -> None:
        driver = _mock_driver_with_data(
            conv_records=[_CONV_ROW],
            viol_records=[],
            total_violations=0,
        )

        with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, kind="naming", project="uw-ios-app")

        assert payload["ok"] is True
        assert payload["project"] == "uw-ios-app"
        session = driver.session.return_value.__aenter__.return_value
        assert session.run.call_args_list, "expected at least one Cypher call"
        for call in session.run.call_args_list:
            assert call.kwargs.get("project_id") == "uw-ios-app", (
                "find_idiom must query bare-slug project_id "
                "(coding_convention writes ctx.project_slug), not 'project/'-prefixed"
            )
