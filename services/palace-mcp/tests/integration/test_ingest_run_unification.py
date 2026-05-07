"""Integration tests for IngestRun schema unification + migration (GIM-228, S0.1).

Requires Neo4j (testcontainers or COMPOSE_NEO4J_URI env var).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_ingest_run_unification.py -m integration
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from neo4j import GraphDatabase

pytest_plugins = ("tests.integration.hotspot_wire_support",)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sync_driver(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> GraphDatabase:
    return GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)


def _seed_path_a_row(
    drv: object,
    *,
    run_id: str,
    source: str = "extractor.hotspot",
    group_id: str = "project/gimle",
) -> None:
    """Insert a legacy Path A :IngestRun without extractor_name / project."""
    with drv.session() as sess:  # type: ignore[union-attr]
        sess.run(
            """
            CREATE (r:IngestRun {
                id: $id,
                source: $source,
                group_id: $group_id,
                started_at: datetime()
            })
            """,
            id=run_id,
            source=source,
            group_id=group_id,
        )


def _seed_path_b_row(
    drv: object,
    *,
    run_id: str,
    project: str = "gimle",
    extractor_name: str = "symbol_index_python",
) -> None:
    """Insert a Path B :IngestRun already containing canonical fields."""
    with drv.session() as sess:  # type: ignore[union-attr]
        sess.run(
            """
            MERGE (r:IngestRun {run_id: $run_id})
            ON CREATE SET
                r.project = $project,
                r.extractor_name = $extractor_name,
                r.started_at = datetime()
            """,
            run_id=run_id,
            project=project,
            extractor_name=extractor_name,
        )


def _delete_rows(drv: object, run_ids: list[str]) -> None:
    with drv.session() as sess:  # type: ignore[union-attr]
        sess.run("MATCH (r:IngestRun) WHERE r.id IN $ids OR r.run_id IN $ids DETACH DELETE r", ids=run_ids)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sync_drv(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[object]:
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    yield drv
    drv.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_migration_idempotent(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> None:
    """Migration back-fills Path A rows and is safe to re-run (zero net writes)."""
    from neo4j import AsyncGraphDatabase
    from palace_mcp.migrations.m2026_05_unify_ingest_run import run_migration

    drv = _sync_driver(neo4j_uri, neo4j_auth)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    try:
        _seed_path_a_row(drv, run_id=ids[0], source="extractor.hotspot", group_id="project/gimle")
        _seed_path_a_row(drv, run_id=ids[1], source="extractor.dependency_surface", group_id="project/other")
        _seed_path_a_row(drv, run_id=ids[2], source="extractor.code_ownership", group_id="bundle/uw-ios")

        async_drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
        try:
            migrated = await run_migration(async_drv)
            assert migrated == 3, f"Expected 3 migrated rows, got {migrated}"

            # Verify fields are correct
            with drv.session() as sess:
                for run_id, source, group_id in [
                    (ids[0], "extractor.hotspot", "project/gimle"),
                    (ids[1], "extractor.dependency_surface", "project/other"),
                    (ids[2], "extractor.code_ownership", "bundle/uw-ios"),
                ]:
                    row = sess.run(
                        "MATCH (r:IngestRun {id: $id}) RETURN r.extractor_name AS en, r.project AS p",
                        id=run_id,
                    ).single()
                    assert row is not None
                    expected_name = source.removeprefix("extractor.")
                    expected_project = (
                        group_id.removeprefix("project/") if group_id.startswith("project/") else group_id
                    )
                    assert row["en"] == expected_name, f"extractor_name mismatch for {run_id}"
                    assert row["p"] == expected_project, f"project mismatch for {run_id}"

            # Idempotency: re-run should affect 0 rows
            migrated_again = await run_migration(async_drv)
            assert migrated_again == 0, f"Expected 0 on re-run, got {migrated_again}"
        finally:
            await async_drv.close()
    finally:
        _delete_rows(drv, ids)
        drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_discovery_sees_both_paths(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> None:
    """After migration, querying by extractor_name returns nodes from both paths."""
    from neo4j import AsyncGraphDatabase
    from palace_mcp.migrations.m2026_05_unify_ingest_run import run_migration

    drv = _sync_driver(neo4j_uri, neo4j_auth)
    path_a_id = str(uuid.uuid4())
    path_b_id = str(uuid.uuid4())
    try:
        _seed_path_a_row(drv, run_id=path_a_id, source="extractor.hotspot", group_id="project/gimle")
        _seed_path_b_row(drv, run_id=path_b_id, extractor_name="hotspot", project="gimle")

        async_drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
        try:
            await run_migration(async_drv)

            # Both rows queryable by extractor_name
            async with async_drv.session() as sess:
                result = await sess.run(
                    "MATCH (r:IngestRun) "
                    "WHERE r.extractor_name = 'hotspot' AND r.project = 'gimle' "
                    "RETURN count(r) AS n"
                )
                row = await result.single()
            assert row is not None and row["n"] >= 2, (
                f"Expected >= 2 rows with extractor_name='hotspot', got {row}"
            )
        finally:
            await async_drv.close()
    finally:
        _delete_rows(drv, [path_a_id, path_b_id])
        drv.close()
