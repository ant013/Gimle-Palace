from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.code.edges import CALL_EDGES, KNOWN_NON_CALL_EDGES
from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.code.native_trace_call_path import (
    _path_query,
    native_trace_call_path,
)


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


def test_trace_call_path_tool_has_native_handler() -> None:
    from palace_mcp.code_router import _PASSTHROUGH_TOOLS

    assert _PASSTHROUGH_TOOLS["trace_call_path"].native_handler is not None


@pytest.mark.asyncio
async def test_trace_call_path_falls_back_without_project() -> None:
    result = await native_trace_call_path(function_name="register_code_tools")

    assert result is FALLBACK_TO_CM


@pytest.mark.asyncio
async def test_trace_call_path_outbound_returns_stable_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "hop": 1,
                "path_nodes": [
                    {
                        "qualified_name": "pkg.root",
                        "name": "root",
                        "file_path": "src/root.py",
                        "kind": "function",
                        "is_test": False,
                    },
                    {
                        "qualified_name": "pkg.child",
                        "name": "child",
                        "file_path": "src/child.py",
                        "kind": "function",
                        "is_test": False,
                    },
                ],
                "path_edges": [
                    {
                        "source": "pkg.root",
                        "target": "pkg.child",
                        "type": "CALLS",
                    }
                ],
            },
            {
                "hop": 2,
                "path_nodes": [
                    {
                        "qualified_name": "pkg.root",
                        "name": "root",
                        "file_path": "src/root.py",
                        "kind": "function",
                        "is_test": False,
                    },
                    {
                        "qualified_name": "pkg.child",
                        "name": "child",
                        "file_path": "src/child.py",
                        "kind": "function",
                        "is_test": False,
                    },
                    {
                        "qualified_name": "pkg.leaf",
                        "name": "leaf",
                        "file_path": "src/leaf.py",
                        "kind": "function",
                        "is_test": False,
                    },
                ],
                "path_edges": [
                    {
                        "source": "pkg.root",
                        "target": "pkg.child",
                        "type": "CALLS",
                    },
                    {
                        "source": "pkg.child",
                        "target": "pkg.leaf",
                        "type": "CALLS",
                    },
                ],
            },
        ]
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_trace_call_path(
        project="gimle",
        function_name="root",
        direction="outbound",
        depth=2,
    )

    assert result == {
        "function": "root",
        "project": "gimle",
        "direction": "outbound",
        "mode": "calls",
        "nodes": [
            {
                "qualified_name": "pkg.child",
                "name": "child",
                "file_path": "src/child.py",
                "kind": "function",
            },
            {
                "qualified_name": "pkg.leaf",
                "name": "leaf",
                "file_path": "src/leaf.py",
                "kind": "function",
            },
            {
                "qualified_name": "pkg.root",
                "name": "root",
                "file_path": "src/root.py",
                "kind": "function",
            },
        ],
        "edges": [
            {"source": "pkg.child", "target": "pkg.leaf", "type": "CALLS"},
            {"source": "pkg.root", "target": "pkg.child", "type": "CALLS"},
        ],
        "callees": [
            {
                "qualified_name": "pkg.child",
                "name": "child",
                "file_path": "src/child.py",
                "kind": "function",
                "hop": 1,
            },
            {
                "qualified_name": "pkg.leaf",
                "name": "leaf",
                "file_path": "src/leaf.py",
                "kind": "function",
                "hop": 2,
            },
        ],
    }


