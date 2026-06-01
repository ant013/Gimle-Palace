"""Unit tests for palace.code.get_snippet_rich composite tool."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import CallToolResult, TextContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(data: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        isError=False,
    )


def _make_error_result(msg: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=msg)],
        isError=True,
    )


def _fake_session(*call_tool_responses: dict[str, Any] | CallToolResult) -> AsyncMock:
    session = AsyncMock()
    results = [
        r if isinstance(r, CallToolResult) else _make_result(r)
        for r in call_tool_responses
    ]
    session.call_tool = AsyncMock(side_effect=results)
    return session


_SEARCH_GRAPH_HIT = {
    "total": 1,
    "has_more": False,
    "results": [
        {
            "name": "my_fn",
            "qualified_name": "mod.sub.my_fn",
            "file_path": "src/mod/sub.py",
        }
    ],
}

_SNIPPET_RESPONSE = {
    "source": "def my_fn(): pass",
    "language": "python",
    "file_path": "src/mod/sub.py",
    "start_line": 10,
    "end_line": 11,
}

_OWNERS_RESPONSE = {
    "ok": True,
    "owners": [
        {"author_email": "alice@example.com", "author_name": "Alice", "weight": 0.8}
    ],
}

_COMMITS_RESPONSE = {
    "ok": True,
    "project": "gimle",
    "ref": "HEAD",
    "entries": [
        {
            "sha": "abc123def456",
            "short": "abc123d",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "date": "2026-05-20T09:00:00+00:00",
            "subject": "fix: do the thing",
        }
    ],
    "truncated": False,
}


def _make_mcp_and_register() -> Any:
    from mcp.server.fastmcp import FastMCP

    from palace_mcp.code_composite import register_code_composite_tools

    mcp = FastMCP("test")
    register_code_composite_tools(
        lambda name, desc: mcp.tool(name=name, description=desc),
        default_project="repos-gimle",
    )
    return mcp


async def _call(mcp: Any, **kwargs: Any) -> dict[str, Any]:
    result = await mcp.call_tool("palace.code.get_snippet_rich", kwargs)
    return json.loads(result[0][0].text)  # type: ignore[index]


# ---------------------------------------------------------------------------
# Test 1: Happy path — all sub-calls succeed
# ---------------------------------------------------------------------------


class TestGetSnippetRichHappyPath:
    @pytest.mark.asyncio
    async def test_full_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_session = _fake_session(_SEARCH_GRAPH_HIT, _SNIPPET_RESPONSE)
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        mock_bridge = AsyncMock()
        mock_bridge.search_by_symbol_id_async = AsyncMock(
            return_value=[
                {
                    "file_path": "src/mod/sub.py",
                    "line": 42,
                    "col_start": 4,
                    "col_end": 9,
                    "kind": "call",
                    "symbol_qualified_name": "mod.sub.my_fn",
                }
            ]
        )
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=False)

        mock_driver = AsyncMock()
        mock_neo4j_session = AsyncMock()
        mock_result = AsyncMock()
        mock_record = {"hotspot_score": 0.42}
        mock_result.single = AsyncMock(return_value=mock_record)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)
        mock_neo4j_session.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        mock_neo4j_session.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session = MagicMock(return_value=mock_neo4j_session)

        with (
            patch("palace_mcp.code_composite.TantivyBridge", return_value=mock_bridge),
            patch(
                "palace_mcp.code_composite.palace_code_get_snippet_rich.__wrapped__"
                if False
                else "palace_mcp.mcp_server.get_driver",
                return_value=mock_driver,
            ),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
            patch(
                "palace_mcp.code.find_owners.find_owners",
                new=AsyncMock(return_value=_OWNERS_RESPONSE),
            ),
            patch(
                "palace_mcp.git.tools.palace_git_log",
                new=AsyncMock(return_value=_COMMITS_RESPONSE),
            ),
        ):
            mcp = _make_mcp_and_register()
            # Patch get_driver inside the tool's deferred import path
            with patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver):
                payload = await _call(mcp, qualified_name="my_fn")

        assert payload["ok"] is True
        assert payload["qualified_name"] == "mod.sub.my_fn"
        assert payload["project"] == "gimle"
        assert payload["snippet"]["source"] == "def my_fn(): pass"
        assert payload["definition_location"]["file_path"] == "src/mod/sub.py"
        assert payload["definition_location"]["start_line"] == 10
        assert "conventions" not in payload

    @pytest.mark.asyncio
    async def test_short_name_fallback_normalizes_cm_project_for_neo4j(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_session = _fake_session(
            {"total": 0, "results": [], "has_more": False},
            {
                "source": "struct BalanceData {}",
                "language": "swift",
                "file_path": "Sources/App/BalanceData.swift",
                "start_line": 10,
                "end_line": 12,
            },
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        query_mock = AsyncMock(
            return_value=[
                {
                    "name": "BalanceData",
                    "short_name": "BalanceData",
                    "qualified_name": "WalletKit.BalanceData",
                    "file_path": "Sources/App/BalanceData.swift",
                    "symbol": "",
                }
            ]
        )
        monkeypatch.setattr("palace_mcp.code_composite._query_symbol_candidates", query_mock)

        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        mock_bridge = AsyncMock()
        mock_bridge.search_by_symbol_id_async = AsyncMock(return_value=[])
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=False)

        mock_driver = AsyncMock()
        mock_neo4j_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"hotspot_score": 0.42})
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)
        mock_neo4j_session.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        mock_neo4j_session.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session = MagicMock(return_value=mock_neo4j_session)

        with (
            patch("palace_mcp.code_composite.TantivyBridge", return_value=mock_bridge),
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
            patch(
                "palace_mcp.code.find_owners.find_owners",
                new=AsyncMock(return_value=_OWNERS_RESPONSE),
            ),
            patch(
                "palace_mcp.git.tools.palace_git_log",
                new=AsyncMock(return_value=_COMMITS_RESPONSE),
            ),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(
                mcp,
                qualified_name="BalanceData",
                project="uw-ios-app",
            )

        assert payload["ok"] is True
        assert payload["qualified_name"] == "WalletKit.BalanceData"
        assert payload["project"] == "uw-ios-app"
        assert query_mock.await_args_list[0].kwargs["group_id"] == "project/uw-ios-app"

    @pytest.mark.asyncio
    async def test_usages_are_deduped_by_file_and_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_session = _fake_session(_SEARCH_GRAPH_HIT, _SNIPPET_RESPONSE)
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        mock_bridge = AsyncMock()
        mock_bridge.search_by_symbol_id_async = AsyncMock(
            return_value=[
                {
                    "file_path": "src/mod/sub.py",
                    "line": 42,
                    "col_start": 4,
                    "col_end": 9,
                    "kind": "call",
                    "symbol_qualified_name": "mod.sub.my_fn",
                },
                {
                    "file_path": "src/mod/sub.py",
                    "line": 42,
                    "col_start": 12,
                    "col_end": 17,
                    "kind": "call",
                    "symbol_qualified_name": "mod.sub.my_fn",
                },
            ]
        )
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=False)

        mock_driver = AsyncMock()
        mock_neo4j_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"hotspot_score": 0.42})
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)
        mock_neo4j_session.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        mock_neo4j_session.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session = MagicMock(return_value=mock_neo4j_session)

        with (
            patch("palace_mcp.code_composite.TantivyBridge", return_value=mock_bridge),
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
            patch(
                "palace_mcp.code.find_owners.find_owners",
                new=AsyncMock(return_value=_OWNERS_RESPONSE),
            ),
            patch(
                "palace_mcp.git.tools.palace_git_log",
                new=AsyncMock(return_value=_COMMITS_RESPONSE),
            ),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, qualified_name="my_fn")

        assert len(payload["usages"]) == 1
        assert payload["usages"][0]["line"] == 42


# ---------------------------------------------------------------------------
# Test 2: Symbol not found
# ---------------------------------------------------------------------------


class TestGetSnippetRichSymbolNotFound:
    @pytest.mark.asyncio
    async def test_symbol_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_session = _fake_session(
            {"total": 0, "results": [], "has_more": False},
            {"rows": []},
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_driver = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, qualified_name="nonexistent_fn")

        assert payload["ok"] is False
        assert payload["error_code"] == "symbol_not_found"
        assert payload["requested_qualified_name"] == "nonexistent_fn"


# ---------------------------------------------------------------------------
# Test 3: Snippet resolves but owners fails → graceful degradation
# ---------------------------------------------------------------------------


class TestGetSnippetRichOwnersFailure:
    @pytest.mark.asyncio
    async def test_owners_fail_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_session = _fake_session(_SEARCH_GRAPH_HIT, _SNIPPET_RESPONSE)
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        mock_bridge = AsyncMock()
        mock_bridge.search_by_symbol_id_async = AsyncMock(return_value=[])
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=False)

        mock_driver = AsyncMock()
        mock_neo4j_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)
        mock_neo4j_session.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        mock_neo4j_session.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session = MagicMock(return_value=mock_neo4j_session)

        with (
            patch("palace_mcp.code_composite.TantivyBridge", return_value=mock_bridge),
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
            patch(
                "palace_mcp.code.find_owners.find_owners",
                new=AsyncMock(side_effect=RuntimeError("owners DB offline")),
            ),
            patch(
                "palace_mcp.git.tools.palace_git_log",
                new=AsyncMock(return_value=_COMMITS_RESPONSE),
            ),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, qualified_name="my_fn")

        assert payload["ok"] is True
        assert payload["owners"] == []
        assert "owners_error" in payload
        assert "owners DB offline" in payload["owners_error"]


# ---------------------------------------------------------------------------
# Test 4: Snippet resolves but hotspot fails → graceful degradation
# ---------------------------------------------------------------------------


class TestGetSnippetRichHotspotFailure:
    @pytest.mark.asyncio
    async def test_hotspot_fail_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_session = _fake_session(_SEARCH_GRAPH_HIT, _SNIPPET_RESPONSE)
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        mock_bridge = AsyncMock()
        mock_bridge.search_by_symbol_id_async = AsyncMock(return_value=[])
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=False)

        mock_driver = AsyncMock()
        mock_neo4j_session = AsyncMock()
        mock_neo4j_session.run = AsyncMock(
            side_effect=RuntimeError("Neo4j unavailable")
        )
        mock_neo4j_session.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        mock_neo4j_session.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session = MagicMock(return_value=mock_neo4j_session)

        with (
            patch("palace_mcp.code_composite.TantivyBridge", return_value=mock_bridge),
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
            patch(
                "palace_mcp.code.find_owners.find_owners",
                new=AsyncMock(return_value=_OWNERS_RESPONSE),
            ),
            patch(
                "palace_mcp.git.tools.palace_git_log",
                new=AsyncMock(return_value=_COMMITS_RESPONSE),
            ),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, qualified_name="my_fn")

        assert payload["ok"] is True
        assert payload["hotspot_score"] is None
        assert "hotspot_error" in payload
        assert "Neo4j unavailable" in payload["hotspot_error"]


# ---------------------------------------------------------------------------
# Test 5: Snippet resolves but git fails → graceful degradation
# ---------------------------------------------------------------------------


class TestGetSnippetRichGitFailure:
    @pytest.mark.asyncio
    async def test_git_fail_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_session = _fake_session(_SEARCH_GRAPH_HIT, _SNIPPET_RESPONSE)
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        mock_bridge = AsyncMock()
        mock_bridge.search_by_symbol_id_async = AsyncMock(return_value=[])
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=False)

        mock_driver = AsyncMock()
        mock_neo4j_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)
        mock_neo4j_session.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        mock_neo4j_session.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session = MagicMock(return_value=mock_neo4j_session)

        with (
            patch("palace_mcp.code_composite.TantivyBridge", return_value=mock_bridge),
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
            patch(
                "palace_mcp.code.find_owners.find_owners",
                new=AsyncMock(return_value=_OWNERS_RESPONSE),
            ),
            patch(
                "palace_mcp.git.tools.palace_git_log",
                new=AsyncMock(side_effect=RuntimeError("git subprocess crashed")),
            ),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, qualified_name="my_fn")

        assert payload["ok"] is True
        assert payload["recent_commits"] == []
        assert "recent_commits_error" in payload
        assert "git subprocess crashed" in payload["recent_commits_error"]


# ---------------------------------------------------------------------------
# Test 6: Snippet resolves but usages/Tantivy fails → graceful degradation (F4)
# ---------------------------------------------------------------------------


class TestGetSnippetRichTantivyFailure:
    @pytest.mark.asyncio
    async def test_tantivy_fail_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_session = _fake_session(_SEARCH_GRAPH_HIT, _SNIPPET_RESPONSE)
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        mock_bridge = AsyncMock()
        mock_bridge.search_by_symbol_id_async = AsyncMock(
            side_effect=RuntimeError("tantivy index corrupt")
        )
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=False)

        mock_driver = AsyncMock()
        mock_neo4j_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"hotspot_score": 0.5})
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)
        mock_neo4j_session.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        mock_neo4j_session.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session = MagicMock(return_value=mock_neo4j_session)

        with (
            patch("palace_mcp.code_composite.TantivyBridge", return_value=mock_bridge),
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
            patch(
                "palace_mcp.code.find_owners.find_owners",
                new=AsyncMock(return_value=_OWNERS_RESPONSE),
            ),
            patch(
                "palace_mcp.git.tools.palace_git_log",
                new=AsyncMock(return_value=_COMMITS_RESPONSE),
            ),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, qualified_name="my_fn")

        assert payload["ok"] is True
        assert payload["usages"] == []
        assert "usages_error" in payload
        assert "tantivy index corrupt" in payload["usages_error"]


# ---------------------------------------------------------------------------
# Test 7: CM session None → infrastructure error
# ---------------------------------------------------------------------------


class TestGetSnippetRichCmSessionNone:
    @pytest.mark.asyncio
    async def test_cm_session_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: None)

        mock_driver = AsyncMock()
        mock_settings = MagicMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
        ):
            mcp = _make_mcp_and_register()
            with pytest.raises(ToolError):
                await mcp.call_tool(
                    "palace.code.get_snippet_rich", {"qualified_name": "my_fn"}
                )


# ---------------------------------------------------------------------------
# Test 8: Validation error — bad qualified_name
# ---------------------------------------------------------------------------


class TestGetSnippetRichValidation:
    @pytest.mark.asyncio
    async def test_invalid_qn_returns_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_session = AsyncMock()
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_driver = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, qualified_name="0bad name with spaces")

        assert payload["ok"] is False
        assert payload["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_no_conventions_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """I3 fix: conventions must not appear in the response."""
        fake_session = _fake_session(_SEARCH_GRAPH_HIT, _SNIPPET_RESPONSE)
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mock_settings = MagicMock()
        mock_settings.palace_tantivy_index_path = "/tmp/tantivy"
        mock_settings.palace_tantivy_heap_mb = 50

        mock_bridge = AsyncMock()
        mock_bridge.search_by_symbol_id_async = AsyncMock(return_value=[])
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=False)

        mock_driver = AsyncMock()
        mock_neo4j_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)
        mock_neo4j_session.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        mock_neo4j_session.__aexit__ = AsyncMock(return_value=False)
        mock_driver.session = MagicMock(return_value=mock_neo4j_session)

        with (
            patch("palace_mcp.code_composite.TantivyBridge", return_value=mock_bridge),
            patch("palace_mcp.mcp_server.get_driver", return_value=mock_driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
            patch(
                "palace_mcp.code.find_owners.find_owners",
                new=AsyncMock(return_value=_OWNERS_RESPONSE),
            ),
            patch(
                "palace_mcp.git.tools.palace_git_log",
                new=AsyncMock(return_value=_COMMITS_RESPONSE),
            ),
        ):
            mcp = _make_mcp_and_register()
            payload = await _call(mcp, qualified_name="my_fn")

        assert payload["ok"] is True
        assert "conventions" not in payload
