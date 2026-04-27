"""Unit tests for 3-round eviction (GIM-101a, T7) — mocked Neo4j driver."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.eviction import _round1, _round2, _round3, run_eviction


def _make_summary(nodes_deleted: int = 0) -> MagicMock:
    summary = MagicMock()
    summary.counters.nodes_deleted = nodes_deleted
    return summary


def _make_driver(
    *,
    r1_deleted: int = 0,
    r2_deleted: int = 0,
    total_count: int = 0,
    r3_deleted: int = 0,
    fail_round: int | None = None,
) -> MagicMock:
    call_index = {"n": 0}

    async def run_side_effect(query: str, **kwargs: object) -> AsyncMock:
        call_index["n"] += 1
        result = AsyncMock()

        if fail_round is not None:
            # Determine which round this call belongs to by query content
            if "importance_threshold" in kwargs and fail_round == 1:
                raise RuntimeError("r1 failure")
            if "per_symbol_cap" in kwargs and fail_round == 2:
                raise RuntimeError("r2 failure")
            if "count(n)" in query and fail_round == 3:
                raise RuntimeError("r3 failure")

        if "count(n)" in query:
            result.data = AsyncMock(return_value=[{"total": total_count}])
        elif "importance_threshold" in kwargs:
            result.consume = AsyncMock(return_value=_make_summary(r1_deleted))
        elif "per_symbol_cap" in kwargs:
            result.consume = AsyncMock(return_value=_make_summary(r2_deleted))
        else:
            result.consume = AsyncMock(return_value=_make_summary(r3_deleted))

        return result

    session = AsyncMock()
    session.run = AsyncMock(side_effect=run_side_effect)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


class TestRound1:
    @pytest.mark.asyncio
    async def test_returns_deleted_count(self) -> None:
        driver = _make_driver(r1_deleted=42)
        count = await _round1(
            driver, group_id="project/test", importance_threshold=0.05, batch_size=1000
        )
        assert count == 42

    @pytest.mark.asyncio
    async def test_propagates_error_as_extractor_error(self) -> None:
        driver = _make_driver(fail_round=1)
        with pytest.raises(ExtractorError) as exc_info:
            await _round1(
                driver, group_id="project/test", importance_threshold=0.05, batch_size=1000
            )
        assert exc_info.value.error_code == ExtractorErrorCode.EVICTION_ROUND_1_FAILED
        assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_uses_importance_threshold_param(self) -> None:
        driver = _make_driver()
        await _round1(driver, group_id="project/test", importance_threshold=0.15, batch_size=500)
        call_kwargs = driver.session.return_value.run.call_args
        assert "importance_threshold" in str(call_kwargs)


class TestRound2:
    @pytest.mark.asyncio
    async def test_returns_deleted_count(self) -> None:
        driver = _make_driver(r2_deleted=7)
        count = await _round2(driver, group_id="project/test", per_symbol_cap=5000)
        assert count == 7

    @pytest.mark.asyncio
    async def test_propagates_error_as_extractor_error(self) -> None:
        driver = _make_driver(fail_round=2)
        with pytest.raises(ExtractorError) as exc_info:
            await _round2(driver, group_id="project/test", per_symbol_cap=5000)
        assert exc_info.value.error_code == ExtractorErrorCode.EVICTION_ROUND_2_FAILED


class TestRound3:
    @pytest.mark.asyncio
    async def test_no_eviction_when_under_cap(self) -> None:
        driver = _make_driver(total_count=100)
        count = await _round3(driver, group_id="project/test", global_cap=200)
        assert count == 0

    @pytest.mark.asyncio
    async def test_evicts_when_over_cap(self) -> None:
        driver = _make_driver(total_count=1000, r3_deleted=500)
        count = await _round3(driver, group_id="project/test", global_cap=500)
        assert count == 500

    @pytest.mark.asyncio
    async def test_propagates_error_as_extractor_error(self) -> None:
        driver = _make_driver(fail_round=3)
        with pytest.raises(ExtractorError) as exc_info:
            await _round3(driver, group_id="project/test", global_cap=1000)
        assert exc_info.value.error_code == ExtractorErrorCode.EVICTION_ROUND_3_FAILED


class TestRunEviction:
    @pytest.mark.asyncio
    async def test_returns_triple(self) -> None:
        driver = _make_driver(r1_deleted=10, r2_deleted=5, total_count=100, r3_deleted=0)
        r1, r2, r3 = await run_eviction(
            driver,
            group_id="project/test",
            importance_threshold=0.05,
            per_symbol_cap=5000,
            global_cap=1_000_000,
        )
        assert r1 == 10
        assert r2 == 5
        assert r3 == 0

    @pytest.mark.asyncio
    async def test_round1_failure_propagates(self) -> None:
        driver = _make_driver(fail_round=1)
        with pytest.raises(ExtractorError) as exc_info:
            await run_eviction(
                driver,
                group_id="project/test",
                importance_threshold=0.05,
                per_symbol_cap=5000,
                global_cap=1_000_000,
            )
        assert exc_info.value.error_code == ExtractorErrorCode.EVICTION_ROUND_1_FAILED