@pytest.mark.asyncio
async def test_trace_call_path_both_direction_collects_callers_and_callees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "hop": 1,
                "path_nodes": [
                    {
                        "qualified_name": "pkg.root",
                        "name": "root",
                        "file_path": "src/root.py",
                        "kind": "function",
                        "is_test": False,
                    },
                    {
                        "qualified_name": "tests.test_root",
                        "name": "test_root",
                        "file_path": "tests/test_root.py",
                        "kind": "function",
                        "is_test": False,
                    },
                ],
                "path_edges": [
                    {
                        "source": "tests.test_root",
                        "target": "pkg.root",
                        "type": "CALLS",
                    }
                ],
            }
        ],
        [
            {
                "hop": 1,
                "path_nodes": [
                    {
                        "qualified_name": "pkg.root",
                        "name": "root",
                        "file_path": "src/root.py",
                        "kind": "function",
                        "is_test": False,
                    },
                    {
                        "qualified_name": "pkg.child",
                        "name": "child",
                        "file_path": "src/child.py",
                        "kind": "function",
                        "is_test": False,
                    },
                ],
                "path_edges": [
                    {
                        "source": "pkg.root",
                        "target": "pkg.child",
                        "type": "CALLS",
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_trace_call_path(
        project="gimle",
        function_name="root",
        direction="both",
        depth=3,
        include_tests=True,
    )

    assert result["callers"] == [
        {
            "qualified_name": "tests.test_root",
            "name": "test_root",
            "file_path": "tests/test_root.py",
            "kind": "function",
            "is_test": True,
            "hop": 1,
        }
    ]
    assert result["callees"] == [
        {
            "qualified_name": "pkg.child",
            "name": "child",
            "file_path": "src/child.py",
            "kind": "function",
            "hop": 1,
        }
    ]


@pytest.mark.asyncio
async def test_trace_call_path_excludes_test_paths_from_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "hop": 1,
                "path_nodes": [
                    {
                        "qualified_name": "pkg.root",
                        "name": "root",
                        "file_path": "src/root.py",
                        "kind": "function",
                        "is_test": False,
                    },
                    {
                        "qualified_name": "tests.test_root",
                        "name": "test_root",
                        "file_path": "tests/test_root.py",
                        "kind": "function",
                        "is_test": False,
                    },
                ],
                "path_edges": [
                    {
                        "source": "tests.test_root",
                        "target": "pkg.root",
                        "type": "CALLS",
                    }
                ],
            }
        ],
        [
            {
                "hop": 1,
                "path_nodes": [
                    {
                        "qualified_name": "pkg.root",
                        "name": "root",
                        "file_path": "src/root.py",
                        "kind": "function",
                        "is_test": False,
                    },
                    {
                        "qualified_name": "pkg.child",
                        "name": "child",
                        "file_path": "src/child.py",
                        "kind": "function",
                        "is_test": False,
                    },
                ],
                "path_edges": [
                    {
                        "source": "pkg.root",
                        "target": "pkg.child",
                        "type": "CALLS",
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_trace_call_path(
        project="gimle",
        function_name="root",
        direction="both",
        depth=3,
    )

    assert result["callers"] == []
    assert result["nodes"] == [
        {
            "qualified_name": "pkg.child",
            "name": "child",
            "file_path": "src/child.py",
            "kind": "function",
        },
        {
            "qualified_name": "pkg.root",
            "name": "root",
            "file_path": "src/root.py",
            "kind": "function",
        },
    ]
    assert result["edges"] == [
        {"source": "pkg.root", "target": "pkg.child", "type": "CALLS"}
    ]
    assert result["callees"] == [
        {
            "qualified_name": "pkg.child",
            "name": "child",
            "file_path": "src/child.py",
            "kind": "function",
            "hop": 1,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("depth", "expected_fragment", "expected_clamped_depth"),
    [(0, "*1..1", 1), (7, "*1..6", 6)],
)
async def test_trace_call_path_clamps_depth_in_query_and_response(
    monkeypatch: pytest.MonkeyPatch,
    depth: int,
    expected_fragment: str,
    expected_clamped_depth: int,
) -> None:
    driver = _mock_driver([])
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_trace_call_path(
        project="gimle",
        function_name="root",
        direction="outbound",
        depth=depth,
    )

    session = driver.session.return_value
    query = session.run.await_args.args[0]
    assert expected_fragment in query
    assert result["clamped_depth"] == expected_clamped_depth


@pytest.mark.asyncio
async def test_trace_call_path_redacts_cypher_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        error=RuntimeError("boom /Users/anton/secret db.labels() schema")
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_trace_call_path(
        project="gimle",
        function_name="root",
        direction="outbound",
    )

    assert result["error_code"] == "cypher_error"
    assert "/Users/anton" not in result["message"]
    assert "db.labels()" not in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["data_flow", "cross_service"])
async def test_trace_call_path_non_calls_modes_return_phase2_required(
    mode: str,
) -> None:
    result = await native_trace_call_path(
        project="gimle",
        function_name="root",
        mode=mode,
    )

    assert result == {
        "ok": False,
        "error_code": "phase2_required",
        "message": (
            f"native palace.code.trace_call_path does not support mode={mode!r} "
            "in this slice"
        ),
        "project": "gimle",
        "mode": mode,
    }


def test_path_query_uses_only_call_edges() -> None:
    query = _path_query("outbound", 3)

    for edge_type in CALL_EDGES:
        assert edge_type in query
    for edge_type in KNOWN_NON_CALL_EDGES:
        assert edge_type not in query


@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_path_query_scopes_every_node_in_the_path(direction: str) -> None:
    query = _path_query(direction, 3)

    assert "root.group_id = $group_id" in query
    assert "target.group_id = $group_id" in query
    assert "all(node IN nodes(path) WHERE node.group_id = $group_id)" in query
