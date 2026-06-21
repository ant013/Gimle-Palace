"""Tests for palace.code.find_cross_module_contracts composite MCP tool (GIM-228, S0.2)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ("tests.integration.hotspot_wire_support",)

_BUNDLE_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "find_cross_module_contracts_bundle_fixture.json"
)


def _mock_driver_no_project() -> MagicMock:
    single_result = AsyncMock()
    single_result.single = AsyncMock(return_value=None)
    session = AsyncMock()
    session.run = AsyncMock(return_value=single_result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


class _BundleHealth:
    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {"name": "bundle-one", "members_total": 2}


class _FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def __aiter__(self) -> "_FakeResult":
        self._idx = 0
        return self

    async def __anext__(self) -> dict[str, object]:
        if self._idx >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._idx]
        self._idx += 1
        return row

    async def single(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def run(self, _query: str, **_kwargs: object) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeDriver:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def session(self) -> _FakeSession:
        return _FakeSession(self._rows)


class _QueuedSession:
    def __init__(self, row_sets: list[list[dict[str, object]]]) -> None:
        self._row_sets = row_sets

    async def __aenter__(self) -> "_QueuedSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def run(self, _query: str, **_kwargs: object) -> _FakeResult:
        if not self._row_sets:
            raise AssertionError("unexpected extra query")
        return _FakeResult(self._row_sets.pop(0))


class _QueuedDriver:
    def __init__(self, *row_sets: list[dict[str, object]]) -> None:
        self._row_sets = list(row_sets)

    def session(self) -> _QueuedSession:
        return _QueuedSession(self._row_sets)


@pytest.mark.asyncio
async def test_find_cross_module_contracts_project_not_registered() -> None:
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    driver = _mock_driver_no_project()
    result = await find_cross_module_contracts(driver=driver, project="no-such-project")
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_find_cross_module_contracts_missing_target() -> None:
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    result = await find_cross_module_contracts(driver=MagicMock())
    assert result["ok"] is False
    assert result["error_code"] == "missing_target"


@pytest.mark.asyncio
async def test_find_cross_module_contracts_bundle_and_project_are_mutually_exclusive() -> (
    None
):
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    result = await find_cross_module_contracts(
        driver=MagicMock(),
        project="one",
        bundle="two",
    )
    assert result["ok"] is False
    assert result["error_code"] == "mutually_exclusive_args"


@pytest.mark.asyncio
async def test_find_cross_module_contracts_bundle_payload_without_neo4j(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp.code import find_cross_module_contracts as module

    async def _fake_resolve_slug(_driver: object, _target_slug: str) -> SimpleNamespace:
        return SimpleNamespace(
            kind="bundle",
            member_slugs=["contracts-bundle-alpha", "contracts-bundle-beta"],
        )

    async def _fake_bundle_status(_driver: object, *, bundle: str) -> _BundleHealth:
        assert bundle == "bundle-one"
        return _BundleHealth()

    monkeypatch.setattr(module, "_resolve_slug", _fake_resolve_slug)
    monkeypatch.setattr(module, "bundle_status", _fake_bundle_status)
    driver = _FakeDriver(
        [
            {
                "member_project": "contracts-bundle-alpha",
                "consumer_module": "WalletUI",
                "producer_module": "CoreKit",
                "language": "swift",
                "from_commit": "e0e0e0",
                "to_commit": "f0f0f0",
                "removed_count": 2,
                "added_count": 1,
                "signature_changed_count": 0,
                "affected_use_count": 5,
            },
            {
                "member_project": "contracts-bundle-beta",
                "consumer_module": "SettingsUI",
                "producer_module": "SyncKit",
                "language": "kotlin",
                "from_commit": "909090",
                "to_commit": "a0a0a0",
                "removed_count": 0,
                "added_count": 3,
                "signature_changed_count": 1,
                "affected_use_count": 4,
            },
        ]
    )

    result = await module.find_cross_module_contracts(
        driver=driver, bundle="bundle-one"
    )

    assert result == {
        "ok": True,
        "mode": "bundle",
        "target_slug": "bundle-one",
        "bundle_health": {"name": "bundle-one", "members_total": 2},
        "result": [
            {
                "consumer_module": "WalletUI",
                "producer_module": "CoreKit",
                "language": "swift",
                "from_commit": "e0e0e0",
                "to_commit": "f0f0f0",
                "removed_count": 2,
                "added_count": 1,
                "signature_changed_count": 0,
                "affected_use_count": 5,
                "member_project": "contracts-bundle-alpha",
            },
            {
                "consumer_module": "SettingsUI",
                "producer_module": "SyncKit",
                "language": "kotlin",
                "from_commit": "909090",
                "to_commit": "a0a0a0",
                "removed_count": 0,
                "added_count": 3,
                "signature_changed_count": 1,
                "affected_use_count": 4,
                "member_project": "contracts-bundle-beta",
            },
        ],
    }


@pytest.mark.asyncio
async def test_find_cross_module_contracts_returns_not_extracted_without_snapshots_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp.code import find_cross_module_contracts as module

    async def _fake_resolve_slug(_driver: object, _target_slug: str) -> SimpleNamespace:
        return SimpleNamespace(kind="project", member_slugs=[])

    monkeypatch.setattr(module, "_resolve_slug", _fake_resolve_slug)
    driver = _QueuedDriver([], [{"present": False}])

    result = await module.find_cross_module_contracts(
        driver=driver,
        project="contracts-empty",
    )

    assert result == {
        "ok": False,
        "error_code": "not_extracted",
        "message": (
            "no cross-module contract snapshot/delta records found; "
            "run public_api_surface and cross_module_contract first"
        ),
        "project": "contracts-empty",
    }


@pytest.mark.asyncio
async def test_find_cross_module_contracts_returns_empty_when_snapshots_exist_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp.code import find_cross_module_contracts as module

    async def _fake_resolve_slug(_driver: object, _target_slug: str) -> SimpleNamespace:
        return SimpleNamespace(kind="project", member_slugs=[])

    monkeypatch.setattr(module, "_resolve_slug", _fake_resolve_slug)
    driver = _QueuedDriver([], [{"present": True}])

    result = await module.find_cross_module_contracts(
        driver=driver,
        project="contracts-zero",
    )

    assert result == {
        "ok": True,
        "project": "contracts-zero",
        "result": [],
    }


@pytest.fixture(scope="module")
def contracts_empty_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"cm-empty-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def contracts_seeded_bundle(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[dict[str, object]]:
    from neo4j import GraphDatabase

    payload = cast(
        dict[str, object], json.loads(_BUNDLE_FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    bundle = cast(str, payload["bundle"])
    projects = cast(list[dict[str, object]], payload["projects"])
    excluded_projects = cast(
        list[dict[str, object]], payload.get("excluded_projects", [])
    )
    all_projects = projects + excluded_projects
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run(
            "MERGE (b:Bundle {name: $name}) "
            "SET b.group_id = 'bundle/' + $name, "
            "    b.description = 'Find contracts wire bundle fixture', "
            "    b.created_at = datetime('2026-05-20T00:00:00Z')",
            name=bundle,
        )
        for project in projects:
            sess.run(
                "MERGE (p:Project {slug: $slug}) SET p.group_id = $project_id",
                slug=project["slug"],
                project_id=f"project/{project['slug']}",
            )
            sess.run(
                "MATCH (b:Bundle {name: $bundle}), (p:Project {slug: $slug}) "
                "MERGE (b)-[c:CONTAINS {tier: $tier}]->(p) "
                "ON CREATE SET c.added_at = '2026-05-20T00:00:00Z'",
                bundle=bundle,
                slug=project["slug"],
                tier=project["tier"],
            )
        for project in all_projects:
            slug = cast(str, project["slug"])
            project_id = f"project/{slug}"
            finished_at = cast(str, project["last_run_finished_at"])
            sess.run(
                "MERGE (p:Project {slug: $slug}) SET p.group_id = $project_id",
                slug=slug,
                project_id=project_id,
            )
            sess.run(
                """
                MERGE (r:IngestRun {id: $run_id})
                  SET r.group_id = $project_id,
                      r.errors = [],
                      r.started_at = datetime($finished_at),
                      r.finished_at = datetime($finished_at)
                """,
                run_id=f"contracts-run-{slug}",
                project_id=project_id,
                finished_at=finished_at,
            )
            for delta in cast(list[dict[str, object]], project["deltas"]):
                sess.run(
                    """
                    CREATE (d:ModuleContractDelta {
                        id: $delta_id,
                        project: $slug,
                        group_id: $project_id,
                        consumer_module_name: $consumer_module,
                        producer_module_name: $producer_module,
                        language: $language,
                        from_commit_sha: $from_commit,
                        to_commit_sha: $to_commit,
                        removed_consumed_symbol_count: $removed_count,
                        added_consumed_symbol_count: $added_count,
                        signature_changed_consumed_symbol_count: $signature_changed_count,
                        affected_use_count: $affected_use_count,
                        classification_scope: 'minimal_symbol_delta',
                        schema_version: 1
                    })
                    """,
                    delta_id=delta["delta_id"],
                    slug=slug,
                    project_id=project_id,
                    consumer_module=delta["consumer_module"],
                    producer_module=delta["producer_module"],
                    language=delta["language"],
                    from_commit=delta["from_commit"],
                    to_commit=delta["to_commit"],
                    removed_count=delta["removed_count"],
                    added_count=delta["added_count"],
                    signature_changed_count=delta["signature_changed_count"],
                    affected_use_count=delta["affected_use_count"],
                )
    yield payload
    with drv.session() as sess:
        for project in all_projects:
            slug = cast(str, project["slug"])
            project_id = f"project/{slug}"
            sess.run(
                "MATCH (n) WHERE n.project = $slug OR n.group_id = $project_id DETACH DELETE n",
                slug=slug,
                project_id=project_id,
            )
            sess.run(
                "MATCH (r:IngestRun {group_id: $project_id}) DETACH DELETE r",
                project_id=project_id,
            )
            sess.run("MATCH (p:Project {slug: $slug}) DETACH DELETE p", slug=slug)
        sess.run("MATCH (b:Bundle {name: $name}) DETACH DELETE b", name=bundle)
    drv.close()


@pytest.fixture(scope="module")
def contracts_seeded_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"cm-seeded-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            CREATE (d:ModuleContractDelta {
                id: 'delta1', project: $slug, group_id: $gid,
                consumer_module_name: 'AppModule',
                producer_module_name: 'CoreKit',
                language: 'swift',
                from_commit_sha: 'aaa111',
                to_commit_sha: 'bbb222',
                removed_consumed_symbol_count: 2,
                added_consumed_symbol_count: 1,
                signature_changed_consumed_symbol_count: 0,
                affected_use_count: 5,
                classification_scope: 'minimal_symbol_delta',
                schema_version: 1
            })
            """,
            slug=slug,
            gid=f"project/{slug}",
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.project = $s OR n.group_id = $g DETACH DELETE n",
            s=slug,
            g=f"project/{slug}",
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_cross_module_contracts_returns_not_extracted_without_snapshots(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    contracts_empty_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_cross_module_contracts(
            driver=drv, project=contracts_empty_project
        )
    finally:
        await drv.close()
    assert result == {
        "ok": False,
        "error_code": "not_extracted",
        "message": (
            "no cross-module contract snapshot/delta records found; "
            "run public_api_surface and cross_module_contract first"
        ),
        "project": contracts_empty_project,
    }


@pytest.fixture(scope="module")
def contracts_no_records_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"cm-no-records-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            CREATE (:ModuleContractSnapshot {
                id: 'snapshot-old',
                project: $slug,
                group_id: $gid,
                consumer_module_name: '__no_cross_module_consumer__',
                producer_module_name: 'CoreKit',
                language: 'swift',
                commit_sha: 'aaa111',
                symbol_count: 0,
                use_count: 0,
                file_count: 0,
                skipped_symbol_count: 2,
                schema_version: 1
            })
            CREATE (:ModuleContractSnapshot {
                id: 'snapshot-new',
                project: $slug,
                group_id: $gid,
                consumer_module_name: '__no_cross_module_consumer__',
                producer_module_name: 'CoreKit',
                language: 'swift',
                commit_sha: 'bbb222',
                symbol_count: 0,
                use_count: 0,
                file_count: 0,
                skipped_symbol_count: 2,
                schema_version: 1
            })
            """,
            slug=slug,
            gid=f"project/{slug}",
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.project = $s OR n.group_id = $g DETACH DELETE n",
            s=slug,
            g=f"project/{slug}",
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_cross_module_contracts_seeded(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    contracts_seeded_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_cross_module_contracts(
            driver=drv, project=contracts_seeded_project
        )
    finally:
        await drv.close()
    assert result["ok"] is True
    rows = result["result"]
    assert len(rows) >= 1
    row = rows[0]
    for field in (
        "consumer_module",
        "producer_module",
        "language",
        "removed_count",
        "added_count",
    ):
        assert field in row, f"Missing field: {field}"
    assert row["consumer_module"] == "AppModule"
    assert row["producer_module"] == "CoreKit"
    assert row["removed_count"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_cross_module_contracts_returns_empty_after_seeded_zero_delta_ingest(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    contracts_no_records_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_cross_module_contracts(
            driver=drv, project=contracts_no_records_project
        )
    finally:
        await drv.close()

    assert result == {
        "ok": True,
        "project": contracts_no_records_project,
        "result": [],
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_cross_module_contracts_bundle_seeded(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    contracts_seeded_bundle: dict[str, object],
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_cross_module_contracts(
            driver=drv,
            bundle=cast(str, contracts_seeded_bundle["bundle"]),
        )
    finally:
        await drv.close()
    assert result["ok"] is True
    assert result["mode"] == "bundle"
    assert result["target_slug"] == contracts_seeded_bundle["bundle"]
    assert result["bundle_health"]["members_total"] == 2
    rows = result["result"]
    assert [row["member_project"] for row in rows] == [
        "contracts-bundle-alpha",
        "contracts-bundle-beta",
    ]
    assert rows[0]["consumer_module"] == "WalletUI"
    assert rows[1]["consumer_module"] == "SettingsUI"
