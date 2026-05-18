"""Integration tests for reactive_dependency_tracer."""

from __future__ import annotations

import logging
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.reactive_dependency_tracer.extractor import (
    ReactiveDependencyTracerExtractor,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "reactive-dependency-swift-mini"
)
PROJECT_SLUG = "reactive-dependency-mini"
GROUP_ID = f"project/{PROJECT_SLUG}"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=PROJECT_SLUG,
        group_id=GROUP_ID,
        repo_path=repo_path,
        run_id="integration-test-run",
        duration_ms=0,
        logger=logging.getLogger("integration"),
    )


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "reactive-repo"
    shutil.copytree(FIXTURE_ROOT, repo)
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text(f"{HEAD_SHA}\n", encoding="utf-8")
    return repo


async def _seed_correlation_targets(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (shadow:SymbolOccurrenceShadow {
                group_id: $group_id,
                symbol_id: $symbol_id,
                symbol_qualified_name: $symbol_qualified_name
            })
            SET shadow.language = $language,
                shadow.importance = 0.7,
                shadow.kind = "class",
                shadow.tier_weight = 0.5,
                shadow.last_seen_at = datetime("2026-05-07T00:00:00Z")
            """,
            group_id=GROUP_ID,
            symbol_id=symbol_id_for("App.CounterView"),
            symbol_qualified_name="App.CounterView",
            language=Language.SWIFT.value,
        )
        await session.run(
            """
            MERGE (symbol:PublicApiSymbol {id: $symbol_id})
            SET symbol.group_id = $group_id,
                symbol.project = $project,
                symbol.module_name = "App",
                symbol.language = $language,
                symbol.commit_sha = $commit_sha,
                symbol.fqn = "App.SessionModel",
                symbol.display_name = "SessionModel",
                symbol.kind = "class",
                symbol.visibility = "public",
                symbol.signature = "public final class SessionModel",
                symbol.signature_hash = "session-model-signature",
                symbol.source_artifact_path = "Sources/App/SessionModel.swift",
                symbol.source_line = 4,
                symbol.is_generated = false,
                symbol.is_bridge_exported = false,
                symbol.symbol_qualified_name = "App.SessionModel",
                symbol.schema_version = 1
            """,
            symbol_id="public-session-model",
            group_id=GROUP_ID,
            project=PROJECT_SLUG,
            language=Language.SWIFT.value,
            commit_sha=HEAD_SHA,
        )


@pytest.mark.integration
async def test_reactive_dependency_tracer_writes_expected_graph(
    driver: AsyncDriver, fixture_repo: Path
) -> None:
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(fixture_repo)
    await _seed_correlation_targets(driver)

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        stats = await extractor.run(graphiti=MagicMock(), ctx=ctx)

    assert stats.nodes_written >= 13
    assert stats.edges_written >= 12

    async with driver.session() as session:
        result = await session.run(
            "MATCH (n:ReactiveComponent {project: $project}) RETURN count(n) AS cnt",
            project=PROJECT_SLUG,
        )
        component_count = await result.single()
        result = await session.run(
            "MATCH (n:ReactiveState {project: $project}) RETURN count(n) AS cnt",
            project=PROJECT_SLUG,
        )
        state_count = await result.single()
        result = await session.run(
            "MATCH (n:ReactiveEffect {project: $project}) RETURN count(n) AS cnt",
            project=PROJECT_SLUG,
        )
        effect_count = await result.single()
        result = await session.run(
            "MATCH (n:ReactiveDiagnostic {project: $project}) RETURN count(n) AS cnt",
            project=PROJECT_SLUG,
        )
        diagnostic_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveComponent {project: $project})
                  -[:DECLARES_STATE]->
                  (:ReactiveState {project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        declares_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveState {project: $project})
                  -[:TRIGGERS_EFFECT]->
                  (:ReactiveEffect {project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        triggers_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveState {project: $project})
                  -[:BINDS_TO]->
                  (:ReactiveState {project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        binds_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveEffect {project: $project})
                  -[:WRITES_STATE]->
                  (:ReactiveState {project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        writes_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveDiagnostic {project: $project})
                  -[:DIAGNOSTIC_FOR]->
                  ({project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        diagnostic_edge_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveComponent {project: $project})
                  -[:CORRELATES_SYMBOL]->
                  (:SymbolOccurrenceShadow {group_id: $group_id})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
            group_id=GROUP_ID,
        )
        correlates_symbol_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveComponent {project: $project})
                  -[:CORRELATES_PUBLIC_API]->
                  (:PublicApiSymbol {project: $project, commit_sha: $commit_sha})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
            commit_sha=HEAD_SHA,
        )
        correlates_public_count = await result.single()
        result = await session.run(
            """
            MATCH (n:ReactiveDiagnostic {
                project: $project,
                diagnostic_code: 'swift_generated_or_vendor_skipped'
            })
            RETURN count(n) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        vendor_skip_count = await result.single()
        result = await session.run(
            """
            MATCH (n:ReactiveDiagnostic {
                project: $project,
                diagnostic_code: 'symbol_correlation_unavailable'
            })
            RETURN count(n) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        correlation_diag_count = await result.single()
        result = await session.run(
            """
            MATCH (n:ReactiveState {project: $project, confidence: 'low'})
            RETURN count(n) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        low_confidence_state_count = await result.single()
        result = await session.run(
            """
            MATCH (n:ReactiveEffect {project: $project, confidence: 'high'})
            RETURN count(n) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        high_confidence_effect_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveEffect {
                project: $project,
                effect_kind: 'task'
            })<-[:TRIGGERS_EFFECT]-(:ReactiveState {project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        lifecycle_trigger_count = await result.single()

    assert component_count is not None and component_count["cnt"] == 3
    assert state_count is not None and state_count["cnt"] == 6
    assert effect_count is not None and effect_count["cnt"] == 4
    assert diagnostic_count is not None and diagnostic_count["cnt"] == 3
    assert declares_count is not None and declares_count["cnt"] == 6
    assert triggers_count is not None and triggers_count["cnt"] == 2
    assert binds_count is not None and binds_count["cnt"] == 1
    assert writes_count is not None and writes_count["cnt"] == 2
    assert diagnostic_edge_count is not None and diagnostic_edge_count["cnt"] == 2
    assert correlates_symbol_count is not None and correlates_symbol_count["cnt"] == 1
    assert correlates_public_count is not None and correlates_public_count["cnt"] == 1
    assert vendor_skip_count is not None and vendor_skip_count["cnt"] == 1
    assert correlation_diag_count is not None and correlation_diag_count["cnt"] == 1
    assert (
        low_confidence_state_count is not None
        and low_confidence_state_count["cnt"] >= 1
    )
    assert (
        high_confidence_effect_count is not None
        and high_confidence_effect_count["cnt"] >= 2
    )
    assert lifecycle_trigger_count is not None and lifecycle_trigger_count["cnt"] == 0


@pytest.mark.integration
async def test_reactive_dependency_tracer_rerun_keeps_graph_counts_stable(
    driver: AsyncDriver, fixture_repo: Path
) -> None:
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(fixture_repo)
    await _seed_correlation_targets(driver)

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        await extractor.run(graphiti=MagicMock(), ctx=ctx)
        await extractor.run(graphiti=MagicMock(), ctx=ctx)

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:ReactiveComponent {project: $project})
            WITH count(c) AS components
            MATCH (s:ReactiveState {project: $project})
            WITH components, count(s) AS states
            MATCH (e:ReactiveEffect {project: $project})
            WITH components, states, count(e) AS effects
            MATCH (d:ReactiveDiagnostic {project: $project})
            WITH components, states, effects, count(d) AS diagnostics
            MATCH (:ReactiveComponent {project: $project})-[:DECLARES_STATE]->(:ReactiveState {project: $project})
            WITH components, states, effects, diagnostics, count(*) AS declares_edges
            MATCH (:ReactiveState {project: $project})-[:TRIGGERS_EFFECT]->(:ReactiveEffect {project: $project})
            WITH components, states, effects, diagnostics, declares_edges, count(*) AS trigger_edges
            MATCH (:ReactiveComponent {project: $project})-[:CORRELATES_SYMBOL]->(:SymbolOccurrenceShadow {group_id: $group_id})
            WITH components, states, effects, diagnostics, declares_edges, trigger_edges, count(*) AS symbol_edges
            MATCH (:ReactiveComponent {project: $project})-[:CORRELATES_PUBLIC_API]->(:PublicApiSymbol {project: $project})
            RETURN components, states, effects, diagnostics, declares_edges, trigger_edges, symbol_edges, count(*) AS public_edges
            """,
            project=PROJECT_SLUG,
            group_id=GROUP_ID,
        )
        record = await result.single()

    assert record is not None
    assert record["components"] == 3
    assert record["states"] == 6
    assert record["effects"] == 4
    assert record["diagnostics"] == 3
    assert record["declares_edges"] == 6
    assert record["trigger_edges"] == 2
    assert record["symbol_edges"] == 1
    assert record["public_edges"] == 1


@pytest.mark.integration
async def test_reactive_dependency_tracer_partial_invalid_file_preserves_valid_batches(
    driver: AsyncDriver, fixture_repo: Path
) -> None:
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(fixture_repo)
    await _seed_correlation_targets(driver)

    fixture_path = fixture_repo / "reactive_facts.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["files"].append(
        {
            "path": "Sources/App/Bad.swift",
            "module_name": "App",
            "parse_status": "ok",
            "components": [
                {
                    "component_ref": "bad_component",
                    "module_name": "App",
                    "component_kind": "swiftui_view",
                    "qualified_name": "App.BadView",
                    "display_name": "BadView",
                    "range": {
                        "start_line": 1,
                        "start_col": 1,
                        "end_line": 2,
                        "end_col": 1,
                    },
                    "resolution_status": "syntax_exact",
                }
            ],
            "states": [],
            "effects": [],
            "edges": [
                {
                    "edge_ref": "bad_edge",
                    "edge_kind": "triggers_effect",
                    "from_ref": "bad_component",
                    "to_ref": "missing_ref",
                    "owner_component_ref": "bad_component",
                    "access_path": "broken",
                    "binding_kind": None,
                    "trigger_expression_kind": "on_change_of",
                    "range": {
                        "start_line": 2,
                        "start_col": 1,
                        "end_line": 2,
                        "end_col": 8,
                    },
                    "confidence_hint": "high",
                    "resolution_status": "syntax_exact",
                }
            ],
            "diagnostics": [],
        }
    )
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        await extractor.run(graphiti=MagicMock(), ctx=ctx)

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:ReactiveComponent {project: $project})
            WITH count(c) AS components
            MATCH (d:ReactiveDiagnostic {
                project: $project,
                file_path: 'Sources/App/Bad.swift'
            })
            RETURN components, count(d) AS bad_file_diagnostics
            """,
            project=PROJECT_SLUG,
        )
        record = await result.single()

    assert record is not None
    assert record["components"] == 3
    assert record["bad_file_diagnostics"] == 1


@pytest.mark.integration
async def test_reactive_dependency_tracer_invalid_rerun_keeps_prior_facts_for_same_file(
    driver: AsyncDriver, fixture_repo: Path
) -> None:
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(fixture_repo)
    await _seed_correlation_targets(driver)

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        await extractor.run(graphiti=MagicMock(), ctx=ctx)

    fixture_path = fixture_repo / "reactive_facts.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    session_model_entry = next(
        file_entry
        for file_entry in payload["files"]
        if file_entry["path"] == "Sources/App/SessionModel.swift"
    )
    session_model_entry["edges"] = [
        {
            "edge_ref": "session_invalid_edge",
            "edge_kind": "triggers_effect",
            "from_ref": "session_ticker",
            "to_ref": "missing_ref",
            "owner_component_ref": "session_component",
            "access_path": "ticker",
            "binding_kind": None,
            "trigger_expression_kind": "publisher_sink",
            "range": {
                "start_line": 9,
                "start_col": 9,
                "end_line": 10,
                "end_col": 18,
            },
            "confidence_hint": "high",
            "resolution_status": "syntax_exact",
        }
    ]
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        await extractor.run(graphiti=MagicMock(), ctx=ctx)

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:ReactiveComponent {
                project: $project,
                file_path: 'Sources/App/SessionModel.swift'
            })
            WITH count(c) AS components
            MATCH (s:ReactiveState {
                project: $project,
                file_path: 'Sources/App/SessionModel.swift'
            })
            WITH components, count(s) AS states
            MATCH (e:ReactiveEffect {
                project: $project,
                file_path: 'Sources/App/SessionModel.swift'
            })
            WITH components, states, count(e) AS effects
            MATCH (d:ReactiveDiagnostic {
                project: $project,
                file_path: 'Sources/App/SessionModel.swift',
                diagnostic_code: 'swift_parse_failed'
            })
            RETURN components, states, effects, count(d) AS parse_failures
            """,
            project=PROJECT_SLUG,
        )
        record = await result.single()

    assert record is not None
    assert record["components"] == 1
    assert record["states"] == 2
    assert record["effects"] == 1
    assert record["parse_failures"] == 1
