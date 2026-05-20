from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "find_hotspots_bundle_fixture.json"
)
_GOLDEN_PATH = (
    Path(__file__).parents[1] / "fixtures" / "find_hotspots_bundle_golden.json"
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
async def test_find_hotspots_requires_exactly_one_target() -> None:
    from palace_mcp.code.find_hotspots import find_hotspots

    driver, _session = _driver_for_rows([])

    both = await find_hotspots(driver=driver, project="app", bundle="uw-ios")
    neither = await find_hotspots(driver=driver)

    assert both["ok"] is False
    assert both["error_code"] == "mutually_exclusive_args"
    assert neither["ok"] is False
    assert neither["error_code"] == "missing_target"


@pytest.mark.asyncio
async def test_find_hotspots_bundle_without_members_returns_error() -> None:
    from palace_mcp.code.find_hotspots import find_hotspots
    from palace_mcp.code_composite import SlugResolution

    driver, _session = _driver_for_rows([])

    with patch(
        "palace_mcp.code.find_hotspots._resolve_slug",
        new=AsyncMock(return_value=SlugResolution(kind="bundle", member_slugs=[])),
    ):
        result = await find_hotspots(driver=driver, bundle="uw-ios")

    assert result["ok"] is False
    assert result["error_code"] == "bundle_has_no_members"


@pytest.mark.asyncio
async def test_find_hotspots_bundle_uses_project_ids_and_path_prefix() -> None:
    from palace_mcp.code.find_hotspots import find_hotspots
    from palace_mcp.code_composite import SlugResolution

    computed_at = MagicMock()
    computed_at.iso_format.return_value = "2026-05-19T00:00:00+00:00"
    driver, session = _driver_for_rows(
        [
            {
                "project_id": "project/alpha-kit",
                "path": "Modules/Send/High.swift",
                "ccn_total": 11,
                "churn_count": 7,
                "hotspot_score": 9.2,
                "computed_at": computed_at,
                "window_days": 90,
            }
        ]
    )

    with (
        patch(
            "palace_mcp.code.find_hotspots._resolve_slug",
            new=AsyncMock(
                return_value=SlugResolution(
                    kind="bundle", member_slugs=["alpha-kit", "beta-kit"]
                )
            ),
        ),
        patch(
            "palace_mcp.code.find_hotspots.bundle_status",
            new=AsyncMock(return_value=_bundle_health("uw-ios")),
        ),
    ):
        result = await find_hotspots(
            driver=driver,
            bundle="uw-ios",
            top_n=2,
            min_score=1.5,
            path_prefix="Modules/Send",
        )

    params = session.calls[0][1]
    assert params["project_ids"] == ["project/alpha-kit", "project/beta-kit"]
    assert params["path_prefix"] == "Modules/Send"
    assert params["top_n"] == 2
    assert params["min_score"] == 1.5
    assert result["ok"] is True
    assert result["mode"] == "bundle"
    assert result["target_slug"] == "uw-ios"
    assert result["bundle_health"]["name"] == "uw-ios"
    assert result["result"] == [
        {
            "project_id": "alpha-kit",
            "path": "Modules/Send/High.swift",
            "ccn_total": 11,
            "churn_count": 7,
            "hotspot_score": 9.2,
            "computed_at": "2026-05-19T00:00:00+00:00",
            "window_days": 90,
        }
    ]


@pytest.mark.asyncio
async def test_find_hotspots_project_response_remains_flat() -> None:
    from palace_mcp.code.find_hotspots import find_hotspots
    from palace_mcp.code_composite import SlugResolution

    computed_at = MagicMock()
    computed_at.iso_format.return_value = "2026-05-01T00:00:00+00:00"
    driver, _session = _driver_for_rows(
        [
            {
                "project_id": "project/app-kit",
                "path": "src/main.py",
                "ccn_total": 3,
                "churn_count": 2,
                "hotspot_score": 1.2,
                "computed_at": computed_at,
                "window_days": 90,
            }
        ]
    )

    with patch(
        "palace_mcp.code.find_hotspots._resolve_slug",
        new=AsyncMock(return_value=SlugResolution(kind="project")),
    ):
        result = await find_hotspots(driver=driver, project="app-kit")

    assert result == {
        "ok": True,
        "result": [
            {
                "path": "src/main.py",
                "ccn_total": 3,
                "churn_count": 2,
                "hotspot_score": 1.2,
                "computed_at": "2026-05-01T00:00:00+00:00",
                "window_days": 90,
            }
        ],
    }


@pytest.mark.asyncio
async def test_find_hotspots_bundle_fixture_matches_golden_snapshot() -> None:
    from palace_mcp.code.find_hotspots import find_hotspots
    from palace_mcp.code_composite import SlugResolution

    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for item in golden["result"]:
        computed_at = MagicMock()
        computed_at.iso_format.return_value = item["computed_at"]
        rows.append(
            {
                "project_id": f"project/{item['project_id']}",
                "path": item["path"],
                "ccn_total": item["ccn_total"],
                "churn_count": item["churn_count"],
                "hotspot_score": item["hotspot_score"],
                "computed_at": computed_at,
                "window_days": item["window_days"],
            }
        )

    driver, _session = _driver_for_rows(rows)
    health = _bundle_health(fixture["bundle"])
    health = health.model_copy(
        update={
            "oldest_member_ingest_at": datetime(2026, 5, 18, tzinfo=timezone.utc),
            "newest_member_ingest_at": datetime(2026, 5, 19, tzinfo=timezone.utc),
        }
    )

    with (
        patch(
            "palace_mcp.code.find_hotspots._resolve_slug",
            new=AsyncMock(
                return_value=SlugResolution(
                    kind="bundle",
                    member_slugs=[project["slug"] for project in fixture["projects"]],
                )
            ),
        ),
        patch(
            "palace_mcp.code.find_hotspots.bundle_status",
            new=AsyncMock(return_value=health),
        ),
    ):
        result = await find_hotspots(
            driver=driver,
            bundle=fixture["bundle"],
            top_n=fixture["top_n"],
            min_score=fixture["min_score"],
            path_prefix=fixture["path_prefix"],
        )

    result["bundle_health"].pop("as_of", None)
    assert result == golden
