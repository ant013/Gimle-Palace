from datetime import datetime, timezone

import pytest

from palace_mcp.extractors.code_ownership.models import OwnershipEdge
from palace_mcp.extractors.code_ownership.neo4j_writer import (
    OWNERSHIP_SOURCE,
    write_batch,
)
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _edge(path: str, author_id: str, weight: float) -> OwnershipEdge:
    return OwnershipEdge(
        project_id="gimle",
        path=path,
        canonical_id=author_id,
        canonical_email=author_id,
        canonical_name=author_id.split("@")[0],
        weight=weight,
        blame_share=weight,
        recency_churn_share=weight,
        last_touched_at=_now(),
        lines_attributed=10,
        commit_count=2,
        canonical_via="identity",
    )


@pytest.mark.asyncio
async def test_write_batch_creates_owned_by_with_source(driver):
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (a:Author {provider: 'git', identity_key: 'a@x.com'})
              SET a.email='a@x.com', a.name='A', a.is_bot=false
            """
        )
    await write_batch(
        driver,
        project_id="gimle",
        edges=[_edge("a.py", "a@x.com", 1.0)],
        file_states=[
            {"path": "a.py", "status": "processed", "no_owners_reason": None}
        ],
        deleted_paths=[],
        run_id="r1",
        alpha=0.5,
    )
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: 'gimle', path: 'a.py'})
                  -[r:OWNED_BY]->(a:Author)
            RETURN r.source AS source, r.weight AS weight,
                   r.run_id_provenance AS run_id, r.alpha_used AS alpha
            """
        )
        row = await result.single()
    assert row["source"] == OWNERSHIP_SOURCE
    assert row["weight"] == 1.0
    assert row["run_id"] == "r1"
    assert row["alpha"] == 0.5


@pytest.mark.asyncio
async def test_atomic_replace_wipes_old_then_writes_new(driver):
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (a:Author {provider: 'git', identity_key: 'old@x.com'})
              SET a.email='old@x.com', a.name='Old', a.is_bot=false
            MERGE (b:Author {provider: 'git', identity_key: 'new@x.com'})
              SET b.email='new@x.com', b.name='New', b.is_bot=false
            """
        )
    # First batch: old@x.com is owner
    await write_batch(
        driver,
        project_id="gimle",
        edges=[_edge("a.py", "old@x.com", 1.0)],
        file_states=[
            {"path": "a.py", "status": "processed", "no_owners_reason": None}
        ],
        deleted_paths=[],
        run_id="r1",
        alpha=0.5,
    )
    # Second batch: new@x.com is owner; old must be wiped
    await write_batch(
        driver,
        project_id="gimle",
        edges=[_edge("a.py", "new@x.com", 1.0)],
        file_states=[
            {"path": "a.py", "status": "processed", "no_owners_reason": None}
        ],
        deleted_paths=[],
        run_id="r2",
        alpha=0.5,
    )
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: 'gimle', path: 'a.py'})
                  -[r:OWNED_BY]->(a:Author)
            RETURN a.identity_key AS who
            """
        )
        whos = [row["who"] for row in await result.data()]
    assert whos == ["new@x.com"]


@pytest.mark.asyncio
async def test_deleted_paths_wipe_edges_no_new_writes(driver):
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (a:Author {provider: 'git', identity_key: 'a@x.com'})
              SET a.email='a@x.com', a.name='A', a.is_bot=false
            MERGE (f)-[r:OWNED_BY]->(a)
              SET r.source='extractor.code_ownership', r.weight=1.0
            """
        )
    await write_batch(
        driver,
        project_id="gimle",
        edges=[],
        file_states=[],
        deleted_paths=["a.py"],
        run_id="r1",
        alpha=0.5,
    )
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (:File {project_id: 'gimle', path: 'a.py'})
                  -[r:OWNED_BY]->()
            RETURN count(r) AS c
            """
        )
        row = await result.single()
    assert row["c"] == 0


@pytest.mark.asyncio
async def test_file_state_sidecar_written(driver):
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (b:File {project_id: 'gimle', path: 'b.bin'})
            """
        )
    await write_batch(
        driver,
        project_id="gimle",
        edges=[],
        file_states=[
            {"path": "a.py", "status": "skipped", "no_owners_reason": "all_bot_authors"},
            {"path": "b.bin", "status": "skipped", "no_owners_reason": "binary_or_skipped"},
        ],
        deleted_paths=[],
        run_id="r1",
        alpha=0.5,
    )
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (s:OwnershipFileState {project_id: 'gimle'})
            RETURN s.path AS path, s.no_owners_reason AS reason
            ORDER BY s.path
            """
        )
        rows = await result.data()
    assert {r["path"]: r["reason"] for r in rows} == {
        "a.py": "all_bot_authors",
        "b.bin": "binary_or_skipped",
    }


@pytest.mark.asyncio
async def test_synthetic_author_merged_when_canonical_unknown(driver):
    """canonical_via=mailmap_synthetic → MERGE creates virtual :Author."""
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            "MERGE (f:File {project_id: 'gimle', path: 'a.py'})"
        )
    edge = _edge("a.py", "synthetic@x.com", 1.0)
    edge_dict = edge.model_dump()
    edge_dict["canonical_via"] = "mailmap_synthetic"
    syn_edge = OwnershipEdge(**edge_dict)
    await write_batch(
        driver,
        project_id="gimle",
        edges=[syn_edge],
        file_states=[
            {"path": "a.py", "status": "processed", "no_owners_reason": None}
        ],
        deleted_paths=[],
        run_id="r1",
        alpha=0.5,
    )
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:Author {provider: 'git', identity_key: 'synthetic@x.com'})
            RETURN a.identity_key AS id
            """
        )
        row = await result.single()
    assert row is not None and row["id"] == "synthetic@x.com"
