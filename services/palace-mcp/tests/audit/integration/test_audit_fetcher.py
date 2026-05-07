"""Integration tests for the generic audit fetcher (S1.5).

Seeds Neo4j with synthetic data and fake extractors each returning a known
AuditContract. Verifies that fetch_audit_data returns one AuditSectionData
per extractor via direct Cypher (no MCP round-trips).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from neo4j import AsyncDriver, AsyncGraphDatabase
import os

from palace_mcp.audit.contracts import AuditContract, AuditSectionData, RunInfo
from palace_mcp.extractors.base import BaseExtractor, ExtractorRunContext, ExtractorStats


# ---------------------------------------------------------------------------
# Neo4j fixture (same pattern as extractors/integration/conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield reuse
        return
    from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]
    with Neo4jContainer("neo4j:5.26.0") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def neo4j_auth() -> tuple[str, str]:
    user = os.environ.get("COMPOSE_NEO4J_USER", "neo4j")
    pw = os.environ.get("COMPOSE_NEO4J_PASSWORD", "password")
    return user, pw


@pytest.fixture
async def driver(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[AsyncDriver]:
    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        yield drv
    finally:
        await drv.close()


@pytest.fixture(autouse=True)
async def clean_db(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


# ---------------------------------------------------------------------------
# Fake extractor with known AuditContract
# ---------------------------------------------------------------------------


class FakeExtractor(BaseExtractor):
    name = "fake_extractor"
    description = "test-only fake extractor"

    def __init__(self, contract: AuditContract) -> None:
        self._contract = contract

    async def run(self, *, graphiti: Any, ctx: Any) -> ExtractorStats:
        return ExtractorStats()

    def audit_contract(self) -> AuditContract:
        return self._contract


# ---------------------------------------------------------------------------
# Synthetic fixture query that reads :FakeNode rows
# ---------------------------------------------------------------------------

_SEED_FAKE_NODE = """
CREATE (:FakeNode {project: $project, name: $name, sev: $sev})
"""

_FAKE_QUERY = """
MATCH (n:FakeNode {project: $project})
RETURN n.name AS name, n.sev AS sev
"""


@pytest.mark.integration
class TestAuditFetcher:
    async def test_fetches_one_section_per_extractor(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        await _seed_fake_nodes(driver, project="p")
        run_info = RunInfo(run_id="r1", extractor_name="fake_extractor", project="p", completed_at=None)
        contract = AuditContract(
            extractor_name="fake_extractor",
            template_name="hotspot.md",  # reuse any valid template
            query=_FAKE_QUERY,
            severity_column="sev",
        )
        registry = {"fake_extractor": FakeExtractor(contract)}
        result = await fetch_audit_data(driver, {"fake_extractor": run_info}, registry)

        assert "fake_extractor" in result
        section = result["fake_extractor"]
        assert isinstance(section, AuditSectionData)
        assert section.extractor_name == "fake_extractor"
        assert len(section.findings) == 2

    async def test_skips_extractor_with_no_contract(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        class NoContractExtractor(BaseExtractor):
            name = "no_contract"
            description = "returns None"

            async def run(self, *, graphiti: Any, ctx: Any) -> ExtractorStats:
                return ExtractorStats()

        run_info = RunInfo(run_id="r2", extractor_name="no_contract", project="p", completed_at=None)
        registry: dict[str, Any] = {"no_contract": NoContractExtractor()}
        result = await fetch_audit_data(driver, {"no_contract": run_info}, registry)
        assert "no_contract" not in result

    async def test_skips_extractor_not_in_registry(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        run_info = RunInfo(run_id="r3", extractor_name="ghost", project="p", completed_at=None)
        result = await fetch_audit_data(driver, {"ghost": run_info}, {})
        assert result == {}

    async def test_findings_carry_run_provenance(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        await _seed_fake_nodes(driver, project="q")
        run_info = RunInfo(run_id="run-xyz", extractor_name="fake_extractor", project="q", completed_at="2026-05-07T10:00:00Z")
        contract = AuditContract(
            extractor_name="fake_extractor",
            template_name="hotspot.md",
            query=_FAKE_QUERY,
            severity_column="sev",
        )
        registry = {"fake_extractor": FakeExtractor(contract)}
        result = await fetch_audit_data(driver, {"fake_extractor": run_info}, registry)

        section = result["fake_extractor"]
        assert section.run_id == "run-xyz"
        assert section.completed_at == "2026-05-07T10:00:00Z"


async def _seed_fake_nodes(driver: AsyncDriver, *, project: str) -> None:
    async with driver.session() as session:
        await session.run(_SEED_FAKE_NODE, project=project, name="node-a", sev="high")
        await session.run(_SEED_FAKE_NODE, project=project, name="node-b", sev="low")
