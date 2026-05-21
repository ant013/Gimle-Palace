"""MCP wire-contract tests for palace.code.list_functions (GIM-195).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_list_functions_tool.py -m integration
"""

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
    Path(__file__).parents[1] / "fixtures" / "list_functions_bundle_fixture.json"
)
_GOLDEN_PATH = (
    Path(__file__).parents[1] / "fixtures" / "list_functions_bundle_golden.json"
)


@pytest.fixture(scope="module")
def seeded_functions_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    """Seed :Project + :File + :Function nodes for list_functions tests; delete after module."""
    from neo4j import GraphDatabase

    slug = "lf-wire-seeded"
    group_id = f"project/{slug}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            "MERGE (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "SET f.hotspot_score = 2.5, f.ccn_total = 8, f.churn_count = 5, "
            "f.complexity_status = 'fresh', f.complexity_window_days = 90, "
            "f.last_complexity_run_at = datetime('2026-05-01T00:00:00Z')",
            p=group_id,
        )
        # classify function: ccn=6
        sess.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "MERGE (fn:Function {project_id: $p, path: 'src/python_complex.py', name: 'classify', start_line: 1}) "
            "SET fn.end_line = 11, fn.ccn = 6, fn.parameter_count = 1, fn.nloc = 11, fn.language = 'python' "
            "MERGE (f)-[:CONTAINS]->(fn)",
            p=group_id,
        )
        # helper function: ccn=2
        sess.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "MERGE (fn:Function {project_id: $p, path: 'src/python_complex.py', name: 'helper', start_line: 13}) "
            "SET fn.end_line = 17, fn.ccn = 2, fn.parameter_count = 0, fn.nloc = 5, fn.language = 'python' "
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
def seeded_functions_bundle(
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
            "    b.description = 'List functions wire bundle fixture', "
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
            for file in project["files"]:
                sess.run(
                    "MERGE (f:File {project_id: $project_id, path: $path})",
                    project_id=project_id,
                    path=file["path"],
                )
                for function in file["functions"]:
                    sess.run(
                        "MATCH (f:File {project_id: $project_id, path: $path}) "
                        "MERGE (fn:Function {"
                        "  project_id: $project_id,"
                        "  path: $path,"
                        "  name: $name,"
                        "  start_line: $start_line"
                        "}) "
                        "SET fn.end_line = $end_line, "
                        "    fn.ccn = $ccn, "
                        "    fn.parameter_count = $parameter_count, "
                        "    fn.nloc = $nloc, "
                        "    fn.language = $language "
                        "MERGE (f)-[:CONTAINS]->(fn)",
                        project_id=project_id,
                        path=file["path"],
                        name=function["name"],
                        start_line=function["start_line"],
                        end_line=function["end_line"],
                        ccn=function["ccn"],
                        parameter_count=function["parameter_count"],
                        nloc=function["nloc"],
                        language=function["language"],
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
    data = cast(dict[str, object], json.loads(json.dumps(payload)))
    bundle_health = data.get("bundle_health")
    if isinstance(bundle_health, dict):
        bundle_health.pop("as_of", None)
    return data


def _response_json(result: Any) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(cast(Any, result.content[0]).text))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_unregistered_project_returns_error(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": "doesnotexist", "path": "src/x.py"},
            )
    resp = _response_json(result)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_appears_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool = next(
        (item for item in result.tools if item.name == "palace.code.list_functions"),
        None,
    )
    assert tool is not None, "palace.code.list_functions missing from tools/list"
    assert tool.inputSchema is not None, (
        "palace.code.list_functions inputSchema must not be None"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_missing_file_returns_empty(
    mcp_url: str,
    seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": seeded_functions_project, "path": "src/does_not_exist.py"},
            )
    resp = _response_json(result)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_min_ccn_filter_excludes_low(
    mcp_url: str,
    seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {
                    "project": seeded_functions_project,
                    "path": "src/python_complex.py",
                    "min_ccn": 100,
                },
            )
    resp = _response_json(result)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_returns_sorted_by_ccn_desc(
    mcp_url: str,
    seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {
                    "project": seeded_functions_project,
                    "path": "src/python_complex.py",
                    "min_ccn": 0,
                },
            )
    resp = _response_json(result)
    assert resp.get("ok") is True
    rows = resp["result"]
    assert len(rows) >= 1
    ccns = [r["ccn"] for r in rows]
    assert ccns == sorted(ccns, reverse=True)
    for r in rows:
        for k in (
            "name",
            "start_line",
            "end_line",
            "ccn",
            "parameter_count",
            "nloc",
            "language",
        ):
            assert k in r


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_bundle_and_project_are_mutually_exclusive(
    mcp_url: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": "one", "bundle": "two", "path": "src/x.py"},
            )
    resp = _response_json(result)
    assert resp["ok"] is False
    assert resp["error_code"] == "mutually_exclusive_args"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_bundle_fixture_matches_golden(
    mcp_url: str,
    seeded_functions_bundle: dict[str, object],
) -> None:
    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {
                    "bundle": seeded_functions_bundle["bundle"],
                    "path": seeded_functions_bundle["path"],
                    "min_ccn": seeded_functions_bundle["min_ccn"],
                },
            )
    resp = _response_json(result)
    assert _normalize_bundle_payload(resp) == golden
