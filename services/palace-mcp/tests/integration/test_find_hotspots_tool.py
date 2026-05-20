"""MCP wire-contract tests for palace.code.find_hotspots (GIM-195).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_find_hotspots_tool.py -m integration
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytest_plugins = ("tests.integration.hotspot_wire_support",)

_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "find_hotspots_bundle_fixture.json"
)
_GOLDEN_PATH = (
    Path(__file__).parents[1] / "fixtures" / "find_hotspots_bundle_golden.json"
)


@pytest.fixture(scope="module")
def registered_project_empty(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    """Create a bare :Project node with no :File nodes; delete after module."""
    from neo4j import GraphDatabase

    slug = "hotspot-wire-empty"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def seeded_hotspot_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    """Seed :Project + :File nodes with hotspot data for query tests."""
    from neo4j import GraphDatabase

    slug = "hotspot-wire-seeded"
    group_id = f"project/{slug}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            "MERGE (f:File {project_id: $p, path: 'src/complex.py'}) "
            "SET f.hotspot_score = 2.5, f.ccn_total = 8, f.churn_count = 5, "
            "f.complexity_status = 'fresh', f.complexity_window_days = 90, "
            "f.last_complexity_run_at = datetime('2026-05-01T00:00:00Z')",
            p=group_id,
        )
        sess.run(
            "MERGE (f:File {project_id: $p, path: 'src/simple.py'}) "
            "SET f.hotspot_score = 0.8, f.ccn_total = 2, f.churn_count = 2, "
            "f.complexity_status = 'fresh', f.complexity_window_days = 90, "
            "f.last_complexity_run_at = datetime('2026-05-01T00:00:00Z')",
            p=group_id,
        )
        sess.run(
            "MATCH (f:File {project_id: $p, path: 'src/complex.py'}) "
            "MERGE (fn:Function {project_id: $p, path: 'src/complex.py', name: 'classify', start_line: 1}) "
            "SET fn.end_line = 13, fn.ccn = 6, fn.parameter_count = 1, fn.nloc = 13, fn.language = 'python' "
            "MERGE (f)-[:CONTAINS]->(fn)",
            p=group_id,
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.project_id = $g DETACH DELETE n",
            g=group_id,
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def seeded_hotspot_bundle(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[dict[str, object]]:
    from neo4j import GraphDatabase

    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    bundle = payload["bundle"]
    projects = payload["projects"]
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run(
            "MERGE (b:Bundle {name: $name}) "
            "SET b.group_id = 'bundle/' + $name, "
            "    b.description = 'Hotspot wire bundle fixture', "
            "    b.created_at = datetime('2026-05-17T00:00:00Z')",
            name=bundle,
        )
        for project in projects:
            slug = project["slug"]
            tier = project["tier"]
            finished_at = project["last_run_finished_at"]
            project_id = f"project/{slug}"
            sess.run(
                "MERGE (p:Project {slug: $slug}) SET p.group_id = $project_id",
                slug=slug,
                project_id=project_id,
            )
            sess.run(
                "MATCH (b:Bundle {name: $bundle}), (p:Project {slug: $slug}) "
                "MERGE (b)-[c:CONTAINS {tier: $tier}]->(p) "
                "ON CREATE SET c.added_at = '2026-05-17T00:00:00Z'",
                bundle=bundle,
                slug=slug,
                tier=tier,
            )
            sess.run(
                "CREATE (:IngestRun {"
                "  id: $id,"
                "  group_id: $project_id,"
                "  source: 'hotspot',"
                "  started_at: datetime($finished_at),"
                "  finished_at: datetime($finished_at),"
                "  duration_ms: 1000,"
                "  errors: []"
                "})",
                id=f"run-{slug}",
                project_id=project_id,
                finished_at=finished_at,
            )
            for item in project["files"]:
                sess.run(
                    "MERGE (f:File {project_id: $project_id, path: $path}) "
                    "SET f.hotspot_score = $hotspot_score, "
                    "    f.ccn_total = $ccn_total, "
                    "    f.churn_count = $churn_count, "
                    "    f.complexity_status = $complexity_status, "
                    "    f.complexity_window_days = $window_days, "
                    "    f.last_complexity_run_at = datetime($computed_at)",
                    project_id=project_id,
                    path=item["path"],
                    hotspot_score=item["hotspot_score"],
                    ccn_total=item["ccn_total"],
                    churn_count=item["churn_count"],
                    complexity_status=item["complexity_status"],
                    window_days=item["complexity_window_days"],
                    computed_at=item["last_complexity_run_at"],
                )
    yield payload
    with drv.session() as sess:
        for project in projects:
            slug = project["slug"]
            project_id = f"project/{slug}"
            sess.run(
                "MATCH (n) WHERE n.project_id = $project_id DETACH DELETE n",
                project_id=project_id,
            )
            sess.run(
                "MATCH (r:IngestRun {group_id: $project_id}) DETACH DELETE r",
                project_id=project_id,
            )
            sess.run("MATCH (p:Project {slug: $slug}) DETACH DELETE p", slug=slug)
        sess.run("MATCH (b:Bundle {name: $name}) DETACH DELETE b", name=bundle)
    drv.close()


def _normalize_bundle_payload(payload: dict[str, object]) -> dict[str, object]:
    data = json.loads(json.dumps(payload))
    bundle_health = data.get("bundle_health")
    if isinstance(bundle_health, dict):
        bundle_health.pop("as_of", None)
    return data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_unregistered_project_returns_error(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": "doesnotexist"},
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_appears_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool = next(
        (item for item in result.tools if item.name == "palace.code.find_hotspots"),
        None,
    )
    assert tool is not None, "palace.code.find_hotspots missing from tools/list"
    assert tool.inputSchema is not None, (
        "palace.code.find_hotspots inputSchema must not be None"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_registered_no_files_returns_empty(
    mcp_url: str,
    registered_project_empty: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": registered_project_empty},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_with_data_returns_sorted_descending(
    mcp_url: str,
    seeded_hotspot_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": seeded_hotspot_project, "top_n": 5},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    rows = resp["result"]
    assert len(rows) > 0
    scores = [r["hotspot_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    for r in rows:
        for k in (
            "path",
            "ccn_total",
            "churn_count",
            "hotspot_score",
            "computed_at",
            "window_days",
        ):
            assert k in r


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_min_score_filter(
    mcp_url: str,
    seeded_hotspot_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": seeded_hotspot_project, "min_score": 1.5},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    for r in resp["result"]:
        assert r["hotspot_score"] >= 1.5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_bundle_and_project_are_mutually_exclusive(
    mcp_url: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": "one", "bundle": "two"},
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is False
    assert resp["error_code"] == "mutually_exclusive_args"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_bundle_fixture_matches_golden(
    mcp_url: str,
    seeded_hotspot_bundle: dict[str, object],
) -> None:
    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {
                    "bundle": seeded_hotspot_bundle["bundle"],
                    "path_prefix": seeded_hotspot_bundle["path_prefix"],
                    "top_n": seeded_hotspot_bundle["top_n"],
                    "min_score": seeded_hotspot_bundle["min_score"],
                },
            )
    resp = json.loads(result.content[0].text)
    assert _normalize_bundle_payload(resp) == golden
