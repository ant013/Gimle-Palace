from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.code.native_get_code_snippet import native_get_code_snippet


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


def _mock_driver(*row_sets: list[dict[str, object]]) -> object:
    session = AsyncMock()
    session.run = AsyncMock(side_effect=[_AsyncRows(rows) for rows in row_sets])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.mark.asyncio
async def test_get_code_snippet_uses_function_window_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletApp.AppDelegate.bootstrap()",
                "file_path": "AppDelegate.swift",
                "commit_sha": "abc",
                "line_start": None,
                "line_end": None,
            }
        ],
        [
            {
                "qualified_name": "WalletApp.AppDelegate.bootstrap()",
                "file_path": "AppDelegate.swift",
                "start_line": 12,
                "end_line": 20,
            }
        ],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet.resolve_snippet",
        lambda **_: (
            SimpleNamespace(
                source="func body",
                language="swift",
                start_line=1,
                end_line=9,
                truncated=False,
                stale=False,
            ),
            None,
            None,
        ),
    )

    result = await native_get_code_snippet(
        qualified_name="WalletApp.AppDelegate.bootstrap()",
        project="gimle",
    )

    assert result["qualified_name"] == "WalletApp.AppDelegate.bootstrap()"
    assert result["snippet_quality"] == "approximate_function_match"
    assert result["source"] == "func body"


@pytest.mark.asyncio
async def test_get_code_snippet_falls_back_to_symbol_window_without_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletKit.BalanceData",
                "file_path": "WalletKit.swift",
                "commit_sha": "abc",
                "line_start": 30,
                "line_end": 35,
            }
        ],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet.resolve_snippet",
        lambda **kwargs: (
            SimpleNamespace(
                source="window",
                language="swift",
                start_line=kwargs["line_start"],
                end_line=kwargs["line_end"],
                truncated=False,
                stale=False,
            ),
            None,
            None,
        ),
    )

    result = await native_get_code_snippet(
        qualified_name="WalletKit.BalanceData",
        project="gimle",
    )

    assert result["snippet_quality"] == "approximate_window"
    assert result["start_line"] == 10
    assert result["end_line"] == 35


@pytest.mark.asyncio
async def test_get_code_snippet_uses_file_head_when_no_line_hints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletKit.BalanceData",
                "file_path": "WalletKit.swift",
                "commit_sha": "abc",
                "line_start": None,
                "line_end": None,
            }
        ],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet.resolve_snippet",
        lambda **kwargs: (
            SimpleNamespace(
                source="head",
                language="swift",
                start_line=kwargs["line_start"],
                end_line=kwargs["line_end"],
                truncated=False,
                stale=False,
            ),
            None,
            None,
        ),
    )

    result = await native_get_code_snippet(
        qualified_name="WalletKit.BalanceData",
        project="gimle",
    )

    assert result["snippet_quality"] == "file_head"
    assert result["start_line"] == 1
    assert result["end_line"] == 80


@pytest.mark.asyncio
async def test_get_code_snippet_returns_symbol_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "palace_mcp.mcp_server.get_driver",
        lambda: _mock_driver([], []),
    )

    result = await native_get_code_snippet(
        qualified_name="does.not.exist",
        project="gimle",
    )

    assert result["error_code"] == "symbol_not_found"
    assert result["requested_qualified_name"] == "does.not.exist"


@pytest.mark.asyncio
async def test_get_code_snippet_returns_ambiguous_for_short_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "palace_mcp.mcp_server.get_driver",
        lambda: _mock_driver(
            [
                {"qualified_name": "A.main", "file_path": "A.swift"},
                {"qualified_name": "B.main", "file_path": "B.swift"},
            ],
            [],
        ),
    )

    result = await native_get_code_snippet(
        qualified_name="main",
        project="gimle",
    )

    assert result["error_code"] == "ambiguous_qualified_name"
    assert len(result["matches"]) == 2


@pytest.mark.asyncio
async def test_get_code_snippet_can_fallback_to_cm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletKit.BalanceData",
                "file_path": None,
                "commit_sha": None,
                "line_start": None,
                "line_end": None,
            }
        ],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet.resolve_snippet",
        lambda **_: (None, "missing_file_path", "missing"),
    )

    result = await native_get_code_snippet(
        qualified_name="WalletKit.BalanceData",
        project="gimle",
    )

    assert result is FALLBACK_TO_CM
