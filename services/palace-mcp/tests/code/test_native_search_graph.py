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
                "short_name": "register_code_tools",
                "kind": "function",
            },
            {
                "name": "register_code_tools_test",
                "qualified_name": "pkg.tests.register_code_tools_test",
                "label": "Function",
                "file_path": "tests/test_code_router.py",
                "short_name": "register_code_tools_test",
                "kind": "function",
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
                "short_name": "register_code_tools",
                "kind": "function",
            }
        ],
        "total": 2,
        "returned": 1,
        "offset": 0,
        "has_more": True,
        "next_offset": 1,
        "truncated": True,
        "truncated_reason": "page_limit",
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


@pytest.mark.asyncio
async def test_search_graph_returns_canonical_struct_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [{"total": 1}],
        [
            {
                "name": "BalanceData",
                "qualified_name": "WalletKit s:9WalletKit11BalanceDataV",
                "label": "Struct",
                "file_path": "Sources/BalanceData.swift",
                "short_name": "BalanceData",
                "kind": "struct",
            }
        ],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(
        project="gimle",
        label="Struct",
        name_pattern="^BalanceData$",
    )

    assert result["results"][0]["short_name"] == "BalanceData"
    assert result["results"][0]["kind"] == "struct"
    assert result["results"][0]["label"] == "Struct"


@pytest.mark.asyncio
async def test_search_graph_plain_name_lookup_prefers_kind_over_generic_symbol_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [{"total": 1}],
        [
            {
                "name": "Passkey",
                "qualified_name": "WalletKit s:9WalletKit7PasskeyV",
                "label": "Struct",
                "file_path": "Sources/Passkey.swift",
                "short_name": "Passkey",
                "kind": "struct",
            }
        ],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(
        project="gimle",
        name_pattern="Passkey",
    )

    assert result["results"][0]["name"] == "Passkey"
    assert result["results"][0]["label"] == "Struct"

    count_call = driver.session.return_value.run.await_args_list[0]
    assert "ELSE coalesce(n.label, 'Symbol')" in count_call.args[0]
    assert (
        "coalesce(n.label, CASE toLower(coalesce(n.kind, ''))" not in count_call.args[0]
    )


@pytest.mark.asyncio
async def test_search_graph_symbol_label_matches_any_symbol_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [{"total": 1}],
        [
            {
                "name": "BalanceData",
                "qualified_name": "WalletKit s:9WalletKit11BalanceDataV",
                "label": "Struct",
                "file_path": "Sources/BalanceData.swift",
                "short_name": "BalanceData",
                "kind": "struct",
            }
        ],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(
        project="gimle",
        label="Symbol",
        name_pattern="^BalanceData$",
    )

    assert result["results"][0]["label"] == "Struct"

    count_call = driver.session.return_value.run.await_args_list[0]
    assert count_call.kwargs["label"] == "Symbol"
    assert "result_is_symbol" in count_call.args[0]
    assert "$label = 'Symbol' AND result_is_symbol" in count_call.args[0]


@pytest.mark.asyncio
async def test_search_graph_unknown_name_returns_zero_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [{"total": 0}],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(
        project="gimle",
        name_pattern="DefinitelyMissingSymbol",
    )

    assert result == {
        "results": [],
        "total": 0,
        "returned": 0,
        "offset": 0,
        "has_more": False,
        "truncated": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("total", "limit", "expected_returned", "expected_truncated"),
    [
        (0, 1, 0, False),
        (1, 1, 1, False),
        (2, 1, 1, True),
    ],
)
async def test_search_graph_pagination_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    total: int,
    limit: int,
    expected_returned: int,
    expected_truncated: bool,
) -> None:
    rows = [
        {
            "name": f"Symbol{i}",
            "qualified_name": f"pkg.Symbol{i}",
            "label": "Function",
            "file_path": f"src/Symbol{i}.py",
            "short_name": f"Symbol{i}",
            "kind": "function",
        }
        for i in range(total)
    ]
    driver = _mock_driver([{"total": total}], rows)
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(
        project="gimle",
        name_pattern="Symbol.*",
        limit=limit,
    )

    assert result["total"] == total
    assert result["returned"] == expected_returned
    assert len(result["results"]) == expected_returned
    assert result["truncated"] is expected_truncated


@pytest.mark.asyncio
async def test_search_graph_coerces_string_int_limit_and_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The open-schema passthrough delivers integer args as strings ("3"); the
    handler must coerce them instead of rejecting with 'must be an integer'."""
    driver = _mock_driver(
        [{"total": 1}],
        [
            {
                "name": "Foo",
                "qualified_name": "pkg.Foo",
                "label": "Class",
                "file_path": "src/foo.py",
                "short_name": "Foo",
                "kind": "class",
            }
        ],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(
        project="gimle",
        name_pattern="Foo",
        limit="3",
        offset="0",
    )

    assert result["returned"] == 1
    assert result["results"][0]["name"] == "Foo"


@pytest.mark.asyncio
async def test_search_graph_rejects_non_numeric_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver([{"total": 0}], [])
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_search_graph(
        project="gimle",
        name_pattern="Foo",
        limit="abc",
    )

    assert result["ok"] is False
    assert result["error_code"] == "validation_error"
    assert "limit must be an integer" in result["message"]
