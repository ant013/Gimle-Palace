"""Live-Neo4j integration for the project_analyze start path."""

from __future__ import annotations

import os
from typing import Any

import pytest
import pytest_asyncio

from palace_mcp.extractors import registry
from palace_mcp.project_analyze import AnalysisRunStatus, ProjectAnalysisService


@pytest.fixture
def neo4j_uri() -> str:
    return os.environ.get("NEO4J_URI", "bolt://localhost:7687")


@pytest.fixture
def neo4j_password() -> str:
    pw = os.environ.get("NEO4J_PASSWORD", "")
    if not pw:
        pytest.skip("NEO4J_PASSWORD not set — skipping integration tests")
    return pw


@pytest_asyncio.fixture
async def live_driver(neo4j_uri: str, neo4j_password: str):  # type: ignore[no-untyped-def]
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password))
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
        await session.run("MATCH (n) DETACH DELETE n")
    yield
    async with live_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_run_preserves_registered_project_metadata(
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
    assert started.run.status == AnalysisRunStatus.PENDING

    async with live_driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Project {slug: $slug})
            RETURN
                p.parent_mount AS parent_mount,
                p.relative_path AS relative_path,
                p.language_profile AS language_profile,
                p.name AS name,
                p.tags AS tags
            """,
            slug="tron-kit",
        )
        row = await result.single()

    assert row is not None
    assert row["parent_mount"] == "hs"
    assert row["relative_path"] == "TronKit.Swift"
    assert row["language_profile"] == "swift_kit"
    assert row["name"] == "tron-kit"
    assert row["tags"] == []
