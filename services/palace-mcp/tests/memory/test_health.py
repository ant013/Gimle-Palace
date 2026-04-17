"""Unit tests for palace_mcp.memory.health.get_health using AsyncMock."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.memory.health import get_health
from palace_mcp.memory.schema import HealthResponse


class _AsyncRows:
    """Minimal async iterable over a list of row dicts."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._iter = iter(rows)

    def __aiter__(self) -> "_AsyncRows":
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _make_mock_driver(
    counts_rows: list[dict[str, Any]],
    ingest_row: dict[str, Any] | None,
) -> MagicMock:
    """Build a minimal AsyncDriver mock for health queries."""

    async def _read_fn(fn: Any, *args: Any, **kwargs: Any) -> Any:
        call_count = 0

        async def _run(query: str, **params: Any) -> Any:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # ENTITY_COUNTS — return async-iterable rows
                return _AsyncRows(counts_rows)
            else:
                # LATEST_INGEST_RUN — return result with .single()
                result = MagicMock()
                if ingest_row is not None:
                    single_val = MagicMock()
                    # single_val["r"] must be dict-like
                    single_val.__getitem__ = lambda _self, key: ingest_row if key == "r" else None
                    result.single = AsyncMock(return_value=single_val)
                else:
                    result.single = AsyncMock(return_value=None)
                return result

        tx = MagicMock()
        tx.run = _run
        return await fn(tx)

    session = MagicMock()
    session.execute_read = AsyncMock(side_effect=_read_fn)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.verify_connectivity = AsyncMock(return_value=None)
    driver.session.return_value = session
    return driver


@pytest.mark.asyncio
async def test_get_health_neo4j_unreachable_returns_false() -> None:
    driver = MagicMock()
    driver.verify_connectivity = AsyncMock(side_effect=Exception("conn refused"))
    result = await get_health(driver)
    assert result.neo4j_reachable is False
    assert result.entity_counts == {}


@pytest.mark.asyncio
async def test_get_health_returns_entity_counts() -> None:
    counts = [
        {"type": "Issue", "count": 42},
        {"type": "Comment", "count": 10},
        {"type": "Agent", "count": 3},
    ]
    driver = _make_mock_driver(counts_rows=counts, ingest_row=None)
    result: HealthResponse = await get_health(driver)
    assert result.neo4j_reachable is True
    assert result.entity_counts == {"Issue": 42, "Comment": 10, "Agent": 3}
    assert result.last_ingest_started_at is None
