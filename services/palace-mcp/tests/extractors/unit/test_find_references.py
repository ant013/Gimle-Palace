"""Tests for palace.code.find_references 3-state distinction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.code_composite import (
    FindReferencesRequest,
    _query_any_ingest_run_for_project,
    _query_eviction_record,
    _query_ingest_run_for_project,
)


def _make_driver_with_result(result_dict: dict | None) -> MagicMock:
    inner_session = AsyncMock()
    result_mock = AsyncMock()
    result_mock.single = AsyncMock(return_value=result_dict)
    inner_session.run = AsyncMock(return_value=result_mock)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=inner_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session.return_value = session_cm
    return driver


class TestFindReferencesRequest:
    def test_valid_request(self) -> None:
        req = FindReferencesRequest(qualified_name="foo.bar.baz")
        assert req.qualified_name == "foo.bar.baz"
        assert req.max_results == 100

    def test_empty_qn_rejected(self) -> None:
        with pytest.raises(Exception):
            FindReferencesRequest(qualified_name="")

    def test_max_results_default(self) -> None:
        req = FindReferencesRequest(qualified_name="x.y")
        assert req.max_results == 100

    def test_project_optional(self) -> None:
        req = FindReferencesRequest(qualified_name="x.y", project="gimle")
        assert req.project == "gimle"


class TestQueryIngestRun:
    @pytest.mark.asyncio
    async def test_no_ingest_run_returns_none(self) -> None:
        driver = _make_driver_with_result(None)
        result = await _query_ingest_run_for_project(
            driver, "test", "symbol_index_python"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_run_returns_dict(self) -> None:
        record = {"run_id": "r1", "success": True, "error_code": None}
        driver = _make_driver_with_result(record)
        result = await _query_ingest_run_for_project(
            driver, "test", "symbol_index_python"
        )
        assert result is not None
        assert result["success"] is True


class TestQueryAnyIngestRun:
    """Tests for _query_any_ingest_run_for_project (AC#3, AC#5)."""

    @pytest.mark.asyncio
    async def test_no_ingest_run_returns_none(self) -> None:
        driver = _make_driver_with_result(None)
        result = await _query_any_ingest_run_for_project(driver, "test")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "extractor_name",
        [
            "symbol_index_python",
            "symbol_index_typescript",
            "symbol_index_java",
            "symbol_index_solidity",
        ],
    )
    async def test_any_extractor_returns_ingest_run(self, extractor_name: str) -> None:
        record = {
            "run_id": f"r-{extractor_name}",
            "success": True,
            "extractor_name": extractor_name,
        }
        driver = _make_driver_with_result(record)
        result = await _query_any_ingest_run_for_project(driver, "test-project")
        assert result is not None
        assert result["success"] is True
        assert result["extractor_name"] == extractor_name

    @pytest.mark.asyncio
    async def test_backwards_compat_missing_extractor_name_property(self) -> None:
        # AC#5: old IngestRun records may lack extractor_name — still pass gate
        record = {"run_id": "r-old", "success": True, "extractor_name": None}
        driver = _make_driver_with_result(record)
        result = await _query_any_ingest_run_for_project(driver, "legacy-project")
        assert result is not None
        assert result["success"] is True


class TestQueryEvictionRecord:
    @pytest.mark.asyncio
    async def test_no_eviction_returns_none(self) -> None:
        driver = _make_driver_with_result(None)
        result = await _query_eviction_record(driver, "foo.bar", "test")
        assert result is None

    @pytest.mark.asyncio
    async def test_eviction_record_returns_dict(self) -> None:
        record = {"eviction_round": 1, "evicted_at": "2026-01-01", "run_id": "r1"}
        driver = _make_driver_with_result(record)
        result = await _query_eviction_record(driver, "foo.bar", "test")
        assert result is not None
        assert result["eviction_round"] == 1
