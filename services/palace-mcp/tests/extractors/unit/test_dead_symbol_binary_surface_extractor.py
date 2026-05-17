"""Unit tests for dead_symbol_binary_surface extractor orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext, ExtractorStats
from palace_mcp.extractors.dead_symbol_binary_surface.correlation import (
    BlockedContractSymbol,
    CorrelationResult,
)
from palace_mcp.extractors.dead_symbol_binary_surface.extractor import (
    DeadSymbolBinarySurfaceExtractor,
)
from palace_mcp.extractors.dead_symbol_binary_surface.models import (
    CandidateState,
    Confidence,
    DeadSymbolCandidate,
    DeadSymbolEvidenceMode,
    DeadSymbolEvidenceSource,
    DeadSymbolKind,
    DeadSymbolLanguage,
)
from palace_mcp.extractors.dead_symbol_binary_surface.neo4j_writer import (
    DeadSymbolWriteSummary,
)
from palace_mcp.extractors.dead_symbol_binary_surface.parsers.periphery import (
    PeripheryFinding,
    PeripheryParseResult,
)
from palace_mcp.extractors.dead_symbol_binary_surface.parsers.reaper import (
    ReaperParseResult,
    ReaperPlatform,
    ReaperSkipReason,
)
from palace_mcp.extractors.foundation.models import (
    Language,
    PublicApiSymbol,
    PublicApiSymbolKind,
    PublicApiVisibility,
    SymbolKind,
    SymbolOccurrenceShadow,
)

_FIXED_NOW = datetime(2026, 5, 5, tzinfo=timezone.utc)


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="dead-symbol-mini",
        group_id="project/test",
        repo_path=repo_path,
        run_id="run-1",
        duration_ms=0,
        logger=MagicMock(),
    )


def _periphery_finding() -> PeripheryFinding:
    return PeripheryFinding(
        tool_symbol_id="s:wallet.balance",
        all_ids=("s:wallet.balance",),
        display_name="Wallet.balance()",
        symbol_key="Wallet.balance()",
        module_name="ProducerKit",
        language=DeadSymbolLanguage.SWIFT,
        kind=DeadSymbolKind.FUNCTION,
        accessibility="internal",
        source_file="Sources/ProducerKit/Wallet.swift",
        source_line=10,
        source_column=5,
        attributes=(),
        modifiers=(),
        hints=("unused",),
        candidate_state=CandidateState.UNUSED_CANDIDATE,
        skip_reason=None,
    )


def _candidate() -> DeadSymbolCandidate:
    return DeadSymbolCandidate(
        id="candidate-1",
        group_id="project/test",
        project="dead-symbol-mini",
        module_name="ProducerKit",
        language=DeadSymbolLanguage.SWIFT,
        commit_sha="commit-1",
        symbol_key="Wallet.balance()",
        display_name="Wallet.balance()",
        kind=DeadSymbolKind.FUNCTION,
        source_file="Sources/ProducerKit/Wallet.swift",
        source_line=10,
        evidence_source=DeadSymbolEvidenceSource.PERIPHERY,
        evidence_mode=DeadSymbolEvidenceMode.STATIC,
        confidence=Confidence.HIGH,
        candidate_state=CandidateState.UNUSED_CANDIDATE,
    )


def _correlation_result() -> CorrelationResult:
    return CorrelationResult(
        candidate=_candidate(),
        binary_surface=None,
        backed_symbol_id=42,
        backed_public_api_symbol_id=None,
        blocked_contract_symbols=(),
    )


def _public_api_symbol() -> PublicApiSymbol:
    return PublicApiSymbol(
        id="public-symbol-1",
        group_id="project/test",
        project="dead-symbol-mini",
        module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha="commit-1",
        fqn="Wallet.balance()",
        display_name="Wallet.balance()",
        kind=PublicApiSymbolKind.FUNCTION,
        visibility=PublicApiVisibility.PUBLIC,
        signature="public func balance() -> Int",
        signature_hash="sig-wallet-balance",
        source_artifact_path=".palace/public-api/swift/ProducerKit.swiftinterface",
        source_line=10,
        symbol_qualified_name="Wallet.balance()",
    )


def _symbol_shadow() -> SymbolOccurrenceShadow:
    return SymbolOccurrenceShadow(
        symbol_id=42,
        symbol_qualified_name="Wallet.balance()",
        language=Language.SWIFT,
        importance=1.0,
        kind=SymbolKind.DEF,
        tier_weight=1.0,
        last_seen_at=_FIXED_NOW,
        group_id="project/test",
    )


def _blocked_contract_symbol() -> BlockedContractSymbol:
    return BlockedContractSymbol(
        public_symbol_id="public-symbol-1",
        contract_snapshot_id="snapshot-1",
        consumer_module_name="ConsumerKit",
        producer_module_name="ProducerKit",
        commit_sha="commit-1",
        use_count=3,
        evidence_paths_sample=("Sources/ConsumerKit/File.swift",),
    )


def _settings(tmp_path: Path) -> MagicMock:
    return MagicMock(
        palace_max_occurrences_total=1000,
        dead_symbol_periphery_report_path=str(
            tmp_path / "periphery" / "periphery-3.7.4-swiftpm.json"
        ),
        dead_symbol_periphery_contract_path=str(
            tmp_path / "periphery" / "contract.json"
        ),
        dead_symbol_skiplist_path=str(
            tmp_path / ".palace" / "dead-symbol-skiplist.yaml"
        ),
        dead_symbol_codeql_report_path=str(tmp_path / "codeql" / "results.sarif"),
    )


def _write_periphery_fixture(tmp_path: Path) -> None:
    periphery_dir = tmp_path / "periphery"
    periphery_dir.mkdir(parents=True)
    (periphery_dir / "periphery-3.7.4-swiftpm.json").write_text("[]", encoding="utf-8")
    (periphery_dir / "contract.json").write_text(
        json.dumps(
            {
                "tool_name": "Periphery",
                "tool_version": "3.7.4",
                "output_format": "json",
                "tool_output_schema_version": "periphery-json-3.7.4",
                "required_result_keys": [
                    "accessibility",
                    "attributes",
                    "hints",
                    "ids",
                    "kind",
                    "location",
                    "modifiers",
                    "modules",
                    "name",
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _mock_correlation_inputs() -> object:
    with patch(
        "palace_mcp.extractors.dead_symbol_binary_surface.extractor._load_correlation_inputs",
        new=AsyncMock(return_value=((), (), ())),
    ) as mocked:
        yield mocked


@pytest.mark.asyncio
async def test_extractor_periphery_only_happy_path(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            return_value=PeripheryParseResult(
                findings=(_periphery_finding(),), parser_warnings=()
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.correlate_finding",
            return_value=_correlation_result(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            new=AsyncMock(
                return_value=DeadSymbolWriteSummary(
                    nodes_created=1,
                    relationships_created=2,
                    properties_set=0,
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget"
        ),
    ):
        extractor = DeadSymbolBinarySurfaceExtractor()
        stats = await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(tmp_path))

    assert isinstance(stats, ExtractorStats)
    assert stats.nodes_written == 1
    assert stats.edges_written == 2


@pytest.mark.asyncio
async def test_extractor_missing_periphery_file_raises_error(tmp_path: Path) -> None:
    from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
    ):
        with pytest.raises(ExtractorError) as exc_info:
            await DeadSymbolBinarySurfaceExtractor().run(
                graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
            )

    assert exc_info.value.error_code == ExtractorErrorCode.PERIPHERY_FIXTURES_MISSING


@pytest.mark.asyncio
async def test_extractor_passes_loaded_graph_facts_to_correlation(
    tmp_path: Path,
) -> None:
    _write_periphery_fixture(tmp_path)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)
    correlate_mock = MagicMock(return_value=_correlation_result())

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            return_value=PeripheryParseResult(
                findings=(_periphery_finding(),), parser_warnings=()
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._load_correlation_inputs",
            new=AsyncMock(
                return_value=(
                    (_public_api_symbol(),),
                    (_symbol_shadow(),),
                    (_blocked_contract_symbol(),),
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.correlate_finding",
            correlate_mock,
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            new=AsyncMock(
                return_value=DeadSymbolWriteSummary(
                    nodes_created=1,
                    relationships_created=2,
                    properties_set=0,
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget"
        ),
    ):
        await DeadSymbolBinarySurfaceExtractor().run(
            graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
        )

    kwargs = correlate_mock.call_args.kwargs
    assert kwargs["public_api_symbols"] == (_public_api_symbol(),)
    assert kwargs["symbol_shadows"] == (_symbol_shadow(),)
    assert kwargs["blocked_contract_symbols"] == (_blocked_contract_symbol(),)


@pytest.mark.asyncio
async def test_extractor_reaper_unavailable_does_not_fail(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            return_value=PeripheryParseResult(findings=(), parser_warnings=()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            new=AsyncMock(return_value=DeadSymbolWriteSummary()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget"
        ),
    ):
        stats = await DeadSymbolBinarySurfaceExtractor().run(
            graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
        )

    assert stats == ExtractorStats()


@pytest.mark.asyncio
async def test_extractor_codeql_unavailable_does_not_fail(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            return_value=PeripheryParseResult(findings=(), parser_warnings=()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            new=AsyncMock(return_value=DeadSymbolWriteSummary()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget"
        ),
    ):
        stats = await DeadSymbolBinarySurfaceExtractor().run(
            graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
        )

    assert stats == ExtractorStats()


@pytest.mark.asyncio
async def test_extractor_loads_dead_symbol_skiplist(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    skiplist_path = tmp_path / ".palace" / "dead-symbol-skiplist.yaml"
    skiplist_path.parent.mkdir(parents=True)
    skiplist_path.write_text(
        "rules:\n"
        '  - path_glob: "**/Generated/*.swift"\n'
        "    skip_reason: generated_code\n",
        encoding="utf-8",
    )
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)
    parse_mock = MagicMock(
        return_value=PeripheryParseResult(findings=(), parser_warnings=())
    )

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            parse_mock,
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            new=AsyncMock(return_value=DeadSymbolWriteSummary()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget"
        ),
    ):
        await DeadSymbolBinarySurfaceExtractor().run(
            graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
        )

    skip_rules = parse_mock.call_args.kwargs["skip_rules"]
    assert len(skip_rules) == 1
    assert skip_rules[0].path_glob == "**/Generated/*.swift"


@pytest.mark.asyncio
async def test_extractor_rejects_malformed_skiplist(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    skiplist_path = tmp_path / ".palace" / "dead-symbol-skiplist.yaml"
    skiplist_path.parent.mkdir(parents=True)
    skiplist_path.write_text("rules:\n  - not-valid\n", encoding="utf-8")
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
    ):
        with pytest.raises(ValueError, match="skiplist"):
            await DeadSymbolBinarySurfaceExtractor().run(
                graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
            )


@pytest.mark.asyncio
async def test_extractor_stats_align_with_writer_result_summary(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            return_value=PeripheryParseResult(findings=(), parser_warnings=()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            new=AsyncMock(
                return_value=DeadSymbolWriteSummary(
                    nodes_created=3,
                    relationships_created=4,
                    properties_set=0,
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget"
        ),
    ):
        stats = await DeadSymbolBinarySurfaceExtractor().run(
            graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
        )

    assert stats == ExtractorStats(nodes_written=3, edges_written=4)


@pytest.mark.asyncio
async def test_extractor_respects_check_phase_budget(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)
    phase_budget = MagicMock()

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            return_value=PeripheryParseResult(findings=(), parser_warnings=()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            new=AsyncMock(return_value=DeadSymbolWriteSummary()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget",
            phase_budget,
        ),
    ):
        await DeadSymbolBinarySurfaceExtractor().run(
            graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
        )

    assert phase_budget.call_count == 3


@pytest.mark.asyncio
async def test_extractor_respects_check_resume_budget(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)
    resume_budget = MagicMock()

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            return_value=PeripheryParseResult(findings=(), parser_warnings=()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            new=AsyncMock(return_value=DeadSymbolWriteSummary()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value="budget_exceeded"),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget",
            resume_budget,
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget"
        ),
    ):
        await DeadSymbolBinarySurfaceExtractor().run(
            graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
        )

    resume_budget.assert_called_once_with(previous_error_code="budget_exceeded")


@pytest.mark.asyncio
async def test_run_pipeline_raises_when_report_missing(tmp_path: Path) -> None:
    """_run_pipeline raises ExtractorError(PERIPHERY_FIXTURES_MISSING) when report absent."""
    from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

    contract_dir = tmp_path / "periphery"
    contract_dir.mkdir(parents=True)
    (contract_dir / "contract.json").write_text("{}", encoding="utf-8")
    # report file deliberately absent

    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
    ):
        with pytest.raises(ExtractorError) as exc_info:
            await DeadSymbolBinarySurfaceExtractor().run(
                graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
            )

    assert exc_info.value.error_code == ExtractorErrorCode.PERIPHERY_FIXTURES_MISSING


@pytest.mark.asyncio
async def test_run_pipeline_raises_when_contract_missing(tmp_path: Path) -> None:
    """_run_pipeline raises ExtractorError(PERIPHERY_FIXTURES_MISSING) when contract absent."""
    from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

    report_dir = tmp_path / "periphery"
    report_dir.mkdir(parents=True)
    (report_dir / "periphery-3.7.4-swiftpm.json").write_text("[]", encoding="utf-8")
    # contract file deliberately absent

    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
    ):
        with pytest.raises(ExtractorError) as exc_info:
            await DeadSymbolBinarySurfaceExtractor().run(
                graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
            )

    assert exc_info.value.error_code == ExtractorErrorCode.PERIPHERY_FIXTURES_MISSING


@pytest.mark.asyncio
async def test_run_pipeline_raises_when_both_missing(tmp_path: Path) -> None:
    """_run_pipeline raises ExtractorError(PERIPHERY_FIXTURES_MISSING) when both absent."""
    from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

    # neither periphery file exists (tmp_path is empty)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
    ):
        with pytest.raises(ExtractorError) as exc_info:
            await DeadSymbolBinarySurfaceExtractor().run(
                graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
            )

    assert exc_info.value.error_code == ExtractorErrorCode.PERIPHERY_FIXTURES_MISSING


@pytest.mark.asyncio
async def test_run_error_handler_propagates_extractor_error_code(tmp_path: Path) -> None:
    """finalize_ingest_run receives the error_code from ExtractorError, not the hardcoded fallback."""
    from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)
    finalize_mock = AsyncMock()

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            finalize_mock,
        ),
        patch.object(
            DeadSymbolBinarySurfaceExtractor,
            "_run_pipeline",
            new=AsyncMock(
                side_effect=ExtractorError(
                    error_code=ExtractorErrorCode.PERIPHERY_FIXTURES_MISSING,
                    message="periphery fixture not found: /repo/periphery/periphery-3.7.4-swiftpm.json",
                    recoverable=False,
                    action="manual_cleanup",
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
    ):
        with pytest.raises(ExtractorError):
            await DeadSymbolBinarySurfaceExtractor().run(
                graphiti=MagicMock(), ctx=_make_ctx(tmp_path)
            )

    finalize_call_kwargs = finalize_mock.call_args_list[-1].kwargs
    assert finalize_call_kwargs["success"] is False
    assert finalize_call_kwargs["error_code"] == "periphery_fixtures_missing"


@pytest.mark.asyncio
async def test_extractor_concurrent_runs_are_idempotent(tmp_path: Path) -> None:
    _write_periphery_fixture(tmp_path)
    fake_driver = MagicMock()
    fake_settings = _settings(tmp_path)
    writer = AsyncMock(
        side_effect=[
            DeadSymbolWriteSummary(
                nodes_created=1, relationships_created=2, properties_set=0
            ),
            DeadSymbolWriteSummary(
                nodes_created=0, relationships_created=0, properties_set=0
            ),
        ]
    )

    common_patches = (
        patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_checkpoint",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_periphery_fixture",
            return_value=PeripheryParseResult(findings=(), parser_warnings=()),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.parse_reaper_report",
            return_value=ReaperParseResult(
                platform=ReaperPlatform.IOS,
                skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_resume_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.check_phase_budget"
        ),
        patch(
            "palace_mcp.extractors.dead_symbol_binary_surface.extractor.write_dead_symbol_graph",
            writer,
        ),
    )

    with (
        common_patches[0],
        common_patches[1],
        common_patches[2],
        common_patches[3],
        common_patches[4],
        common_patches[5],
        common_patches[6],
        common_patches[7],
        common_patches[8],
        common_patches[9],
        common_patches[10],
        common_patches[11],
    ):
        extractor = DeadSymbolBinarySurfaceExtractor()
        first = await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(tmp_path))
        second = await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(tmp_path))

    assert first == ExtractorStats(nodes_written=1, edges_written=2)
    assert second == ExtractorStats()
