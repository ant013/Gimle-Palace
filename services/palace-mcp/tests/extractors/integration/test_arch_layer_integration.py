"""Integration tests for arch_layer extractor (GIM-243).

Uses real Neo4j (testcontainers or COMPOSE_NEO4J_URI).
Tests:
  1. Fixture repo writes expected Module/Layer/ArchRule/ArchViolation counts.
  2. Second run is idempotent (zero duplicates).
  3. :DEPENDS_ON edges (owned by dependency_surface) are untouched.
  4. Registry includes arch_layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.arch_layer.neo4j_writer import replace_project_snapshot
from palace_mcp.extractors.arch_layer.models import (
    Module,
    Layer,
    ArchRule,
    ArchViolation,
    ModuleEdge,
)
from palace_mcp.extractors.base import ExtractorRunContext

pytestmark = pytest.mark.integration

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "arch-layer-mini-project"
_PROJECT_ID = "project/arch-layer-test"
_RUN_1 = "run-integ-1"
_RUN_2 = "run-integ-2"


def _make_ctx(run_id: str = _RUN_1) -> ExtractorRunContext:
    import logging

    return ExtractorRunContext(
        project_slug="arch-layer-test",
        group_id=_PROJECT_ID,
        repo_path=_FIXTURE,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


# ---------------------------------------------------------------------------
# Snapshot writer tests (mock-free Neo4j writes)
# ---------------------------------------------------------------------------


async def _count_nodes(driver: AsyncDriver, label: str, project_id: str) -> int:
    async with driver.session() as session:
        result = await session.run(
            f"MATCH (n:{label} {{project_id: $pid}}) RETURN count(n) AS cnt",
            pid=project_id,
        )
        record = await result.single()
        return record["cnt"] if record else 0


async def _count_edges(driver: AsyncDriver, edge_type: str, project_id: str) -> int:
    async with driver.session() as session:
        result = await session.run(
            f"MATCH (a {{project_id: $pid}})-[r:{edge_type}]->(b {{project_id: $pid}}) RETURN count(r) AS cnt",
            pid=project_id,
        )
        record = await result.single()
        return record["cnt"] if record else 0


def _make_fixture_data(run_id: str) -> dict:
    modules = [
        Module(
            project_id=_PROJECT_ID,
            slug="WalletCore",
            name="WalletCore",
            kind="swift_target",
            manifest_path="Package.swift",
            source_root="Sources/WalletCore",
            run_id=run_id,
        ),
        Module(
            project_id=_PROJECT_ID,
            slug="WalletUI",
            name="WalletUI",
            kind="swift_target",
            manifest_path="Package.swift",
            source_root="Sources/WalletUI",
            run_id=run_id,
        ),
    ]
    layers = [
        Layer(
            project_id=_PROJECT_ID,
            name="core",
            rule_source=".palace/architecture-rules.yaml",
            run_id=run_id,
        ),
        Layer(
            project_id=_PROJECT_ID,
            name="ui",
            rule_source=".palace/architecture-rules.yaml",
            run_id=run_id,
        ),
    ]
    rules = [
        ArchRule(
            project_id=_PROJECT_ID,
            rule_id="core_no_ui_import",
            kind="forbidden_dependency",
            severity="high",
            rule_source=".palace/architecture-rules.yaml",
            run_id=run_id,
        ),
    ]
    violations = [
        ArchViolation(
            project_id=_PROJECT_ID,
            kind="forbidden_dependency",
            severity="high",
            src_module="WalletCore",
            dst_module="WalletUI",
            rule_id="core_no_ui_import",
            message="bad",
            evidence="test edge",
            file="Package.swift",
            start_line=0,
            run_id=run_id,
        ),
    ]
    edges = [
        ModuleEdge(
            src_slug="WalletUI",
            dst_slug="WalletCore",
            scope="target_dep",
            declared_in="Package.swift",
            evidence_kind="manifest",
            run_id=run_id,
        ),
    ]
    module_layers = {"WalletCore": "core", "WalletUI": "ui"}
    return dict(
        modules=modules,
        layers=layers,
        rules=rules,
        violations=violations,
        edges=edges,
        module_layers=module_layers,
    )


@pytest.mark.asyncio
async def test_snapshot_writes_expected_nodes(driver: AsyncDriver) -> None:
    data = _make_fixture_data(_RUN_1)
    await replace_project_snapshot(
        driver, project_id=_PROJECT_ID, run_id=_RUN_1, **data
    )

    assert await _count_nodes(driver, "Module", _PROJECT_ID) == 2
    assert await _count_nodes(driver, "Layer", _PROJECT_ID) == 2
    assert await _count_nodes(driver, "ArchRule", _PROJECT_ID) == 1
    assert await _count_nodes(driver, "ArchViolation", _PROJECT_ID) == 1


@pytest.mark.asyncio
async def test_snapshot_idempotent_second_run(driver: AsyncDriver) -> None:
    data1 = _make_fixture_data(_RUN_1)
    data2 = _make_fixture_data(_RUN_2)
    await replace_project_snapshot(
        driver, project_id=_PROJECT_ID, run_id=_RUN_1, **data1
    )
    await replace_project_snapshot(
        driver, project_id=_PROJECT_ID, run_id=_RUN_2, **data2
    )

    # Second run deletes+rewrites — node counts must be the same
    assert await _count_nodes(driver, "Module", _PROJECT_ID) == 2
    assert await _count_nodes(driver, "Layer", _PROJECT_ID) == 2
    assert await _count_nodes(driver, "ArchRule", _PROJECT_ID) == 1
    assert await _count_nodes(driver, "ArchViolation", _PROJECT_ID) == 1


@pytest.mark.asyncio
async def test_depends_on_not_created(driver: AsyncDriver) -> None:
    """arch_layer must never create :DEPENDS_ON edges."""
    data = _make_fixture_data(_RUN_1)
    await replace_project_snapshot(
        driver, project_id=_PROJECT_ID, run_id=_RUN_1, **data
    )

    async with driver.session() as session:
        result = await session.run("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r) AS cnt")
        record = await result.single()
        count = record["cnt"] if record else 0
    assert count == 0


@pytest.mark.asyncio
async def test_module_depends_on_edges_written(driver: AsyncDriver) -> None:
    data = _make_fixture_data(_RUN_1)
    await replace_project_snapshot(
        driver, project_id=_PROJECT_ID, run_id=_RUN_1, **data
    )

    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:Module {project_id: $pid})-[r:MODULE_DEPENDS_ON]->(b:Module) "
            "RETURN count(r) AS cnt",
            pid=_PROJECT_ID,
        )
        record = await result.single()
        cnt = record["cnt"] if record else 0
    assert cnt == 1  # one MODULE_DEPENDS_ON edge in fixture


# ---------------------------------------------------------------------------
# Registry test
# ---------------------------------------------------------------------------


def test_arch_layer_registered() -> None:
    from palace_mcp.extractors.registry import EXTRACTORS

    assert "arch_layer" in EXTRACTORS
    extractor = EXTRACTORS["arch_layer"]
    assert extractor.name == "arch_layer"
    contract = extractor.audit_contract()
    assert contract is not None
    assert contract.template_name == "arch_layer.md"
    assert "$project_id" in contract.query
