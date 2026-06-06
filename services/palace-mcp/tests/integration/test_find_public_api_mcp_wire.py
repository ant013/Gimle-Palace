"""MCP wire-contract tests for palace.code.find_public_api bundle mode."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytest_plugins = ("tests.integration.hotspot_wire_support",)

_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "find_public_api_bundle_fixture.json"
_GOLDEN_PATH = Path(__file__).parents[1] / "fixtures" / "find_public_api_bundle_golden.json"


@pytest.fixture(scope="module")
def seeded_public_api_bundle(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[dict[str, object]]:
    from neo4j import GraphDatabase

    payload = cast(dict[str, object], json.loads(_FIXTURE_PATH.read_text(encoding="utf-8")))
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


def _response_json(result: Any) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(cast(Any, result.content[0]).text))


def _normalize_bundle_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = cast(dict[str, Any], json.loads(json.dumps(payload)))
    bundle_health = data.get("bundle_health")
    if isinstance(bundle_health, dict):
        bundle_health.pop("as_of", None)
    return data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_public_api_bundle_and_project_are_mutually_exclusive(
    mcp_url: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_public_api",
                {
                    "project": "one",
                    "bundle": "two",
                },
            )
    resp = _response_json(result)
    assert resp["ok"] is False
    assert resp["error_code"] == "mutually_exclusive_args"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_public_api_bundle_fixture_matches_golden(
    mcp_url: str,
    seeded_public_api_bundle: dict[str, object],
) -> None:
    golden = cast(
        dict[str, Any], json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    )
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_public_api",
                {
                    "bundle": seeded_public_api_bundle["bundle"],
                    "limit": seeded_public_api_bundle["limit"],
                },
            )
    resp = _response_json(result)
    assert _normalize_bundle_payload(resp) == golden
