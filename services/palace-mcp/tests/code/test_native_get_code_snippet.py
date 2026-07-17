from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import subprocess
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


async def _unresolved_repo_path(_: str) -> None:
    return None


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _run_text(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.asyncio
async def test_get_code_snippet_prefers_exact_symbol_bounds_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletApp.AppDelegate.bootstrap()",
                "file_path": "AppDelegate.swift",
                "short_name": "bootstrap",
                "kind": "method",
                "label": "Method",
                "commit_sha": "abc",
                "line_start": 42,
                "line_end": 49,
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
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path",
        _unresolved_repo_path,
    )
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet.resolve_snippet",
        lambda **kwargs: (
            SimpleNamespace(
                source="exact body",
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
        qualified_name="WalletApp.AppDelegate.bootstrap()",
        project="gimle",
    )

    assert result["snippet_quality"] == "exact"
    assert result["start_line"] == 42
    assert result["end_line"] == 49
    assert result["source"] == "exact body"


@pytest.mark.asyncio
async def test_get_code_snippet_uses_function_window_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletApp.AppDelegate.bootstrap()",
                "file_path": "AppDelegate.swift",
                "short_name": "bootstrap",
                "kind": "method",
                "label": "Method",
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
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path",
        _unresolved_repo_path,
    )
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
    assert result["short_name"] == "bootstrap"
    assert result["kind"] == "method"
    assert result["label"] == "Method"
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
                "short_name": "BalanceData",
                "kind": "class",
                "label": "Class",
                "commit_sha": "abc",
                "line_start": 30,
                "line_end": None,
            }
        ],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path",
        _unresolved_repo_path,
    )
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
    assert result["end_line"] == 70


@pytest.mark.asyncio
async def test_get_code_snippet_uses_file_head_when_no_line_hints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletKit.BalanceData",
                "file_path": "WalletKit.swift",
                "short_name": "BalanceData",
                "kind": "class",
                "label": "Class",
                "commit_sha": "abc",
                "line_start": None,
                "line_end": None,
            }
        ],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path",
        _unresolved_repo_path,
    )
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
                "short_name": "BalanceData",
                "kind": "class",
                "label": "Class",
                "commit_sha": None,
                "line_start": None,
                "line_end": None,
            }
        ],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path",
        _unresolved_repo_path,
    )
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet.resolve_snippet",
        lambda **_: (None, "missing_file_path", "missing"),
    )

    result = await native_get_code_snippet(
        qualified_name="WalletKit.BalanceData",
        project="gimle",
    )

    assert result is FALLBACK_TO_CM


@pytest.mark.asyncio
async def test_get_code_snippet_returns_canonical_struct_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletKit s:9WalletKit11BalanceDataV",
                "file_path": "BalanceData.swift",
                "short_name": "BalanceData",
                "kind": "struct",
                "label": "Struct",
                "commit_sha": "abc",
                "line_start": 10,
                "line_end": 20,
            }
        ],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path",
        _unresolved_repo_path,
    )
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet.resolve_snippet",
        lambda **kwargs: (
            SimpleNamespace(
                source="struct body",
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
        qualified_name="WalletKit s:9WalletKit11BalanceDataV",
        project="gimle",
    )

    assert result["short_name"] == "BalanceData"
    assert result["kind"] == "struct"
    assert result["label"] == "Struct"
    assert result["indexed_commit"] == "abc"
    assert result["commits_behind_head"] is None
    assert result["stale"] is None
    assert result["freshness_state"] == "unknown"


@pytest.mark.asyncio
async def test_get_code_snippet_passes_resolved_repo_path_to_snippet_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    repo_path = tmp_path / "repos-hs" / "WalletKit.Swift"
    seen: dict[str, object] = {}

    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    async def _resolve_repo_path(_: str) -> Path:
        return repo_path

    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path",
        _resolve_repo_path,
    )
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet.resolve_snippet",
        lambda **kwargs: (
            seen.update(kwargs)
            or SimpleNamespace(
                source="body",
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
        project="wallet-kit",
    )

    assert result["source"] == "body"
    assert seen["repo_path"] == repo_path
    assert seen["freshness"].indexed_commit == "abc"


@pytest.mark.asyncio
async def test_get_code_snippet_returns_stale_metadata_for_deleted_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_path = tmp_path / "gimle"
    repo_path.mkdir()
    _run(["git", "init", "-q", "-b", "main"], cwd=repo_path)
    _run(["git", "config", "user.email", "t@t"], cwd=repo_path)
    _run(["git", "config", "user.name", "T"], cwd=repo_path)
    (repo_path / "BalanceData.swift").write_text("struct BalanceData {}\n")
    _run(["git", "add", "."], cwd=repo_path)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=repo_path)
    indexed_commit = _run_text(["git", "rev-parse", "HEAD"], cwd=repo_path)
    (repo_path / "BalanceData.swift").unlink()
    _run(["git", "add", "-A"], cwd=repo_path)
    _run(["git", "commit", "-m", "delete", "-q"], cwd=repo_path)

    driver = _mock_driver(
        [
            {
                "qualified_name": "WalletKit.BalanceData",
                "file_path": "BalanceData.swift",
                "short_name": "BalanceData",
                "kind": "struct",
                "label": "Struct",
                "commit_sha": indexed_commit,
                "line_start": 1,
                "line_end": 1,
            }
        ],
        [],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    async def _resolve_repo_path(_: str) -> Path:
        return repo_path

    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path",
        _resolve_repo_path,
    )

    result = await native_get_code_snippet(
        qualified_name="WalletKit.BalanceData",
        project="gimle",
    )

    assert result["error_code"] == "missing_source_file"
    assert result["indexed_commit"] == indexed_commit
    assert result["commits_behind_head"] == 1
    assert result["stale"] is True
