"""Live-Neo4j integration for the project_analyze start path."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from collections.abc import Iterator
from pathlib import Path
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
from tests.integration.neo4j_runtime_support import ensure_reachable_neo4j_uri


def _colima_docker_host() -> str | None:
    if os.environ.get("DOCKER_HOST"):
        return None

    socket_path = Path.home() / ".colima" / "default" / "docker.sock"
    if not socket_path.exists():
        return None

    try:
        result = subprocess.run(
            ["docker", "context", "show"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    if result.stdout.strip() != "colima":
        return None

    return f"unix://{socket_path}"


@pytest.fixture(scope="module")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield ensure_reachable_neo4j_uri(reuse)
        return

    from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]

    fallback_docker_host = _colima_docker_host()
    original_docker_host = os.environ.get("DOCKER_HOST")
    original_ryuk_disabled = os.environ.get("TESTCONTAINERS_RYUK_DISABLED")
    if fallback_docker_host is not None:
        os.environ["DOCKER_HOST"] = fallback_docker_host
        os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"

    try:
        with Neo4jContainer("neo4j:5.26.0") as container:
            yield container.get_connection_url()
    finally:
        if fallback_docker_host is not None:
            if original_docker_host is None:
                os.environ.pop("DOCKER_HOST", None)
            else:
                os.environ["DOCKER_HOST"] = original_docker_host
            if original_ryuk_disabled is None:
                os.environ.pop("TESTCONTAINERS_RYUK_DISABLED", None)
            else:
                os.environ["TESTCONTAINERS_RYUK_DISABLED"] = original_ryuk_disabled


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
    last_error: Exception | None = None
    try:
        for _attempt in range(10):
            try:
                await driver.verify_connectivity()
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(1)
            else:
                break
        else:
            message = "Could not connect to Neo4j — skipping integration tests"
            if last_error is not None:
                message = f"{message}: {last_error}"
            await driver.close()
            pytest.skip(message)
    except Exception:
        await driver.close()
        raise
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
async def test_start_run_persists_staged_mount_and_bundle_membership(
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
        parent_mount="hs-stage",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        bundle="uw-ios",
        extractors=["symbol_index_swift", "code_ownership"],
        idempotency_key="integration-start-run-staged",
    )

    assert started.active_run_reused is False
    assert started.run.parent_mount == "hs-stage"
    assert started.run.relative_path == "TronKit.Swift"
    assert started.run.bundle == "uw-ios"
    assert started.run.slug == "tron-kit"

    async with live_driver.session() as session:
        result = await session.run(
            """
            MATCH (l:AnalysisLock {key: $lock_key})
            MATCH (p:Project {slug: $slug})
            MATCH (b:Bundle {name: $bundle})-[:CONTAINS]->(p)
            MATCH (r:AnalysisRun {run_id: $run_id})
            OPTIONAL MATCH (r)-[:HAS_ANALYSIS_CHECKPOINT]->(c:AnalysisCheckpoint)
            RETURN
                l.key AS lock_key,
                p.parent_mount AS project_parent_mount,
                p.relative_path AS project_relative_path,
                p.language_profile AS project_language_profile,
                b.name AS bundle_name,
                r.slug AS run_slug,
                r.parent_mount AS run_parent_mount,
                r.relative_path AS run_relative_path,
                r.bundle AS run_bundle,
                collect(c.extractor) AS checkpoint_extractors
            """,
            slug="tron-kit",
            bundle="uw-ios",
            run_id=started.run.run_id,
            lock_key="tron-kit|swift_kit",
        )
        row = await result.single()

    assert row is not None
    assert row["lock_key"] == "tron-kit|swift_kit"
    assert row["project_parent_mount"] == "hs-stage"
    assert row["project_relative_path"] == "TronKit.Swift"
    assert row["project_language_profile"] == "swift_kit"
    assert row["bundle_name"] == "uw-ios"
    assert row["run_slug"] == "tron-kit"
    assert row["run_parent_mount"] == "hs-stage"
    assert row["run_relative_path"] == "TronKit.Swift"
    assert row["run_bundle"] == "uw-ios"
    assert sorted(row["checkpoint_extractors"]) == [
        "code_ownership",
        "symbol_index_swift",
    ]


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
