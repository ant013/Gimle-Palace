"""Integration tests for get_code_snippet scope=file|type (mocked driver)."""

from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

import pytest

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
    from unittest.mock import AsyncMock, MagicMock

    session = AsyncMock()
    session.run = AsyncMock(side_effect=[_AsyncRows(r) for r in row_sets])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


async def _no_repo(_: str) -> None:
    return None


def _fake_snip(source: str) -> Any:
    return SimpleNamespace(
        source=source, language="swift", start_line=1,
        end_line=source.count("\n") + 1, total_lines=source.count("\n") + 1,
        truncated=False, truncated_lines=0, truncated_reason=None,
        byte_count=len(source.encode()),
    )


def _patch(monkeypatch: pytest.MonkeyPatch, driver: object) -> None:
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)
    monkeypatch.setattr(
        "palace_mcp.code.native_get_code_snippet._resolve_repo_path", _no_repo
    )
    monkeypatch.setattr(
        "palace_mcp.code.snippet_scope.resolve_snippet",
        lambda *, file_path, **_: (_fake_snip(f"body of {file_path}"), None, None),
    )


_CLASS_ROW = {
    "qualified_name": "EvmKit s:6EvmKit4KitC",
    "file_path": "Sources/EvmKit/Kit.swift",
    "short_name": "Kit",
    "kind": "class",
    "label": "Class",
    "module_name": "EvmKit",
    "commit_sha": "abc",
    "line_start": 6,
    "line_end": None,
}


@pytest.mark.asyncio
async def test_scope_file_returns_whole_file_single_doc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, _mock_driver([dict(_CLASS_ROW)]))
    r = await native_get_code_snippet(
        qualified_name=_CLASS_ROW["qualified_name"], project="evm-kit", scope="file"
    )
    assert r["effective_scope"] == "file"
    assert r["snippet_quality"] == "whole_file"
    assert r["complete"] is True
    assert len(r["documents"]) == 1
    assert r["documents"][0]["role"] == "file"
    assert r["source"] == "body of Sources/EvmKit/Kit.swift"


@pytest.mark.asyncio
async def test_scope_type_unions_declaration_and_extension_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    type_files = [
        {"file_path": "Sources/EvmKit/Kit.swift", "dep_count": 0, "live_count": 9},
        {"file_path": "Sources/EvmKit/Kit+Sync.swift", "dep_count": 0, "live_count": 4},
    ]
    _patch(monkeypatch, _mock_driver([dict(_CLASS_ROW)], type_files))
    r = await native_get_code_snippet(
        qualified_name=_CLASS_ROW["qualified_name"], project="evm-kit", scope="type"
    )
    assert r["effective_scope"] == "type"
    assert r["snippet_quality"] == "whole_type"
    assert r["type_completeness"] == "best_effort"
    assert r["documents_total"] == 2
    roles = {d["role"] for d in r["documents"]}
    assert roles == {"declaration", "extension"}
    # multi-file → no top-level source footgun
    assert "source" not in r


@pytest.mark.asyncio
async def test_scope_type_on_member_downgrades_to_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member = dict(_CLASS_ROW)
    member["kind"] = "method"
    member["short_name"] = "sync"
    _patch(monkeypatch, _mock_driver([member]))
    r = await native_get_code_snippet(
        qualified_name=_CLASS_ROW["qualified_name"], project="evm-kit", scope="type"
    )
    assert r["requested_scope"] == "type"
    assert r["effective_scope"] == "file"
    assert r["scope_downgraded"] is True
    assert "member" in r["downgrade_reason"]


@pytest.mark.asyncio
async def test_scope_type_non_swift_downgrades_to_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kt = dict(_CLASS_ROW)
    kt["file_path"] = "src/Kit.kt"
    _patch(monkeypatch, _mock_driver([kt]))
    r = await native_get_code_snippet(
        qualified_name=_CLASS_ROW["qualified_name"], project="evm-kit", scope="type"
    )
    assert r["effective_scope"] == "file"
    assert r["scope_downgraded"] is True
    assert "Swift" in r["downgrade_reason"]


@pytest.mark.asyncio
async def test_unknown_scope_is_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = await native_get_code_snippet(
        qualified_name="x", project="evm-kit", scope="bogus"
    )
    assert r["error_code"] == "validation_error"
