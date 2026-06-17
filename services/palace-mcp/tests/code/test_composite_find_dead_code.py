"""Tests for dependency filtering in palace.code.find_dead_code."""

from __future__ import annotations

import json
from typing import Any

import pytest


class _FakeResult:
    def __init__(
        self,
        *,
        single_value: Any | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._single_value = single_value
        self._rows = rows or []

    async def single(self) -> Any | None:
        return self._single_value

    def __aiter__(self) -> Any:
        async def _iterate() -> Any:
            for row in self._rows:
                yield row

        return _iterate()


class _FakeSession:
    def __init__(self, run_fn: Any) -> None:
        self._run_fn = run_fn

    async def run(self, query: str, **params: Any) -> _FakeResult:
        return self._run_fn(query, params)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakeDriver:
    def __init__(self, run_fn: Any) -> None:
        self._session = _FakeSession(run_fn)

    def session(self) -> _FakeSession:
        return self._session


def _finding_row(finding_id: str, file_path: str) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "kind": "dead_symbol",
        "severity": "medium",
        "size": 1,
        "safe_to_delete_score": 0.8,
        "git_last_external_ref": None,
        "members_json": json.dumps(
            [
                {
                    "qualified_name": f"{finding_id}.Symbol",
                    "kind": "function",
                    "file_path": file_path,
                }
            ]
        ),
        "module_coverage_ratio": None,
        "target_dead_type": None,
        "created_at": "2026-06-18T00:00:00Z",
    }


def _run_fn_dead_code(
    rows: list[dict[str, Any]],
    *,
    observed: list[tuple[str, dict[str, Any]]] | None = None,
) -> Any:
    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if observed is not None:
            observed.append((query, params))
        if "MATCH (p:Project" in query:
            return _FakeResult(single_value={"slug": params["slug"]})
        if "MATCH (f:DeadFinding" in query:
            return _FakeResult(rows=rows)
        raise AssertionError(f"unexpected query: {query}")

    return run_fn


@pytest.mark.asyncio
async def test_find_dead_code_excludes_dependency_members_by_default() -> None:
    from palace_mcp.code.find_dead_code import find_dead_code

    rows = [
        _finding_row("project-finding", "Unstoppable/Services/BalanceService.swift"),
        _finding_row(
            "dependency-finding",
            "checkouts/WalletKit/Sources/WalletClient.swift",
        ),
    ]
    driver = _FakeDriver(_run_fn_dead_code(rows))

    result = await find_dead_code(driver=driver, project="uw-ios-app")

    assert result["ok"] is True
    assert [row["finding_id"] for row in result["result"]] == ["project-finding"]
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_find_dead_code_can_include_dependency_members() -> None:
    from palace_mcp.code.find_dead_code import find_dead_code

    rows = [
        _finding_row(
            "dependency-finding",
            "checkouts/WalletKit/Sources/WalletClient.swift",
        )
    ]
    driver = _FakeDriver(_run_fn_dead_code(rows))

    result = await find_dead_code(
        driver=driver,
        project="uw-ios-app",
        include_dependencies=True,
    )

    assert result["ok"] is True
    assert [row["finding_id"] for row in result["result"]] == ["dependency-finding"]
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_find_dead_code_keeps_query_bounded_before_dependency_filtering() -> None:
    from palace_mcp.code.find_dead_code import find_dead_code

    observed: list[tuple[str, dict[str, Any]]] = []
    rows = [
        _finding_row(
            "dependency-finding",
            "checkouts/WalletKit/Sources/WalletClient.swift",
        ),
        _finding_row("project-finding", "Unstoppable/Services/BalanceService.swift"),
    ]
    driver = _FakeDriver(_run_fn_dead_code(rows, observed=observed))

    result = await find_dead_code(driver=driver, project="uw-ios-app", limit=17)

    assert result["ok"] is True
    query, params = next(
        (query, params) for query, params in observed if "MATCH (f:DeadFinding" in query
    )
    assert "LIMIT $limit" in query
    assert params["limit"] == 17
