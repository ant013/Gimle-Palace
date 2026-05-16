"""Integration tests for the generic audit fetcher (S1.5).

Seeds Neo4j with synthetic data and fake extractors each returning a known
AuditContract. Verifies that fetch_audit_data returns one AuditSectionData
per extractor via direct Cypher (no MCP round-trips).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from neo4j import AsyncDriver, AsyncGraphDatabase
import os

from palace_mcp.audit.contracts import AuditContract, AuditSectionData, RunInfo
from palace_mcp.audit.renderer import render_section
from palace_mcp.extractors.base import BaseExtractor, ExtractorStats
from palace_mcp.extractors.testability_di import TestabilityDiExtractor
from tests.integration.neo4j_runtime_support import ensure_reachable_neo4j_uri

_HAS_NEO4J_RUNTIME = (
    bool(os.environ.get("COMPOSE_NEO4J_URI")) or Path("/var/run/docker.sock").exists()
)


# ---------------------------------------------------------------------------
# Neo4j fixture (same pattern as extractors/integration/conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield ensure_reachable_neo4j_uri(reuse)
        return

    if not Path("/var/run/docker.sock").exists():
        pytest.skip("requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration")

    from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]

    try:
        with Neo4jContainer("neo4j:5.26.0") as container:
            yield container.get_connection_url()
    except Exception as exc:
        pytest.skip(
            f"Could not start Neo4j testcontainer — skipping integration tests: {exc}"
        )


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
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
class TestAuditFetcher:
    async def test_fetches_one_section_per_extractor(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        await _seed_fake_nodes(driver, project="p")
        run_info = RunInfo(
            run_id="r1", extractor_name="fake_extractor", project="p", completed_at=None
        )
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

        run_info = RunInfo(
            run_id="r2", extractor_name="no_contract", project="p", completed_at=None
        )
        registry: dict[str, Any] = {"no_contract": NoContractExtractor()}
        result = await fetch_audit_data(driver, {"no_contract": run_info}, registry)
        assert "no_contract" not in result

    async def test_skips_extractor_not_in_registry(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        run_info = RunInfo(
            run_id="r3", extractor_name="ghost", project="p", completed_at=None
        )
        result = await fetch_audit_data(driver, {"ghost": run_info}, {})
        assert result == {}

    async def test_findings_carry_run_provenance(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        await _seed_fake_nodes(driver, project="q")
        run_info = RunInfo(
            run_id="run-xyz",
            extractor_name="fake_extractor",
            project="q",
            completed_at="2026-05-07T10:00:00Z",
        )
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

    async def test_testability_di_summary_stats_follow_real_fetcher_path(
        self, driver: AsyncDriver
    ) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        async with driver.session() as session:
            await session.run(
                """
                CREATE (:DiPattern {
                  project_id: 'project/wallet',
                  module: 'WalletKit',
                  language: 'swift',
                  style: 'service_locator',
                  framework: null,
                  sample_count: 1,
                  outliers: 0,
                  confidence: 'heuristic',
                  run_id: 'run-1'
                })
                """
            )
            await session.run(
                """
                CREATE (:TestDouble {
                  project_id: 'project/wallet',
                  module: 'WalletKit',
                  language: 'swift',
                  kind: 'fake',
                  target_symbol: 'WalletService',
                  test_file: 'Tests/WalletKitTests/WalletServiceTests.swift',
                  run_id: 'run-1'
                })
                """
            )
            await session.run(
                """
                CREATE (:TestDouble {
                  project_id: 'project/wallet',
                  module: 'WalletKit',
                  language: 'swift',
                  kind: 'spy',
                  target_symbol: 'PriceFeed',
                  test_file: 'Tests/WalletKitTests/WalletServiceTests.swift',
                  run_id: 'run-1'
                })
                """
            )
            await session.run(
                """
                CREATE (:UntestableSite {
                  project_id: 'project/wallet',
                  module: 'WalletKit',
                  language: 'swift',
                  file: 'Sources/WalletKit/WalletManager.swift',
                  start_line: 8,
                  end_line: 8,
                  category: 'service_locator',
                  symbol_referenced: 'ServiceLocator.shared',
                  severity: 'high',
                  message: 'Service locator usage hides dependencies from tests.',
                  run_id: 'run-1'
                })
                """
            )

        run_info = RunInfo(
            run_id="run-1",
            extractor_name="testability_di",
            project="wallet",
            completed_at="2026-05-08T11:00:00Z",
        )
        extractor = TestabilityDiExtractor()
        result = await fetch_audit_data(
            driver,
            {"testability_di": run_info},
            {"testability_di": extractor},
        )

        section = result["testability_di"]
        assert section.summary_stats == {
            "total": 1,
            "patterns": 1,
            "test_doubles": 2,
            "untestable_sites": 1,
        }

        rendered = render_section(
            section,
            extractor.audit_contract().severity_column,
            100,
            severity_mapper=extractor.audit_contract().severity_mapper,
        )
        assert "2 test doubles" in rendered
        assert "1 untestable site" in rendered

    async def test_testability_di_audit_includes_test_double_only_modules(
        self, driver: AsyncDriver
    ) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        async with driver.session() as session:
            await session.run(
                """
                CREATE (:TestDouble {
                  project_id: 'project/wallet',
                  module: 'WalletKitTests',
                  language: 'swift',
                  kind: 'fake',
                  target_symbol: 'WalletService',
                  test_file: 'Tests/WalletKitTests/WalletServiceTests.swift',
                  run_id: 'run-standalone-double'
                })
                """
            )

        run_info = RunInfo(
            run_id="run-standalone-double",
            extractor_name="testability_di",
            project="wallet",
            completed_at="2026-05-08T11:00:00Z",
        )
        extractor = TestabilityDiExtractor()
        result = await fetch_audit_data(
            driver,
            {"testability_di": run_info},
            {"testability_di": extractor},
        )

        section = result["testability_di"]
        assert section.summary_stats == {
            "total": 1,
            "patterns": 0,
            "test_doubles": 1,
            "untestable_sites": 0,
        }
        assert len(section.findings) == 1
        assert section.findings[0]["module"] == "WalletKitTests"
        assert section.findings[0]["style"] is None
        assert section.findings[0]["test_doubles"][0]["kind"] == "fake"

        rendered = render_section(
            section,
            extractor.audit_contract().severity_column,
            100,
            severity_mapper=extractor.audit_contract().severity_mapper,
        )
        assert "STANDALONE_SIGNAL" in rendered
        assert "1 test double" in rendered

    async def test_testability_di_audit_includes_untestable_only_modules(
        self, driver: AsyncDriver
    ) -> None:
        from palace_mcp.audit.fetcher import fetch_audit_data

        async with driver.session() as session:
            await session.run(
                """
                CREATE (:UntestableSite {
                  project_id: 'project/wallet',
                  module: 'WalletKit',
                  language: 'swift',
                  file: 'Sources/WalletKit/WalletManager.swift',
                  start_line: 8,
                  end_line: 8,
                  category: 'service_locator',
                  symbol_referenced: 'ServiceLocator.shared',
                  severity: 'high',
                  message: 'Service locator usage hides dependencies from tests.',
                  run_id: 'run-standalone-site'
                })
                """
            )

        run_info = RunInfo(
            run_id="run-standalone-site",
            extractor_name="testability_di",
            project="wallet",
            completed_at="2026-05-08T11:00:00Z",
        )
        extractor = TestabilityDiExtractor()
        result = await fetch_audit_data(
            driver,
            {"testability_di": run_info},
            {"testability_di": extractor},
        )

        section = result["testability_di"]
        assert section.summary_stats == {
            "total": 1,
            "patterns": 0,
            "test_doubles": 0,
            "untestable_sites": 1,
        }
        assert len(section.findings) == 1
        assert section.findings[0]["module"] == "WalletKit"
        assert section.findings[0]["style"] is None
        assert section.findings[0]["max_severity"] == "high"

        rendered = render_section(
            section,
            extractor.audit_contract().severity_column,
            100,
            severity_mapper=extractor.audit_contract().severity_mapper,
        )
        assert "ServiceLocator.shared" in rendered
        assert "STANDALONE_SIGNAL" in rendered


async def _seed_fake_nodes(driver: AsyncDriver, *, project: str) -> None:
    async with driver.session() as session:
        await session.run(_SEED_FAKE_NODE, project=project, name="node-a", sev="high")
        await session.run(_SEED_FAKE_NODE, project=project, name="node-b", sev="low")
