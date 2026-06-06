"""Tests for palace.code.find_public_api composite MCP tool (GIM-228, S0.2)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ("tests.integration.hotspot_wire_support",)

_BUNDLE_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "find_public_api_bundle_fixture.json"
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


@pytest.mark.asyncio
async def test_find_public_api_project_not_registered() -> None:
    from palace_mcp.code.find_public_api import find_public_api

    driver = _mock_driver_no_project()
    result = await find_public_api(driver=driver, project="no-such-project")
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_find_public_api_missing_target() -> None:
    from palace_mcp.code.find_public_api import find_public_api

    result = await find_public_api(driver=MagicMock())
    assert result["ok"] is False
    assert result["error_code"] == "missing_target"


@pytest.mark.asyncio
async def test_find_public_api_bundle_and_project_are_mutually_exclusive() -> None:
    from palace_mcp.code.find_public_api import find_public_api

    result = await find_public_api(
        driver=MagicMock(),
        project="one",
        bundle="two",
    )
    assert result["ok"] is False
    assert result["error_code"] == "mutually_exclusive_args"


@pytest.fixture(scope="module")
def public_api_empty_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"pa-empty-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def public_api_seeded_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"pa-seeded-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            CREATE (surface:PublicApiSurface {
                id: 'surface1', project: $slug, group_id: $gid,
                module_name: 'CoreKit', language: 'swift',
                commit_sha: 'abc123',
                artifact_path: 'CoreKit.swiftinterface',
                artifact_kind: 'swiftinterface',
                tool_name: 'swiftinterface_parser',
                tool_version: '1.0',
                schema_version: 1
            })
            CREATE (sym:PublicApiSymbol {
                id: 'sym1', project: $slug, group_id: $gid,
                module_name: 'CoreKit', language: 'swift',
                commit_sha: 'abc123',
                fqn: 'CoreKit.WalletService',
                display_name: 'WalletService',
                kind: 'class',
                visibility: 'public',
                signature: 'public class WalletService',
                signature_hash: 'hash1',
                source_artifact_path: 'CoreKit.swiftinterface',
                schema_version: 1
            })
            MERGE (surface)-[:EXPORTS]->(sym)
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


@pytest.fixture(scope="module")
def public_api_seeded_bundle(
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
            "    b.description = 'Find public API wire bundle fixture', "
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
                MERGE (r:IngestRun {run_id: $run_id})
                  SET r.group_id = $project_id,
                      r.errors = [],
                      r.started_at = datetime($finished_at),
                      r.finished_at = datetime($finished_at)
                """,
                run_id=f"public-api-run-{slug}",
                project_id=project_id,
                finished_at=finished_at,
            )
            for symbol in cast(list[dict[str, object]], project["symbols"]):
                sess.run(
                    """
                    CREATE (surface:PublicApiSurface {
                        id: $surface_id,
                        project: $slug,
                        group_id: $project_id,
                        module_name: $module_name,
                        language: $language,
                        commit_sha: $commit_sha,
                        artifact_path: $artifact_path,
                        artifact_kind: $artifact_kind,
                        tool_name: 'fixture',
                        tool_version: '1.0',
                        schema_version: 1
                    })
                    CREATE (sym:PublicApiSymbol {
                        id: $symbol_id,
                        project: $slug,
                        group_id: $project_id,
                        module_name: $module_name,
                        language: $language,
                        commit_sha: $commit_sha,
                        fqn: $fqn,
                        display_name: $display_name,
                        kind: $kind,
                        visibility: $visibility,
                        signature: $signature,
                        signature_hash: $signature_hash,
                        source_artifact_path: $artifact_path,
                        schema_version: 1
                    })
                    MERGE (surface)-[:EXPORTS]->(sym)
                    """,
                    surface_id=symbol["surface_id"],
                    symbol_id=symbol["symbol_id"],
                    slug=slug,
                    project_id=project_id,
                    module_name=symbol["module_name"],
                    language=symbol["language"],
                    commit_sha=symbol["commit_sha"],
                    artifact_path=symbol["artifact_path"],
                    artifact_kind=symbol["artifact_kind"],
                    fqn=symbol["fqn"],
                    display_name=symbol["display_name"],
                    kind=symbol["kind"],
                    visibility=symbol["visibility"],
                    signature=symbol["signature"],
                    signature_hash=symbol["signature_hash"],
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_public_api_empty_graph(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    public_api_empty_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_public_api import find_public_api

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_public_api(driver=drv, project=public_api_empty_project)
    finally:
        await drv.close()
    assert result["ok"] is True
    assert result["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_public_api_seeded(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    public_api_seeded_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_public_api import find_public_api

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_public_api(driver=drv, project=public_api_seeded_project)
    finally:
        await drv.close()
    assert result["ok"] is True
    rows = result["result"]
    assert len(rows) >= 1
    row = rows[0]
    for field in ("fqn", "module_name", "kind", "visibility"):
        assert field in row, f"Missing field: {field}"
    assert row["fqn"] == "CoreKit.WalletService"
    assert row["visibility"] == "public"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_public_api_bundle_seeded(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    public_api_seeded_bundle: dict[str, object],
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_public_api import find_public_api

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_public_api(
            driver=drv,
            bundle=cast(str, public_api_seeded_bundle["bundle"]),
        )
    finally:
        await drv.close()
    assert result["ok"] is True
    assert result["mode"] == "bundle"
    assert result["target_slug"] == public_api_seeded_bundle["bundle"]
    assert result["bundle_health"]["members_total"] == 2
    rows = result["result"]
    assert [row["member_project"] for row in rows] == [
        "public-api-bundle-alpha",
        "public-api-bundle-beta",
    ]
    assert rows[0]["fqn"] == "AlphaKit.ProfileAPI"
    assert rows[1]["fqn"] == "BetaKit.SettingsAPI"
