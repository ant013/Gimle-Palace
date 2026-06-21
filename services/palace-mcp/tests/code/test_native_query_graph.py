from __future__ import annotations

from collections.abc import Iterable
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.code.native_query_graph import native_query_graph


class _AsyncRows:
    def __init__(self, rows: Iterable[dict[str, object]]) -> None:
        self._rows = list(rows)

    def __aiter__(self) -> _AsyncRows:
        self._iter = iter(self._rows)
        return self

    async def __anext__(self) -> dict[str, object]:
        try:
            return next(self._iter)
        except StopIteration as exc:  # pragma: no cover
            raise StopAsyncIteration from exc


def _mock_driver(
    rows: list[dict[str, object]] | None = None, *, error: Exception | None = None
) -> object:
    session = AsyncMock()
    if error is not None:
        session.run = AsyncMock(side_effect=error)
    else:
        session.run = AsyncMock(return_value=_AsyncRows(rows or []))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.mark.asyncio
async def test_query_graph_returns_columns_rows_and_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver([{"qualified_name": "A"}, {"qualified_name": "B"}])
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_query_graph(
        project="gimle",
        query=(
            "MATCH (s:Symbol) "
            "WHERE s.group_id = $group_id "
            "RETURN s.qualified_name AS qualified_name"
        ),
    )

    assert result == {
        "columns": ["qualified_name"],
        "rows": [["A"], ["B"]],
        "total": 2,
    }


@pytest.mark.asyncio
async def test_query_graph_rejects_reserved_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: _mock_driver())

    result = await native_query_graph(
        project="gimle",
        query="MATCH (s:Symbol) WHERE s.group_id = $group_id RETURN s",
        group_id="project/evil",
    )

    assert result["error_code"] == "reserved_param"


@pytest.mark.asyncio
async def test_query_graph_rejects_unscoped_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: _mock_driver())

    result = await native_query_graph(
        project="gimle",
        query="MATCH (s:Symbol) RETURN s.qualified_name AS qualified_name",
    )

    assert result["error_code"] == "scope_predicate_required"


@pytest.mark.asyncio
async def test_query_graph_rejects_partially_scoped_multi_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: _mock_driver())

    result = await native_query_graph(
        project="gimle",
        query=(
            "MATCH (s:Symbol) WHERE s.group_id = $group_id "
            "MATCH (f:File) RETURN count(f) AS total"
        ),
    )

    assert result["error_code"] == "scope_predicate_required"


@pytest.mark.asyncio
async def test_query_graph_allows_write_words_inside_string_literals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver([{"name": "CREATE"}])
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_query_graph(
        project="gimle",
        query=(
            "MATCH (s:Symbol) WHERE s.group_id = $group_id "
            'AND s.name = "CREATE" RETURN s.name AS name'
        ),
    )

    assert result["rows"] == [["CREATE"]]


@pytest.mark.asyncio
async def test_query_graph_allows_write_words_inside_comments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver([{"name": "A"}])
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_query_graph(
        project="gimle",
        query=(
            "MATCH (s:Symbol) WHERE s.group_id = $group_id // CREATE\n"
            "RETURN s.name AS name"
        ),
    )

    assert result["rows"] == [["A"]]


@pytest.mark.asyncio
async def test_query_graph_rejects_write_queries_before_driver_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver()
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_query_graph(
        project="gimle",
        query="CREATE (s:Symbol {group_id: $group_id}) RETURN s",
    )

    assert result["error_code"] == "write_query_forbidden"
    driver.session.assert_not_called()


@pytest.mark.asyncio
async def test_query_graph_redacts_cypher_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        error=RuntimeError("boom /Users/anton/secret db.labels() schema")
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_query_graph(
        project="gimle",
        query="MATCH (s:Symbol) WHERE s.group_id = $group_id RETURN s",
    )

    assert result["error_code"] == "cypher_error"
    assert "/Users/anton" not in result["message"]
    assert "db.labels()" not in result["message"]


@pytest.mark.asyncio
async def test_query_graph_marks_row_cap_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("palace_mcp.code.native_query_graph._MAX_ROWS", 1)
    monkeypatch.setattr(
        "palace_mcp.mcp_server.get_driver",
        lambda: _mock_driver([{"name": "A"}, {"name": "B"}]),
    )

    result = await native_query_graph(
        project="gimle",
        query="MATCH (s:Symbol) WHERE s.group_id = $group_id RETURN s.name AS name",
    )

    assert result["rows"] == [["A"]]
    assert result["total"] == 2
    assert result["truncated_reason"] == "row_cap"


@pytest.mark.asyncio
async def test_query_graph_marks_byte_budget_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("palace_mcp.code.native_query_graph._MAX_BYTES", 10)
    monkeypatch.setattr(
        "palace_mcp.mcp_server.get_driver",
        lambda: _mock_driver([{"name": "A"}, {"name": "BBBBBBBBBB"}]),
    )

    result = await native_query_graph(
        project="gimle",
        query="MATCH (s:Symbol) WHERE s.group_id = $group_id RETURN s.name AS name",
    )

    assert result["rows"] == [["A"]]
    assert result["total"] == 2
    assert result["truncated_reason"] == "byte_budget"
