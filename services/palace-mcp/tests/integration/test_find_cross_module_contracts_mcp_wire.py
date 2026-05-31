"""MCP wire-contract tests for palace.code.find_cross_module_contracts bundle mode."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytest_plugins = ("tests.integration.hotspot_wire_support",)

_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "find_cross_module_contracts_bundle_fixture.json"
)
_GOLDEN_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "find_cross_module_contracts_bundle_golden.json"
)


@pytest.fixture(scope="module")
def seeded_contracts_bundle(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[dict[str, object]]:
    from neo4j import GraphDatabase

    payload = cast(
        dict[str, object], json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
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


def _response_json(result: Any) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(cast(Any, result.content[0]).text))


def _normalize_bundle_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip wall-clock-dependent fields (GIM-1078)."""
    data = cast(dict[str, Any], json.loads(json.dumps(payload)))
    bundle_health = data.get("bundle_health")
    if isinstance(bundle_health, dict):
        for k in (
            "as_of",
            "members_fresh_within_7d",
            "members_stale",
            "stale_slugs",
            "oldest_member_ingest_at",
            "newest_member_ingest_at",
        ):
            bundle_health.pop(k, None)
    return data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_cross_module_contracts_bundle_and_project_are_mutually_exclusive(
    mcp_url: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_cross_module_contracts",
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
async def test_find_cross_module_contracts_bundle_fixture_matches_golden(
    mcp_url: str,
    seeded_contracts_bundle: dict[str, object],
) -> None:
    golden = cast(dict[str, Any], json.loads(_GOLDEN_PATH.read_text(encoding="utf-8")))
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_cross_module_contracts",
                {
                    "bundle": seeded_contracts_bundle["bundle"],
                    "limit": seeded_contracts_bundle["limit"],
                },
            )
    resp = _response_json(result)
    assert _normalize_bundle_payload(resp) == golden
