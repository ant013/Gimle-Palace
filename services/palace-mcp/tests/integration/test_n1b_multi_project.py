"""Task 12: Integration test — register Medic + multi-project isolation.

Run against a live Neo4j with:
    NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=... uv run pytest tests/integration/ -m integration

Excluded from default CI run.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
import pytest_asyncio


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    return os.environ.get("NEO4J_URI", "bolt://localhost:7687")


@pytest.fixture(scope="module")
def neo4j_password() -> str:
    pw = os.environ.get("NEO4J_PASSWORD", "")
    if not pw:
        pytest.skip("NEO4J_PASSWORD not set — skipping integration tests")
    return pw


@pytest_asyncio.fixture(scope="module")
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_medic_registration_and_isolation(live_driver: Any) -> None:  # type: ignore[no-untyped-def]
    """Register Medic project and verify scoping isolation.

    Invariants checked:
    - Medic :Project node exists with correct group_id after register_project
    - list_projects returns both gimle and medic
    - Lookup with project="medic" returns no Issues (Medic has none)
    - Lookup with project=["gimle","medic"] == project="*" (same item IDs)
    - Lookup with project="does-not-exist" returns error envelope
    """
    from palace_mcp.memory.constraints import ensure_schema
    from palace_mcp.memory.lookup import perform_lookup
    from palace_mcp.memory.project_tools import list_projects, register_project
    from palace_mcp.memory.projects import UnknownProjectError
    from palace_mcp.memory.schema import LookupRequest

    default_group_id = "project/gimle"
    await ensure_schema(live_driver, default_group_id=default_group_id)

    # Register Medic
    info = await register_project(
        live_driver,
        slug="medic",
        name="Medic Healthcare",
        tags=["mobile", "kmp", "healthcare"],
    )
    assert info.slug == "medic"
    assert info.tags == ["mobile", "kmp", "healthcare"]

    # Verify :Project node has correct group_id
    async with live_driver.session() as session:
        row = await (
            await session.run(
                "MATCH (p:Project {slug: 'medic'}) RETURN p.group_id AS g, p.name AS n"
            )
        ).single()
    assert row is not None
    assert row["g"] == "project/medic"
    assert row["n"] == "Medic Healthcare"

    # list_projects includes both
    infos = await list_projects(live_driver)
    slugs = [i.slug for i in infos]
    assert "medic" in slugs
    assert "gimle" in slugs

    # Medic isolation: no Issues for new project
    medic_resp = await perform_lookup(
        live_driver,
        LookupRequest(entity_type="Issue", project="medic", limit=20),
        default_group_id,
    )
    assert medic_resp.items == []

    # Multi-project == star (same IDs)
    multi_resp = await perform_lookup(
        live_driver,
        LookupRequest(entity_type="Issue", project=["gimle", "medic"], limit=100),
        default_group_id,
    )
    star_resp = await perform_lookup(
        live_driver,
        LookupRequest(entity_type="Issue", project="*", limit=100),
        default_group_id,
    )
    assert {i.id for i in multi_resp.items} == {i.id for i in star_resp.items}

    # Unknown project returns UnknownProjectError
    with pytest.raises(UnknownProjectError):
        await perform_lookup(
            live_driver,
            LookupRequest(entity_type="Issue", project="does-not-exist", limit=5),
            default_group_id,
        )
