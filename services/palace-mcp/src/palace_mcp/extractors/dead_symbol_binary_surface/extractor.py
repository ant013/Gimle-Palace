"""Extractor orchestrator for dead_symbol_binary_surface."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

from graphiti_core import Graphiti
from neo4j import AsyncDriver

from palace_mcp.config import Settings
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.dead_symbol_binary_surface.correlation import (
    BlockedContractSymbol,
    correlate_finding,
)
from palace_mcp.extractors.foundation.models import (
    PublicApiSymbol,
    SymbolOccurrenceShadow,
)
from palace_mcp.extractors.dead_symbol_binary_surface.neo4j_writer import (
    write_dead_symbol_graph,
)
from palace_mcp.extractors.dead_symbol_binary_surface.parsers.periphery import (
    PeripheryFinding,
    PeripherySkipRule,
    parse_periphery_fixture,
)
from palace_mcp.extractors.dead_symbol_binary_surface.parsers.reaper import (
    ReaperPlatform,
    parse_reaper_report,
)
from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run,
    finalize_ingest_run,
    write_checkpoint,
)
from palace_mcp.extractors.foundation.circuit_breaker import (
    check_phase_budget,
    check_resume_budget,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.schema import ensure_custom_schema

_LOAD_PUBLIC_API_SYMBOLS = """
MATCH (symbol:PublicApiSymbol {project: $project, commit_sha: $commit_sha})
RETURN symbol {.*} AS symbol_props
ORDER BY symbol.id
"""

_LOAD_SYMBOL_SHADOWS = """
MATCH (shadow:SymbolOccurrenceShadow {group_id: $group_id, language: $language})
RETURN shadow {.*} AS shadow_props
ORDER BY shadow.symbol_id, shadow.symbol_qualified_name
"""

_LOAD_BLOCKED_CONTRACT_SYMBOLS = """
MATCH (snapshot:ModuleContractSnapshot {project: $project, commit_sha: $commit_sha})
      -[rel:CONSUMES_PUBLIC_SYMBOL]->
      (symbol:PublicApiSymbol {project: $project, commit_sha: $commit_sha})
RETURN symbol.id AS public_symbol_id, properties(rel) AS edge_props
ORDER BY symbol.id, edge_props.contract_snapshot_id
"""


class DeadSymbolBinarySurfaceExtractor(BaseExtractor):
    """Orchestrate parser, correlation, and writer phases."""

    name: ClassVar[str] = "dead_symbol_binary_surface"
    description: ClassVar[str] = (
        "Ingest dead-symbol candidates and binary-surface retention facts from "
        "pre-generated Periphery fixtures with Reaper no-op handling."
    )

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        return AuditContract(
            extractor_name="dead_symbol_binary_surface",
            template_name="dead_symbol_binary_surface.md",
            query="""
MATCH (c:DeadSymbolCandidate {project: $project})
RETURN c.id AS id,
       c.display_name AS display_name,
       c.kind AS kind,
       c.module_name AS module_name,
       c.language AS language,
       c.candidate_state AS candidate_state,
       c.confidence AS confidence,
       c.source_file AS source_file,
       c.source_line AS source_line,
       c.commit_sha AS commit_sha,
       c.evidence_source AS evidence_source
