"""MCP wire-contract tests for palace.code.find_owners (GIM-216).

Tests the full HTTP+SSE round-trip through the MCP protocol layer using
streamablehttp_client. These verify the tool's inputSchema and wire contract,
not just the Python function.

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_find_owners_mcp_wire.py -m integration
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

_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "find_owners_bundle_fixture.json"
_GOLDEN_PATH = Path(__file__).parents[1] / "fixtures" / "find_owners_bundle_golden.json"


@pytest.fixture(scope="module")
def seeded_owners_project(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    """Seed a :Project + checkpoint + :File + :OWNED_BY data for find_owners tests."""
    from neo4j import GraphDatabase

    slug = "owners-wire-seeded"
    group_id = f"project/{slug}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            MERGE (c:OwnershipCheckpoint {project_id: $g})
              SET c.last_head_sha = 'deadbeef01',
                  c.last_completed_at = datetime(),
                  c.run_id = 'wire-r1',
                  c.updated_at = datetime()
            """,
            g=group_id,
        )
        sess.run(
            "MERGE (f:File {project_id: $g, path: 'src/main.py'})",
            g=group_id,
        )
        sess.run(
            """
            MERGE (a:Author {provider: 'git', identity_key: 'alice@example.com'})
              SET a.email = 'alice@example.com', a.name = 'Alice', a.is_bot = false
            """,
        )
        sess.run(
            """
            MATCH (f:File {project_id: $g, path: 'src/main.py'})
            MATCH (a:Author {provider: 'git', identity_key: 'alice@example.com'})
            MERGE (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a)
              SET r.weight = 1.0,
                  r.blame_share = 1.0,
                  r.recency_churn_share = 1.0,
                  r.last_touched_at = datetime(),
                  r.lines_attributed = 10,
                  r.commit_count = 3,
                  r.run_id_provenance = 'wire-r1',
                  r.alpha_used = 0.5,
                  r.canonical_via = 'identity'
            """,
            g=group_id,
        )
        sess.run(
            """
            MERGE (st:OwnershipFileState {project_id: $g, path: 'src/main.py'})
              SET st.status = 'processed',
                  st.no_owners_reason = null,
                  st.last_run_id = 'wire-r1',
                  st.updated_at = datetime()
            """,
            g=group_id,
        )
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (n) WHERE n.project_id = $g DETACH DELETE n", g=group_id)
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def seeded_owners_bundle(
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
            "    b.description = 'Find owners wire bundle fixture', "
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
            run_id = f"run-{slug}"
            finished_at = cast(str, project["last_run_finished_at"])
            sess.run(
                "MERGE (p:Project {slug: $slug}) SET p.group_id = $project_id",
                slug=slug,
                project_id=project_id,
            )
            sess.run(
                """
                MERGE (c:OwnershipCheckpoint {project_id: $project_id})
                  SET c.last_head_sha = $head_sha,
                      c.last_completed_at = datetime($finished_at),
                      c.run_id = $run_id,
                      c.updated_at = datetime($finished_at)
                """,
                project_id=project_id,
                head_sha=project["head_sha"],
                finished_at=finished_at,
                run_id=run_id,
            )
            sess.run(
                """
                MERGE (r:IngestRun {run_id: $run_id})
                  SET r.group_id = $project_id,
                      r.alpha_used = $alpha_used,
                      r.started_at = datetime($finished_at),
                      r.finished_at = datetime($finished_at)
                """,
                run_id=run_id,
                project_id=project_id,
                alpha_used=project["alpha_used"],
                finished_at=finished_at,
            )
            for file in cast(list[dict[str, object]], project["files"]):
                path = cast(str, file["path"])
                sess.run(
                    "MERGE (f:File {project_id: $project_id, path: $path})",
                    project_id=project_id,
                    path=path,
                )
                sess.run(
                    """
                    MERGE (st:OwnershipFileState {project_id: $project_id, path: $path})
                      SET st.status = $status,
                          st.no_owners_reason = $no_owners_reason,
                          st.last_run_id = $run_id,
                          st.updated_at = datetime($finished_at)
                    """,
                    project_id=project_id,
                    path=path,
                    status=file["status"],
                    no_owners_reason=file["no_owners_reason"],
                    run_id=run_id,
                    finished_at=finished_at,
                )
                for owner in cast(list[dict[str, object]], file["owners"]):
                    sess.run(
                        """
                        MERGE (a:Author {provider: 'git', identity_key: $identity_key})
                          SET a.email = $email,
                              a.name = $name,
                              a.is_bot = false
                        """,
                        identity_key=owner["identity_key"],
                        email=owner["email"],
                        name=owner["name"],
                    )
                    sess.run(
                        """
                        MATCH (f:File {project_id: $project_id, path: $path})
                        MATCH (a:Author {provider: 'git', identity_key: $identity_key})
                        MERGE (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a)
                          SET r.weight = $weight,
                              r.blame_share = $blame_share,
                              r.recency_churn_share = $recency_churn_share,
                              r.last_touched_at = datetime($last_touched_at),
                              r.lines_attributed = $lines_attributed,
                              r.commit_count = $commit_count,
                              r.run_id_provenance = $run_id,
                              r.alpha_used = $alpha_used,
                              r.canonical_via = 'identity'
                        """,
                        project_id=project_id,
                        path=path,
                        identity_key=owner["identity_key"],
                        weight=owner["weight"],
                        blame_share=owner["blame_share"],
                        recency_churn_share=owner["recency_churn_share"],
                        last_touched_at=owner["last_touched_at"],
                        lines_attributed=owner["lines_attributed"],
                        commit_count=owner["commit_count"],
                        run_id=run_id,
                        alpha_used=project["alpha_used"],
                    )
    yield payload
    identity_keys = [
        cast(str, owner["identity_key"])
        for project in all_projects
        for file in cast(list[dict[str, object]], project["files"])
        for owner in cast(list[dict[str, object]], file["owners"])
    ]
    with drv.session() as sess:
        for project in all_projects:
            slug = cast(str, project["slug"])
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
        for identity_key in identity_keys:
            sess.run(
                "MATCH (a:Author {provider: 'git', identity_key: $identity_key}) DETACH DELETE a",
                identity_key=identity_key,
            )
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
async def test_find_owners_appears_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool = next(
        (t for t in result.tools if t.name == "palace.code.find_owners"),
        None,
    )
    assert tool is not None, "palace.code.find_owners missing from tools/list"
    assert tool.inputSchema is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_owners_unregistered_project_returns_error(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_owners",
                {"file_path": "src/main.py", "project": "does-not-exist"},
            )
    resp = _response_json(result)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_owners_seeded_project_returns_owners(
    mcp_url: str,
    seeded_owners_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_owners",
                {
                    "file_path": "src/main.py",
                    "project": seeded_owners_project,
                    "top_n": 5,
                },
            )
    resp = _response_json(result)
    assert resp["ok"] is True
    assert len(resp["owners"]) == 1
    assert resp["owners"][0]["author_email"] == "alice@example.com"
    assert resp["owners"][0]["weight"] == pytest.approx(1.0)
    assert resp["no_owners_reason"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_owners_bundle_and_project_are_mutually_exclusive(
    mcp_url: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_owners",
                {
                    "file_path": "Modules/Send/Shared.swift",
                    "project": "one",
                    "bundle": "two",
                },
            )
    resp = _response_json(result)
    assert resp["ok"] is False
    assert resp["error_code"] == "mutually_exclusive_args"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_owners_bundle_fixture_matches_golden(
    mcp_url: str,
    seeded_owners_bundle: dict[str, object],
) -> None:
    golden = cast(
        dict[str, Any], json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    )
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_owners",
                {
                    "bundle": seeded_owners_bundle["bundle"],
                    "file_path": seeded_owners_bundle["file_path"],
                    "top_n": seeded_owners_bundle["top_n"],
                },
            )
    resp = _response_json(result)
    assert _normalize_bundle_payload(resp) == golden
