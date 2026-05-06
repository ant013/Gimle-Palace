"""Wire-contract tests for palace.code.find_owners (GIM-216).

Calls find_owners() directly against real Neo4j.
"""

from __future__ import annotations

import pytest
from neo4j import AsyncDriver

from palace_mcp.code.find_owners import find_owners
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


@pytest.mark.asyncio
async def test_slug_invalid_error(driver: AsyncDriver) -> None:
    result = await find_owners(driver, file_path="x.py", project="!!!bad!!!", top_n=5)
    assert result["ok"] is False
    assert result["error_code"] == "slug_invalid"


@pytest.mark.asyncio
async def test_top_n_out_of_range_error(driver: AsyncDriver) -> None:
    result = await find_owners(driver, file_path="x.py", project="gimle", top_n=0)
    assert result["ok"] is False
    assert result["error_code"] == "top_n_out_of_range"


@pytest.mark.asyncio
async def test_project_not_registered_error(driver: AsyncDriver) -> None:
    result = await find_owners(driver, file_path="x.py", project="ghost", top_n=5)
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_ownership_not_indexed_yet_error(driver: AsyncDriver) -> None:
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run("MERGE (p:Project {slug: 'gimle'})")
    result = await find_owners(driver, file_path="x.py", project="gimle", top_n=5)
    assert result["ok"] is False
    assert result["error_code"] == "ownership_not_indexed_yet"


@pytest.mark.asyncio
async def test_unknown_file_returns_unknown_file_error(driver: AsyncDriver) -> None:
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: 'gimle'})
            MERGE (c:OwnershipCheckpoint {project_id: 'gimle'})
              SET c.last_head_sha='deadbeef',
                  c.last_completed_at=datetime(),
                  c.run_id='r1',
                  c.updated_at=datetime()
            """
        )
    result = await find_owners(driver, file_path="nope.py", project="gimle", top_n=5)
    assert result["ok"] is False
    assert result["error_code"] == "unknown_file"


@pytest.mark.asyncio
async def test_success_with_owners(driver: AsyncDriver) -> None:
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: 'gimle'})
            MERGE (c:OwnershipCheckpoint {project_id: 'gimle'})
              SET c.last_head_sha='deadbeef',
                  c.last_completed_at=datetime(),
                  c.run_id='r1', c.updated_at=datetime()
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (a:Author {provider: 'git', identity_key: 'a@x.com'})
              SET a.email='a@x.com', a.name='A', a.is_bot=false
            MERGE (b:Author {provider: 'git', identity_key: 'b@x.com'})
              SET b.email='b@x.com', b.name='B', b.is_bot=false
            MERGE (f)-[r1:OWNED_BY]->(a)
              SET r1.source='extractor.code_ownership',
                  r1.weight=0.7, r1.blame_share=0.7, r1.recency_churn_share=0.7,
                  r1.last_touched_at=datetime(),
                  r1.lines_attributed=70, r1.commit_count=7,
                  r1.run_id_provenance='r1', r1.alpha_used=0.5,
                  r1.canonical_via='identity'
            MERGE (f)-[r2:OWNED_BY]->(b)
              SET r2.source='extractor.code_ownership',
                  r2.weight=0.3, r2.blame_share=0.3, r2.recency_churn_share=0.3,
                  r2.last_touched_at=datetime(),
                  r2.lines_attributed=30, r2.commit_count=3,
                  r2.run_id_provenance='r1', r2.alpha_used=0.5,
                  r2.canonical_via='identity'
            MERGE (st:OwnershipFileState {project_id: 'gimle', path: 'a.py'})
              SET st.status='processed', st.no_owners_reason=null,
                  st.last_run_id='r1', st.updated_at=datetime()
            """
        )
    result = await find_owners(driver, file_path="a.py", project="gimle", top_n=5)
    assert result["ok"] is True
    assert len(result["owners"]) == 2
    assert result["owners"][0]["author_email"] == "a@x.com"
    assert result["owners"][0]["weight"] == pytest.approx(0.7)
    assert result["total_authors"] == 2
    assert result["no_owners_reason"] is None


@pytest.mark.asyncio
async def test_success_binary_skipped(driver: AsyncDriver) -> None:
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: 'gimle'})
            MERGE (c:OwnershipCheckpoint {project_id: 'gimle'})
              SET c.last_head_sha='deadbeef',
                  c.last_completed_at=datetime(),
                  c.run_id='r1', c.updated_at=datetime()
            MERGE (f:File {project_id: 'gimle', path: 'b.png'})
            MERGE (st:OwnershipFileState {project_id: 'gimle', path: 'b.png'})
              SET st.status='skipped',
                  st.no_owners_reason='binary_or_skipped',
                  st.last_run_id='r1', st.updated_at=datetime()
            """
        )
    result = await find_owners(driver, file_path="b.png", project="gimle", top_n=5)
    assert result["ok"] is True
    assert result["owners"] == []
    assert result["no_owners_reason"] == "binary_or_skipped"


@pytest.mark.asyncio
async def test_success_file_not_yet_processed(driver: AsyncDriver) -> None:
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: 'gimle'})
            MERGE (c:OwnershipCheckpoint {project_id: 'gimle'})
              SET c.last_head_sha='deadbeef',
                  c.last_completed_at=datetime(),
                  c.run_id='r1', c.updated_at=datetime()
            MERGE (f:File {project_id: 'gimle', path: 'fresh.py'})
            """
        )
    result = await find_owners(driver, file_path="fresh.py", project="gimle", top_n=5)
    assert result["ok"] is True
    assert result["owners"] == []
    assert result["no_owners_reason"] == "file_not_yet_processed"
    assert result["last_run_id"] is None
