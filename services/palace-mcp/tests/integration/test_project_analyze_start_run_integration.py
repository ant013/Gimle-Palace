"""Live-Neo4j integration for the project_analyze start path."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from collections.abc import Iterator
from typing import Any

import pytest
import pytest_asyncio

from palace_mcp.extractors import registry
from palace_mcp.project_analyze import (
    ACTIVE_ANALYSIS_RUN_STATUSES,
    ActiveAnalysisRunExistsError,
    AnalysisRunStatus,
    ProjectAnalysisService,
)


@pytest.fixture(scope="module")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield reuse
        return

    from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]

    with Neo4jContainer("neo4j:5.26.0") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="module")
def neo4j_auth() -> tuple[str, str]:
    return (
        os.environ.get("COMPOSE_NEO4J_USER", "neo4j"),
        os.environ.get("COMPOSE_NEO4J_PASSWORD", "password"),
    )


@pytest_asyncio.fixture
async def live_driver(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> AsyncIterator[Any]:
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        await driver.verify_connectivity()
    except Exception:
        await driver.close()
        pytest.skip("Could not connect to Neo4j — skipping integration tests")
    yield driver
    await driver.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_db(live_driver: Any):  # type: ignore[no-untyped-def]
    async with live_driver.session() as session:
        result = await session.run("MATCH (n) DETACH DELETE n")
        await result.consume()
    yield
    async with live_driver.session() as session:
        result = await session.run("MATCH (n) DETACH DELETE n")
        await result.consume()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_run_persists_lock_and_lease_metadata(
    live_driver: Any,
) -> None:
    service = ProjectAnalysisService(
        driver=live_driver,
        extractor_registry=registry.EXTRACTORS,
        lease_owner="pytest",
        lease_seconds=30,
    )

    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["symbol_index_swift"],
        idempotency_key="integration-start-run",
    )

    assert started.active_run_reused is False
    assert started.run.status == AnalysisRunStatus.RUNNING
    assert started.run.lease_owner == "pytest"
    assert started.run.lease_expires_at is not None

    async with live_driver.session() as session:
        result = await session.run(
            """
            MATCH (l:AnalysisLock {key: $lock_key})
            MATCH (p:Project {slug: $slug})
            MATCH (r:AnalysisRun {run_id: $run_id})
            RETURN
                l.key AS lock_key,
                p.parent_mount AS parent_mount,
                p.relative_path AS relative_path,
                p.language_profile AS language_profile,
                p.name AS name,
                p.tags AS tags,
                r.status AS status,
                r.lease_owner AS lease_owner,
                r.lease_expires_at AS lease_expires_at
            """,
            slug="tron-kit",
            run_id=started.run.run_id,
            lock_key="tron-kit|swift_kit",
        )
        row = await result.single()

    assert row is not None
    assert row["lock_key"] == "tron-kit|swift_kit"
    assert row["parent_mount"] == "hs"
    assert row["relative_path"] == "TronKit.Swift"
    assert row["language_profile"] == "swift_kit"
    assert row["name"] == "tron-kit"
    assert row["tags"] == []
    assert row["status"] == AnalysisRunStatus.RUNNING.value
    assert row["lease_owner"] == "pytest"
    assert row["lease_expires_at"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_same_key_concurrent_start_creates_one_active_run(
    live_driver: Any,
) -> None:
    slug = "same-key-concurrency"
    relative_path = "SameKeyConcurrency.Swift"
    first = ProjectAnalysisService(
        driver=live_driver,
        extractor_registry=registry.EXTRACTORS,
        lease_owner="pytest-a",
        lease_seconds=30,
    )
    second = ProjectAnalysisService(
        driver=live_driver,
        extractor_registry=registry.EXTRACTORS,
        lease_owner="pytest-b",
        lease_seconds=30,
    )

    async def _start(
        service: ProjectAnalysisService,
        *,
        idempotency_key: str,
    ) -> str:
        started = await service.start_run(
            slug=slug,
            parent_mount="hs",
            relative_path=relative_path,
            language_profile="swift_kit",
            extractors=["symbol_index_swift"],
            idempotency_key=idempotency_key,
        )
        return started.run.run_id

    first_result, second_result = await asyncio.gather(
        _start(first, idempotency_key="concurrent-a"),
        _start(second, idempotency_key="concurrent-b"),
        return_exceptions=True,
    )

    results = [first_result, second_result]
    run_ids = [result for result in results if isinstance(result, str)]
    conflicts = [
        result for result in results if isinstance(result, ActiveAnalysisRunExistsError)
    ]

    assert len(run_ids) == 1
    assert len(conflicts) == 1
    assert conflicts[0].run_id == run_ids[0]

    async with live_driver.session() as session:
        result = await session.run(
            """
            MATCH (r:AnalysisRun {lock_key: $lock_key})
            WHERE r.status IN $active_statuses
            RETURN count(r) AS active_runs
            """,
            lock_key=f"{slug}|swift_kit",
            active_statuses=[status.value for status in ACTIVE_ANALYSIS_RUN_STATUSES],
        )
        row = await result.single()

    assert row is not None
    assert row["active_runs"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_different_keys_allow_parallel_starts(
    live_driver: Any,
) -> None:
    first_slug = "parallel-start-one"
    second_slug = "parallel-start-two"
    first = ProjectAnalysisService(
        driver=live_driver,
        extractor_registry=registry.EXTRACTORS,
        lease_owner="pytest-a",
        lease_seconds=30,
    )
    second = ProjectAnalysisService(
        driver=live_driver,
        extractor_registry=registry.EXTRACTORS,
        lease_owner="pytest-b",
        lease_seconds=30,
    )

    async def _start(
        service: ProjectAnalysisService,
        *,
        slug: str,
    ) -> str:
        started = await service.start_run(
            slug=slug,
            parent_mount="hs",
            relative_path=f"{slug}.Swift",
            language_profile="swift_kit",
            extractors=["symbol_index_swift"],
            idempotency_key=f"idem-{slug}",
        )
        return started.run.run_id

    first_run_id, second_run_id = await asyncio.gather(
        _start(first, slug=first_slug),
        _start(second, slug=second_slug),
    )

    assert first_run_id != second_run_id

    async with live_driver.session() as session:
        result = await session.run(
            """
            MATCH (r:AnalysisRun)
            WHERE r.run_id IN $run_ids
            RETURN count(r) AS run_count
            """,
            run_ids=[first_run_id, second_run_id],
        )
        row = await result.single()

    assert row is not None
    assert row["run_count"] == 2
