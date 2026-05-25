from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "list_functions_bundle_fixture.json"
)
_GOLDEN_PATH = (
    Path(__file__).parents[1] / "fixtures" / "list_functions_bundle_golden.json"
)


class _FakeRecord:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __getitem__(self, key: str) -> Any:
        return self._payload[key]


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = [_FakeRecord(row) for row in rows]
        self._index = 0

    def __aiter__(self) -> "_FakeResult":
        self._index = 0
        return self

    async def __anext__(self) -> _FakeRecord:
        if self._index >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._index]
        self._index += 1
        return row


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((query, params))
        return _FakeResult(self.rows)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


def _driver_for_rows(rows: list[dict[str, Any]]) -> tuple[MagicMock, _FakeSession]:
    session = _FakeSession(rows)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver, session


def _bundle_health(name: str) -> Any:
    from palace_mcp.memory.models import BundleStatus

    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    return BundleStatus(
        name=name,
        members_total=2,
        members_fresh_within_7d=2,
        members_stale=0,
        query_failed_slugs=(),
        ingest_failed_slugs=(),
        never_ingested_slugs=(),
        stale_slugs=(),
        oldest_member_ingest_at=now,
        newest_member_ingest_at=now,
        as_of=now,
    )


@pytest.mark.asyncio
async def test_list_functions_requires_exactly_one_target() -> None:
    from palace_mcp.code.list_functions import list_functions

    driver, _session = _driver_for_rows([])

    both = await list_functions(
        driver=driver,
        path="src/app.py",
        project="app",
        bundle="uw-ios",
    )
    neither = await list_functions(driver=driver, path="src/app.py")

    assert both["ok"] is False
    assert both["error_code"] == "mutually_exclusive_args"
    assert neither["ok"] is False
    assert neither["error_code"] == "missing_target"


@pytest.mark.asyncio
async def test_list_functions_bundle_without_members_returns_error() -> None:
    from palace_mcp.code.list_functions import list_functions
    from palace_mcp.code_composite import SlugResolution

    driver, _session = _driver_for_rows([])

    with patch(
        "palace_mcp.code.list_functions._resolve_slug",
        new=AsyncMock(return_value=SlugResolution(kind="bundle", member_slugs=[])),
    ):
        result = await list_functions(
            driver=driver,
            bundle="uw-ios",
            path="Modules/Send/Shared.swift",
        )

    assert result["ok"] is False
    assert result["error_code"] == "bundle_has_no_members"


@pytest.mark.asyncio
async def test_list_functions_bundle_uses_project_ids_and_path() -> None:
    from palace_mcp.code.list_functions import list_functions
    from palace_mcp.code_composite import SlugResolution

    driver, session = _driver_for_rows(
        [
            {
                "project_id": "project/alpha-kit",
                "name": "sendNow",
                "start_line": 7,
                "end_line": 18,
                "ccn": 8,
                "parameter_count": 1,
                "nloc": 12,
                "language": "swift",
            }
        ]
    )

    with (
        patch(
            "palace_mcp.code.list_functions._resolve_slug",
            new=AsyncMock(
                return_value=SlugResolution(
                    kind="bundle",
                    member_slugs=["alpha-kit", "beta-kit"],
                )
            ),
        ),
        patch(
            "palace_mcp.code.list_functions.bundle_status",
            new=AsyncMock(return_value=_bundle_health("uw-ios")),
        ),
    ):
        result = await list_functions(
            driver=driver,
            bundle="uw-ios",
            path="Modules/Send/Shared.swift",
            min_ccn=5,
        )

    params = session.calls[0][1]
    assert params["project_ids"] == ["project/alpha-kit", "project/beta-kit"]
    assert params["path"] == "Modules/Send/Shared.swift"
    assert params["min_ccn"] == 5
    assert result == {
        "ok": True,
        "mode": "bundle",
        "target_slug": "uw-ios",
        "bundle_health": {
            "name": "uw-ios",
            "members_total": 2,
            "members_fresh_within_7d": 2,
            "members_stale": 0,
            "query_failed_slugs": [],
            "ingest_failed_slugs": [],
            "never_ingested_slugs": [],
            "stale_slugs": [],
            "oldest_member_ingest_at": "2026-05-20T00:00:00Z",
            "newest_member_ingest_at": "2026-05-20T00:00:00Z",
            "as_of": "2026-05-20T00:00:00Z",
        },
        "result": [
            {
                "project_id": "alpha-kit",
                "name": "sendNow",
                "start_line": 7,
                "end_line": 18,
                "ccn": 8,
                "parameter_count": 1,
                "nloc": 12,
                "language": "swift",
            }
        ],
    }


