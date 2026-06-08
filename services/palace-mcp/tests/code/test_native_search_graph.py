from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.code.native_search_graph import native_search_graph


class _RowsResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = list(rows)

    async def data(self) -> list[dict[str, object]]:
        return list(self._rows)


def _mock_driver(
    *row_sets: list[dict[str, object]], error: Exception | None = None
) -> object:
    session = AsyncMock()
    if error is not None:
        session.run = AsyncMock(side_effect=error)
    else:
        session.run = AsyncMock(side_effect=[_RowsResult(rows) for rows in row_sets])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def test_search_graph_tool_has_native_handler() -> None:
    from palace_mcp.code_router import _PASSTHROUGH_TOOLS

    assert _PASSTHROUGH_TOOLS["search_graph"].native_handler is not None


@pytest.mark.asyncio
async def test_search_graph_falls_back_without_project() -> None:
    result = await native_search_graph(name_pattern="register_code_tools")

    assert result is FALLBACK_TO_CM


@pytest.mark.asyncio
async def test_search_graph_query_mode_returns_phase2_required() -> None:
    result = await native_search_graph(project="gimle", query="register code tools")

    assert result["error_code"] == "phase2_required"
    assert result["project"] == "gimle"


@pytest.mark.asyncio
async def test_search_graph_pattern_mode_returns_results_and_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [{"total": 2}],
        [
            {
                "name": "register_code_tools",
                "qualified_name": "pkg.code_router.register_code_tools",
                "label": "Function",
                "file_path": "src/palace_mcp/code_router.py",
            },
            {
                "name": "register_code_tools_test",
                "qualified_name": "pkg.tests.register_code_tools_test",
                "label": "Function",
                "file_path": "tests/test_code_router.py",
            },
        ],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(
        project="gimle",
        label="function",
        name_pattern="register_.*",
        qn_pattern="pkg\\..*",
        file_pattern=".*code_router.*|.*test_code_router.*",
        min_degree=1,
        max_degree=4,
        limit=1,
    )

    assert result == {
        "results": [
            {
                "name": "register_code_tools",
                "qualified_name": "pkg.code_router.register_code_tools",
                "label": "Function",
                "file_path": "src/palace_mcp/code_router.py",
            }
        ],
        "total": 2,
        "has_more": True,
    }

    session = driver.session.return_value
    count_call = session.run.await_args_list[0]
    assert "RETURN count(*) AS total" in count_call.args[0]
    assert count_call.kwargs["group_id"] == "project/gimle"
    assert count_call.kwargs["project_id"] == "project/gimle"
    assert count_call.kwargs["label"] == "Function"
    assert count_call.kwargs["min_degree"] == 1
    assert count_call.kwargs["max_degree"] == 4

    result_call = session.run.await_args_list[1]
    assert "ORDER BY qualified_name ASC" in result_call.args[0]
    assert "LIMIT $fetch_limit" in result_call.args[0]
    assert result_call.kwargs["fetch_limit"] == 2
    assert result_call.kwargs["offset"] == 0


@pytest.mark.asyncio
async def test_search_graph_rejects_invalid_regex_before_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver()
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(project="gimle", name_pattern="(")

    assert result["error_code"] == "validation_error"
    driver.session.assert_not_called()