ORDER BY c.module_name, c.display_name
LIMIT 100
""".strip(),
            severity_column="candidate_state",
            severity_mapper=lambda v: (
                Severity.HIGH
                if v == "CONFIRMED_DEAD"
                else Severity.MEDIUM
                if v == "UNUSED_CANDIDATE"
                else Severity.INFORMATIONAL
            ),
        )

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        del graphiti
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()

        if driver is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available — call set_driver() before run_extractor",
                recoverable=False,
                action="retry",
            )
        if settings is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Settings not available — call set_settings() before run_extractor",
                recoverable=False,
                action="retry",
            )

        previous_error = await _get_previous_error_code(driver, ctx.project_slug)
        check_resume_budget(previous_error_code=previous_error)

        await ensure_custom_schema(driver)
        await create_ingest_run(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            extractor_name=self.name,
        )

        try:
            rows = await self._run_pipeline(driver=driver, settings=settings, ctx=ctx)
        except Exception:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code=ExtractorErrorCode.NEO4J_SHADOW_WRITE_FAILED.value,
            )
            raise

        await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
        return rows

    async def _run_pipeline(
        self, *, driver: AsyncDriver, settings: Settings, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        commit_sha = _read_head_sha(ctx.repo_path)
        skip_rules = _load_dead_symbol_skiplist(
            _dead_symbol_skiplist_path(settings, repo_path=ctx.repo_path)
        )
        total_nodes = 0
        total_edges = 0

        check_phase_budget(
            nodes_written_so_far=total_nodes,
            max_occurrences_total=settings.palace_max_occurrences_total,
            phase="phase1_defs",
        )
        periphery_findings = self._load_periphery_findings(
            settings=settings,
            repo_path=ctx.repo_path,
            skip_rules=skip_rules,
        )
        await write_checkpoint(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            phase="phase1_defs",
            expected_doc_count=len(periphery_findings),
        )

        check_phase_budget(
            nodes_written_so_far=total_nodes,
            max_occurrences_total=settings.palace_max_occurrences_total,
            phase="phase2_user_uses",
        )
        parse_reaper_report(platform=ReaperPlatform.IOS, report_path=None)
        parse_reaper_report(platform=ReaperPlatform.ANDROID, report_path=None)
        (
            public_api_symbols,
            symbol_shadows,
            blocked_contract_symbols,
        ) = await _load_correlation_inputs(
            driver=driver,
            project=ctx.project_slug,
            group_id=ctx.group_id,
            commit_sha=commit_sha,
            language="swift",
        )
        correlated_rows = tuple(
            correlate_finding(
                finding=finding,
                group_id=ctx.group_id,
                project=ctx.project_slug,
                commit_sha=commit_sha,
                public_api_symbols=public_api_symbols,
                symbol_shadows=symbol_shadows,
                blocked_contract_symbols=blocked_contract_symbols,
            )
            for finding in periphery_findings
        )
        await write_checkpoint(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            phase="phase2_user_uses",
            expected_doc_count=len(correlated_rows),
        )

        check_phase_budget(
            nodes_written_so_far=total_nodes,
            max_occurrences_total=settings.palace_max_occurrences_total,
            phase="phase3_vendor_uses",
        )
        write_summary = await write_dead_symbol_graph(
            driver=driver, rows=correlated_rows
        )
        total_nodes += write_summary.nodes_created
        total_edges += write_summary.relationships_created
        await write_checkpoint(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            phase="phase3_vendor_uses",
            expected_doc_count=(
                len(correlated_rows)
                + write_summary.nodes_created
                + write_summary.relationships_created
            ),
        )
        return ExtractorStats(nodes_written=total_nodes, edges_written=total_edges)

    def _load_periphery_findings(
        self,
        *,
        settings: Settings,
        repo_path: Path,
        skip_rules: tuple[PeripherySkipRule, ...],
    ) -> tuple[PeripheryFinding, ...]:
        report_path = _dead_symbol_periphery_report_path(settings, repo_path=repo_path)
        contract_path = _dead_symbol_periphery_contract_path(
            settings, repo_path=repo_path
        )
        if not report_path.exists() or not contract_path.exists():
            return ()
        result = parse_periphery_fixture(
            report_path=report_path,
            contract_path=contract_path,
            skip_rules=skip_rules,
        )
        return result.findings


def _load_dead_symbol_skiplist(path: Path) -> tuple[PeripherySkipRule, ...]:
    """Parse a tiny YAML subset for `.palace/dead-symbol-skiplist.yaml`."""

    if not path.exists():
        return ()

    rules: list[PeripherySkipRule] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line == "rules:":
            continue
        if line.startswith("- "):
            if current is not None:
                rules.append(_rule_from_mapping(current))
            current = {}
            line = line[2:]
            if line:
                key, value = _split_yaml_pair(line)
                current[key] = value
            continue
        if current is None:
            raise ValueError("skiplist must declare rules as a list of mappings")
        key, value = _split_yaml_pair(line)
        current[key] = value

    if current is not None:
        rules.append(_rule_from_mapping(current))
    return tuple(rules)


def _rule_from_mapping(mapping: dict[str, str]) -> PeripherySkipRule:
    try:
        return PeripherySkipRule(
            path_glob=mapping.get("path_glob"),
            attribute_contains=mapping.get("attribute_contains"),
            skip_reason=mapping["skip_reason"],
        )
    except Exception as exc:  # pragma: no cover - normalized in ValueError below
        raise ValueError(f"skiplist rule is invalid: {mapping!r}") from exc


def _split_yaml_pair(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"skiplist line is invalid: {line!r}")
    key, value = line.split(":", 1)
    cleaned = value.strip().strip('"').strip("'")
    return key.strip(), cleaned


def _dead_symbol_skiplist_path(settings: Settings, *, repo_path: Path) -> Path:
    configured = getattr(settings, "dead_symbol_skiplist_path", "")
    if isinstance(configured, str) and configured:
        return Path(configured)
    return repo_path / ".palace" / "dead-symbol-skiplist.yaml"


def _dead_symbol_periphery_report_path(settings: Settings, *, repo_path: Path) -> Path:
    configured = getattr(settings, "dead_symbol_periphery_report_path", "")
    if isinstance(configured, str) and configured:
        return Path(configured)
    return repo_path / "periphery" / "periphery-3.7.4-swiftpm.json"


def _dead_symbol_periphery_contract_path(
    settings: Settings, *, repo_path: Path
) -> Path:
    configured = getattr(settings, "dead_symbol_periphery_contract_path", "")
    if isinstance(configured, str) and configured:
        return Path(configured)
    return repo_path / "periphery" / "contract.json"


async def _get_previous_error_code(driver: AsyncDriver, project: str) -> str | None:
    query = """
    MATCH (r:IngestRun {project: $project, extractor_name: 'dead_symbol_binary_surface'})
    WHERE r.success = false
    RETURN r.error_code AS error_code
    ORDER BY r.started_at DESC
    LIMIT 1
    """
    async with driver.session() as session:
        result = await session.run(query, project=project)
        record = await result.single()
        return None if record is None else record["error_code"]


async def _load_correlation_inputs(
    *,
    driver: AsyncDriver,
    project: str,
    group_id: str,
    commit_sha: str,
    language: str,
) -> tuple[
    tuple[PublicApiSymbol, ...],
    tuple[SymbolOccurrenceShadow, ...],
    tuple[BlockedContractSymbol, ...],
]:
    async with driver.session() as session:
        public_result = await session.run(
            _LOAD_PUBLIC_API_SYMBOLS, project=project, commit_sha=commit_sha
        )
        public_rows = await public_result.data()

        shadow_result = await session.run(
            _LOAD_SYMBOL_SHADOWS, group_id=group_id, language=language
        )
        shadow_rows = await shadow_result.data()

        blocker_result = await session.run(
            _LOAD_BLOCKED_CONTRACT_SYMBOLS, project=project, commit_sha=commit_sha
        )
        blocker_rows = await blocker_result.data()

    return (
        tuple(
            PublicApiSymbol.model_validate(row["symbol_props"]) for row in public_rows
        ),
        tuple(
            SymbolOccurrenceShadow.model_validate(row["shadow_props"])
            for row in shadow_rows
        ),
        tuple(_blocked_contract_symbol_from_row(row) for row in blocker_rows),
    )


def _blocked_contract_symbol_from_row(row: dict[str, object]) -> BlockedContractSymbol:
    raw_props = row["edge_props"]
    if not isinstance(raw_props, dict):
        raise ValueError("contract blocker edge_props must be a dict")
    evidence_paths_sample = raw_props.get("evidence_paths_sample", [])
    if not isinstance(evidence_paths_sample, list):
        raise ValueError("contract blocker evidence_paths_sample must be a list")
    return BlockedContractSymbol(
        public_symbol_id=str(row["public_symbol_id"]),
        contract_snapshot_id=str(raw_props["contract_snapshot_id"]),
        consumer_module_name=str(raw_props["consumer_module_name"]),
        producer_module_name=str(raw_props["producer_module_name"]),
        commit_sha=str(raw_props["commit_sha"]),
        use_count=int(raw_props["use_count"]),
        evidence_paths_sample=tuple(str(item) for item in evidence_paths_sample),
    )


def _read_head_sha(repo_path: Path) -> str:
    git_dir = repo_path / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "unknown"
    if not head.startswith("ref: "):
        return head[:40]
    ref_name = head.removeprefix("ref: ").strip()
    try:
        return (git_dir / ref_name).read_text(encoding="utf-8").strip()[:40]
    except FileNotFoundError:
        return "unknown"