@pytest.mark.asyncio
async def test_list_functions_project_response_remains_flat() -> None:
    from palace_mcp.code.list_functions import list_functions
    from palace_mcp.code_composite import SlugResolution

    driver, _session = _driver_for_rows(
        [
            {
                "project_id": "project/app-kit",
                "name": "runApp",
                "start_line": 2,
                "end_line": 12,
                "ccn": 3,
                "parameter_count": 0,
                "nloc": 11,
                "language": "python",
            }
        ]
    )

    with patch(
        "palace_mcp.code.list_functions._resolve_slug",
        new=AsyncMock(return_value=SlugResolution(kind="project")),
    ):
        result = await list_functions(
            driver=driver,
            project="app-kit",
            path="src/main.py",
        )

    assert result == {
        "ok": True,
        "result": [
            {
                "name": "runApp",
                "start_line": 2,
                "end_line": 12,
                "ccn": 3,
                "parameter_count": 0,
                "nloc": 11,
                "language": "python",
            }
        ],
    }


@pytest.mark.asyncio
async def test_list_functions_bundle_missing_path_returns_warning() -> None:
    from palace_mcp.code.list_functions import list_functions
    from palace_mcp.code_composite import SlugResolution

    driver, _session = _driver_for_rows([])

    with (
        patch(
            "palace_mcp.code.list_functions._resolve_slug",
            new=AsyncMock(
                return_value=SlugResolution(
                    kind="bundle",
                    member_slugs=["alpha-kit", "beta-kit"],
                )
            ),
        ),
        patch(
            "palace_mcp.code.list_functions.bundle_status",
            new=AsyncMock(return_value=_bundle_health("uw-ios")),
        ),
    ):
        result = await list_functions(
            driver=driver,
            bundle="uw-ios",
            path="Modules/Send/Missing.swift",
        )

    assert result["ok"] is True
    assert result["warning"] == "path_not_found_in_any_member"
    assert result["result"] == []


@pytest.mark.asyncio
async def test_list_functions_bundle_fixture_matches_golden_snapshot() -> None:
    from palace_mcp.code.list_functions import list_functions
    from palace_mcp.code_composite import SlugResolution

    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    rows = [
        {
            "project_id": f"project/{item['project_id']}",
            "name": item["name"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "ccn": item["ccn"],
            "parameter_count": item["parameter_count"],
            "nloc": item["nloc"],
            "language": item["language"],
        }
        for item in golden["result"]
    ]

    driver, _session = _driver_for_rows(rows)
    health = _bundle_health(fixture["bundle"]).model_copy(
        update={
            "oldest_member_ingest_at": datetime(2026, 5, 24, tzinfo=timezone.utc),
            "newest_member_ingest_at": datetime(2026, 5, 25, tzinfo=timezone.utc),
        }
    )

    with (
        patch(
            "palace_mcp.code.list_functions._resolve_slug",
            new=AsyncMock(
                return_value=SlugResolution(
                    kind="bundle",
                    member_slugs=[project["slug"] for project in fixture["projects"]],
                )
            ),
        ),
        patch(
            "palace_mcp.code.list_functions.bundle_status",
            new=AsyncMock(return_value=health),
        ),
    ):
        result = await list_functions(
            driver=driver,
            bundle=fixture["bundle"],
            path=fixture["path"],
            min_ccn=fixture["min_ccn"],
        )

    result["bundle_health"].pop("as_of", None)
    assert result == golden
