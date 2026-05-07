"""Cross-module contract extractor built on PublicApiSurface/PublicApiSymbol."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

from graphiti_core import Graphiti
from neo4j import AsyncDriver, AsyncSession
from pydantic import BaseModel

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import (
    Language,
    ModuleContractAffectedSymbol,
    ModuleContractConsumption,
    ModuleContractDelta,
    ModuleContractSnapshot,
    PublicApiSurface,
    PublicApiSymbol,
    PublicApiVisibility,
    SCHEMA_VERSION_CURRENT,
    TantivyOccurrenceMatch,
)
from palace_mcp.extractors.foundation.module_owner import (
    ModuleOwnerResolution,
    resolve_module_owner,
)

_LOAD_PUBLIC_API_ROWS = """
MATCH (surface:PublicApiSurface {project: $project, commit_sha: $commit_sha})
      -[:EXPORTS]->(symbol:PublicApiSymbol {project: $project, commit_sha: $commit_sha})
RETURN surface {.*} AS surface_props, symbol {.*} AS symbol_props
ORDER BY surface.module_name, symbol.fqn
"""

_WRITE_SNAPSHOT = """
MERGE (snapshot:ModuleContractSnapshot {id: $snapshot_id})
SET snapshot += $snapshot_props
WITH snapshot
MATCH (surface:PublicApiSurface {id: $surface_id})
MERGE (snapshot)-[:CONTRACT_PRODUCER_SURFACE]->(surface)
"""

_WRITE_CONSUMPTION = """
MATCH (snapshot:ModuleContractSnapshot {id: $snapshot_id})
MATCH (symbol:PublicApiSymbol {id: $symbol_id})
MERGE (snapshot)-[rel:CONSUMES_PUBLIC_SYMBOL]->(symbol)
SET rel += $edge_props
"""

_WRITE_DELTA = """
MERGE (delta:ModuleContractDelta {id: $delta_id})
SET delta += $delta_props
WITH delta
MATCH (from_snapshot:ModuleContractSnapshot {id: $from_snapshot_id})
MATCH (to_snapshot:ModuleContractSnapshot {id: $to_snapshot_id})
MERGE (delta)-[:DELTA_FROM]->(from_snapshot)
MERGE (delta)-[:DELTA_TO]->(to_snapshot)
"""

_WRITE_DELTA_AFFECTED_SYMBOL = """
MATCH (delta:ModuleContractDelta {id: $delta_id})
MATCH (symbol:PublicApiSymbol {id: $symbol_id})
MERGE (delta)-[rel:AFFECTS_PUBLIC_SYMBOL]->(symbol)
SET rel += $edge_props
"""

_DELTA_REQUESTS_PATH = Path(".palace") / "cross-module-contract" / "delta-requests.json"


@dataclass(frozen=True)
class _SurfaceSymbols:
    surface: PublicApiSurface
    symbols: list[PublicApiSymbol]


@dataclass(frozen=True)
class _PlannedContractSnapshot:
    snapshot: ModuleContractSnapshot
    consumptions: list[ModuleContractConsumption]
    symbols_by_fqn: dict[str, PublicApiSymbol]


@dataclass(frozen=True)
class _PlannedContractDelta:
    delta: ModuleContractDelta
    affected_symbols: list[ModuleContractAffectedSymbol]
    from_snapshot_id: str
    to_snapshot_id: str


@dataclass
class _PairAccumulator:
    consumer_module_name: str
    producer_module_name: str
    language: Language
    commit_sha: str
    consumptions_by_symbol_id: dict[str, ModuleContractConsumption] = field(
        default_factory=dict
    )
    evidence_paths: set[str] = field(default_factory=set)


class _DeltaRequest(BaseModel):
    model_config = {"frozen": True}

    consumer_module_name: str
    producer_module_name: str
    language: Language
    from_commit_sha: str
    to_commit_sha: str
    include_package: bool = False


class CrossModuleContractExtractor(BaseExtractor):
    name: ClassVar[str] = "cross_module_contract"
    description: ClassVar[str] = (
        "Infer exact cross-module public API consumption facts from existing "
        "PublicApiSurface/PublicApiSymbol nodes plus Tantivy occurrence evidence."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT module_contract_snapshot_id_unique IF NOT EXISTS "
        "FOR (n:ModuleContractSnapshot) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT module_contract_delta_id_unique IF NOT EXISTS "
        "FOR (n:ModuleContractDelta) REQUIRE n.id IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX module_contract_snapshot_lookup IF NOT EXISTS "
        "FOR (n:ModuleContractSnapshot) ON (n.project, n.consumer_module_name, n.producer_module_name, n.language, n.commit_sha)",
        "CREATE INDEX module_contract_delta_lookup IF NOT EXISTS "
        "FOR (n:ModuleContractDelta) ON (n.project, n.consumer_module_name, n.producer_module_name, n.language, n.from_commit_sha, n.to_commit_sha)",
    ]

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity
        return AuditContract(
            extractor_name="cross_module_contract",
            template_name="cross_module_contract.md",
            query="""
MATCH (d:ModuleContractDelta {project: $project})
RETURN d.consumer_module_name AS consumer_module,
       d.producer_module_name AS producer_module,
       d.language AS language,
       d.from_commit_sha AS from_commit,
       d.to_commit_sha AS to_commit,
       coalesce(d.removed_consumed_symbol_count, 0) AS removed_count,
       coalesce(d.added_consumed_symbol_count, 0) AS added_count,
       coalesce(d.signature_changed_consumed_symbol_count, 0) AS signature_changed_count,
       coalesce(d.affected_use_count, 0) AS affected_use_count
ORDER BY d.to_commit_sha DESC, d.consumer_module_name
LIMIT 100
""".strip(),
            severity_column="removed_count",
            severity_mapper=lambda v: (
                Severity.HIGH   if v is not None and int(v) > 10 else
                Severity.MEDIUM if v is not None and int(v) > 3  else
                Severity.LOW    if v is not None and int(v) > 0  else
                Severity.INFORMATIONAL
            ),
        )

    def __init__(
        self,
        *,
        include_package: bool = False,
        consumer_phases: tuple[str, ...] = ("phase2_user_uses",),
    ) -> None:
        self._include_package = include_package
        self._consumer_phases = consumer_phases

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

        commit_sha = await asyncio.to_thread(_read_head_sha, ctx.repo_path)
        delta_requests = await _load_delta_requests(repo_path=ctx.repo_path)
        commit_requests = _build_commit_requests(
            current_commit_sha=commit_sha,
            delta_requests=delta_requests,
            default_include_package=self._include_package,
        )
        surfaces_by_commit: dict[str, list[_SurfaceSymbols]] = {}
        for candidate_commit_sha in sorted(commit_requests):
            surfaces_by_commit[candidate_commit_sha] = await _load_public_api_surfaces(
                driver=driver,
                project=ctx.project_slug,
                commit_sha=candidate_commit_sha,
            )

        current_surfaces = surfaces_by_commit[commit_sha]
        if not current_surfaces:
            raise ExtractorError(
                error_code=ExtractorErrorCode.PUBLIC_API_ARTIFACTS_REQUIRED,
                message=(
                    "No PublicApiSurface/PublicApiSymbol rows found for the current "
                    f"commit '{commit_sha}'. Run public_api_surface first."
                ),
                recoverable=False,
                action="manual_cleanup",
            )

        from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

        occurrence_cache: dict[tuple[int, str], list[TantivyOccurrenceMatch]] = {}
        tantivy_path = Path(settings.palace_tantivy_index_path)
        planned: list[_PlannedContractSnapshot] = []
        async with TantivyBridge(
            tantivy_path, heap_size_mb=settings.palace_tantivy_heap_mb
        ) as bridge:
            for candidate_commit_sha, include_package_values in sorted(
                commit_requests.items()
            ):
                for include_package in sorted(include_package_values):
                    planned.extend(
                        await _plan_snapshots_for_commit(
                            bridge=bridge,
                            driver=driver,
                            repo_path=ctx.repo_path,
                            group_id=ctx.group_id,
                            surfaces=surfaces_by_commit[candidate_commit_sha],
                            commit_sha=candidate_commit_sha,
                            include_package=include_package,
                            phases=self._consumer_phases,
                            cache=occurrence_cache,
                        )
                    )

        planned_deltas = _plan_requested_deltas(
            project=ctx.project_slug,
            planned=planned,
            delta_requests=delta_requests,
        )
        stats = await _write_contract_graph(
            driver=driver,
            planned=planned,
            planned_deltas=planned_deltas,
        )
        ctx.logger.info(
            "extractor.cross_module_contract.summary",
            extra={
                "extractor": self.name,
                "project": ctx.project_slug,
                "commit_sha": commit_sha,
                "snapshot_count": len(planned),
                "delta_count": len(planned_deltas),
                "nodes_written": stats.nodes_written,
                "edges_written": stats.edges_written,
            },
        )
        return stats


def _build_commit_requests(
    *,
    current_commit_sha: str,
    delta_requests: list[_DeltaRequest],
    default_include_package: bool,
) -> dict[str, set[bool]]:
    commit_requests: dict[str, set[bool]] = {
        current_commit_sha: {default_include_package}
    }
    for request in delta_requests:
        commit_requests.setdefault(request.from_commit_sha, set()).add(
            request.include_package
        )
        commit_requests.setdefault(request.to_commit_sha, set()).add(
            request.include_package
        )
    return commit_requests


async def _plan_snapshots_for_commit(
    *,
    bridge: object,
    driver: AsyncDriver,
    repo_path: Path,
    group_id: str,
    surfaces: list[_SurfaceSymbols],
    commit_sha: str,
    include_package: bool,
    phases: tuple[str, ...],
    cache: dict[tuple[int, str], list[TantivyOccurrenceMatch]],
) -> list[_PlannedContractSnapshot]:
    planned: list[_PlannedContractSnapshot] = []
    for item in surfaces:
        occurrences_by_symbol = await _load_occurrences_for_surface(
            bridge=bridge,
            symbols=item.symbols,
            commit_sha=commit_sha,
            include_package=include_package,
            phases=phases,
            cache=cache,
        )
        owner_cache = await _resolve_owner_cache(
            driver=driver,
            group_id=group_id,
            repo_path=repo_path,
            occurrences_by_symbol=occurrences_by_symbol,
        )
        planned.extend(
            plan_contract_snapshots(
                surface=item.surface,
                symbols=item.symbols,
                occurrences_by_symbol=occurrences_by_symbol,
                resolve_owner=lambda file_path: owner_cache[file_path],
                include_package=include_package,
            )
        )
    return planned


async def _load_delta_requests(*, repo_path: Path) -> list[_DeltaRequest]:
    request_path = repo_path / _DELTA_REQUESTS_PATH
    if not request_path.exists():
        return []
    try:
        payload = json.loads(await asyncio.to_thread(request_path.read_text, "utf-8"))
        return [_DeltaRequest.model_validate(row) for row in payload]
    except (OSError, ValueError, TypeError) as exc:
        raise ExtractorError(
            error_code=ExtractorErrorCode.PUBLIC_API_PARSE_FAILED,
            message=f"Invalid delta request file: {request_path}",
            recoverable=False,
            action="manual_cleanup",
            context={"path": str(request_path), "error": str(exc)},
        ) from exc


def _plan_requested_deltas(
    *,
    project: str,
    planned: list[_PlannedContractSnapshot],
    delta_requests: list[_DeltaRequest],
) -> list[_PlannedContractDelta]:
    snapshot_lookup = {_snapshot_key(item.snapshot): item for item in planned}
    planned_deltas: dict[str, _PlannedContractDelta] = {}
    for request in delta_requests:
        from_snapshot = snapshot_lookup.get(
            (
                request.consumer_module_name,
                request.producer_module_name,
                request.language.value,
                request.from_commit_sha,
                request.include_package,
            )
        )
        if from_snapshot is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.PUBLIC_API_ARTIFACTS_REQUIRED,
                message=(
                    "Requested delta source snapshot is missing for "
                    f"{request.consumer_module_name} -> {request.producer_module_name} "
                    f"at commit '{request.from_commit_sha}'."
                ),
                recoverable=False,
                action="manual_cleanup",
                context={"project": project},
            )
        to_snapshot = snapshot_lookup.get(
            (
                request.consumer_module_name,
                request.producer_module_name,
                request.language.value,
                request.to_commit_sha,
                request.include_package,
            )
        )
        if to_snapshot is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.PUBLIC_API_ARTIFACTS_REQUIRED,
                message=(
                    "Requested delta target snapshot is missing for "
                    f"{request.consumer_module_name} -> {request.producer_module_name} "
                    f"at commit '{request.to_commit_sha}'."
                ),
                recoverable=False,
                action="manual_cleanup",
                context={"project": project},
            )

        delta, affected_symbols = build_contract_delta(
            from_snapshot=from_snapshot.snapshot,
            to_snapshot=to_snapshot.snapshot,
            from_symbols=from_snapshot.symbols_by_fqn,
            to_symbols=to_snapshot.symbols_by_fqn,
            from_consumptions=from_snapshot.consumptions,
            to_consumptions=to_snapshot.consumptions,
        )
        planned_deltas[delta.id] = _PlannedContractDelta(
            delta=delta,
            affected_symbols=affected_symbols,
            from_snapshot_id=from_snapshot.snapshot.id,
            to_snapshot_id=to_snapshot.snapshot.id,
        )
    return [planned_deltas[key] for key in sorted(planned_deltas)]


def plan_contract_snapshots(
    *,
    surface: PublicApiSurface,
    symbols: list[PublicApiSymbol],
    occurrences_by_symbol: Mapping[int, list[TantivyOccurrenceMatch]],
    resolve_owner: Callable[[str], ModuleOwnerResolution],
    include_package: bool,
) -> list[_PlannedContractSnapshot]:
    """Plan snapshot + edge writes for one producer surface."""

    accumulators: dict[tuple[str, str, str, str], _PairAccumulator] = {}
    skipped_symbol_count = 0

    for symbol in symbols:
        skip_symbol = False
        if symbol.symbol_qualified_name is None:
            skip_symbol = True
        elif not include_package and symbol.visibility == PublicApiVisibility.PACKAGE:
            skip_symbol = True
        else:
            match_symbol_id = symbol_id_for(symbol.symbol_qualified_name)
            occurrences = occurrences_by_symbol.get(match_symbol_id, [])
            if not occurrences:
                skip_symbol = True
            else:
                matched_any = False
                for occurrence in occurrences:
                    resolution = resolve_owner(occurrence.file_path)
                    if (
                        resolution.status != "resolved"
                        or resolution.module_name is None
                    ):
                        continue
                    if resolution.module_name == surface.module_name:
                        continue

                    matched_any = True
                    pair_key = (
                        resolution.module_name,
                        surface.module_name,
                        surface.language.value,
                        surface.commit_sha,
                    )
                    accumulator = accumulators.setdefault(
                        pair_key,
                        _PairAccumulator(
                            consumer_module_name=resolution.module_name,
                            producer_module_name=surface.module_name,
                            language=surface.language,
                            commit_sha=surface.commit_sha,
                        ),
                    )
                    accumulator.evidence_paths.add(occurrence.file_path)
                    prior = accumulator.consumptions_by_symbol_id.get(symbol.id)
                    if prior is None:
                        accumulator.consumptions_by_symbol_id[symbol.id] = (
                            ModuleContractConsumption(
                                public_symbol_id=symbol.id,
                                group_id=surface.group_id,
                                commit_sha=surface.commit_sha,
                                match_symbol_id=match_symbol_id,
                                use_count=1,
                                file_count=1,
                                first_seen_path=occurrence.file_path,
                                evidence_paths_sample=[occurrence.file_path],
                            )
                        )
                        continue
                    paths = sorted(
                        {
                            *prior.evidence_paths_sample,
                            occurrence.file_path,
                        }
                    )
                    accumulator.consumptions_by_symbol_id[symbol.id] = (
                        ModuleContractConsumption(
                            public_symbol_id=prior.public_symbol_id,
                            group_id=prior.group_id,
                            commit_sha=prior.commit_sha,
                            match_symbol_id=prior.match_symbol_id,
                            use_count=prior.use_count + 1,
                            file_count=len(paths),
                            first_seen_path=prior.first_seen_path,
                            evidence_paths_sample=paths,
                        )
                    )
                if not matched_any:
                    skip_symbol = True
        if skip_symbol:
            skipped_symbol_count += 1
            continue

    planned: list[_PlannedContractSnapshot] = []
    for pair_key in sorted(accumulators):
        accumulator = accumulators[pair_key]
        consumptions = sorted(
            accumulator.consumptions_by_symbol_id.values(),
            key=lambda consumption: consumption.public_symbol_id,
        )
        snapshot = ModuleContractSnapshot(
            id=_stable_id(
                surface.group_id,
                surface.project,
                accumulator.consumer_module_name,
                accumulator.producer_module_name,
                accumulator.language.value,
                accumulator.commit_sha,
                str(include_package),
                str(SCHEMA_VERSION_CURRENT),
            ),
            group_id=surface.group_id,
            project=surface.project,
            consumer_module_name=accumulator.consumer_module_name,
            producer_module_name=accumulator.producer_module_name,
            language=accumulator.language,
            commit_sha=accumulator.commit_sha,
            include_package=include_package,
            producer_surface_id=surface.id,
            symbol_count=len(consumptions),
            use_count=sum(consumption.use_count for consumption in consumptions),
            file_count=len(accumulator.evidence_paths),
            skipped_symbol_count=skipped_symbol_count,
        )
        planned.append(
            _PlannedContractSnapshot(
                snapshot=snapshot,
                consumptions=consumptions,
                symbols_by_fqn={symbol.fqn: symbol for symbol in symbols},
            )
        )
    return planned


def build_contract_delta(
    *,
    from_snapshot: ModuleContractSnapshot,
    to_snapshot: ModuleContractSnapshot,
    from_symbols: Mapping[str, PublicApiSymbol],
    to_symbols: Mapping[str, PublicApiSymbol],
    from_consumptions: list[ModuleContractConsumption],
    to_consumptions: list[ModuleContractConsumption],
) -> tuple[ModuleContractDelta, list[ModuleContractAffectedSymbol]]:
    """Build the minimal explicit old/new contract delta."""

    from_consumptions_by_qname = _consumptions_by_qname(
        symbols=from_symbols, consumptions=from_consumptions
    )
    to_consumptions_by_qname = _consumptions_by_qname(
        symbols=to_symbols, consumptions=to_consumptions
    )

    removed_count = 0
    signature_changed_count = 0
    added_count = 0
    affected_use_count = 0
    affected: list[ModuleContractAffectedSymbol] = []

    for qname in sorted(
        set(from_consumptions_by_qname) | set(to_consumptions_by_qname)
    ):
        from_entry = from_consumptions_by_qname.get(qname)
        to_entry = to_consumptions_by_qname.get(qname)

        if from_entry is not None and to_entry is None:
            removed_count += 1
            affected_use_count += from_entry[1].use_count
            affected.append(
                ModuleContractAffectedSymbol(
                    public_symbol_id=from_entry[0].id,
                    change_kind="removed",
                    affected_use_count=from_entry[1].use_count,
                )
            )
            continue
        if from_entry is None and to_entry is not None:
            added_count += 1
            affected_use_count += to_entry[1].use_count
            affected.append(
                ModuleContractAffectedSymbol(
                    public_symbol_id=to_entry[0].id,
                    change_kind="added",
                    affected_use_count=to_entry[1].use_count,
                )
            )
            continue

        assert from_entry is not None and to_entry is not None
        from_symbol, from_consumption = from_entry
        to_symbol, to_consumption = to_entry
        if from_symbol.signature_hash == to_symbol.signature_hash:
            continue

        signature_changed_count += 1
        changed_uses = max(from_consumption.use_count, to_consumption.use_count)
        affected_use_count += changed_uses
        affected.append(
            ModuleContractAffectedSymbol(
                public_symbol_id=to_symbol.id,
                change_kind="signature_changed",
                affected_use_count=changed_uses,
            )
        )

    delta = ModuleContractDelta(
        id=_stable_id(
            from_snapshot.id,
            to_snapshot.id,
            str(SCHEMA_VERSION_CURRENT),
        ),
        group_id=to_snapshot.group_id,
        project=to_snapshot.project,
        consumer_module_name=to_snapshot.consumer_module_name,
        producer_module_name=to_snapshot.producer_module_name,
        language=to_snapshot.language,
        from_commit_sha=from_snapshot.commit_sha,
        to_commit_sha=to_snapshot.commit_sha,
        removed_consumed_symbol_count=removed_count,
        signature_changed_consumed_symbol_count=signature_changed_count,
        added_consumed_symbol_count=added_count,
        affected_use_count=affected_use_count,
    )
    return delta, affected


async def _load_public_api_surfaces(
    *, driver: AsyncDriver, project: str, commit_sha: str
) -> list[_SurfaceSymbols]:
    async with driver.session() as session:
        result = await session.run(
            _LOAD_PUBLIC_API_ROWS, project=project, commit_sha=commit_sha
        )
        rows = await result.data()

    grouped: dict[str, _SurfaceSymbols] = {}
    for row in rows:
        surface = PublicApiSurface.model_validate(row["surface_props"])
        symbol = PublicApiSymbol.model_validate(row["symbol_props"])
        current = grouped.get(surface.id)
        if current is None:
            grouped[surface.id] = _SurfaceSymbols(surface=surface, symbols=[symbol])
            continue
        current.symbols.append(symbol)
    return [grouped[key] for key in sorted(grouped)]


async def _load_occurrences_for_surface(
    *,
    bridge: object,
    symbols: list[PublicApiSymbol],
    commit_sha: str,
    include_package: bool,
    phases: tuple[str, ...],
    cache: dict[tuple[int, str], list[TantivyOccurrenceMatch]],
) -> dict[int, list[TantivyOccurrenceMatch]]:
    from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

    typed_bridge = bridge
    assert isinstance(typed_bridge, TantivyBridge)
    occurrences_by_symbol: dict[int, list[TantivyOccurrenceMatch]] = {}
    for symbol in symbols:
        if symbol.symbol_qualified_name is None:
            continue
        if not include_package and symbol.visibility == PublicApiVisibility.PACKAGE:
            continue
        match_symbol_id = symbol_id_for(symbol.symbol_qualified_name)
        cache_key = (match_symbol_id, commit_sha)
        if cache_key not in cache:
            cache[cache_key] = await typed_bridge.search_occurrences_async(
                symbol_id=match_symbol_id,
                commit_sha=commit_sha,
                phases=phases,
            )
        occurrences_by_symbol[match_symbol_id] = cache[cache_key]
    return occurrences_by_symbol


async def _resolve_owner_cache(
    *,
    driver: AsyncDriver,
    group_id: str,
    repo_path: Path,
    occurrences_by_symbol: Mapping[int, list[TantivyOccurrenceMatch]],
) -> dict[str, ModuleOwnerResolution]:
    owner_cache: dict[str, ModuleOwnerResolution] = {}
    for occurrences in occurrences_by_symbol.values():
        for occurrence in occurrences:
            if occurrence.file_path in owner_cache:
                continue
            owner_cache[occurrence.file_path] = await resolve_module_owner(
                driver=driver,
                group_id=group_id,
                repo_path=repo_path,
                file_path=occurrence.file_path,
            )
    return owner_cache


async def _write_contract_graph(
    *,
    driver: AsyncDriver,
    planned: list[_PlannedContractSnapshot],
    planned_deltas: list[_PlannedContractDelta],
) -> ExtractorStats:
    nodes_written = 0
    edges_written = 0
    async with driver.session() as session:
        for planned_snapshot in planned:
            await _write_snapshot(session=session, snapshot=planned_snapshot.snapshot)
            nodes_written += 1
            edges_written += 1
            for consumption in planned_snapshot.consumptions:
                await _write_consumption(
                    session=session,
                    snapshot_id=planned_snapshot.snapshot.id,
                    consumption=consumption,
                )
                edges_written += 1
        for planned_delta in planned_deltas:
            await _write_delta(
                session=session,
                delta=planned_delta.delta,
                from_snapshot_id=planned_delta.from_snapshot_id,
                to_snapshot_id=planned_delta.to_snapshot_id,
            )
            nodes_written += 1
            edges_written += 2
            for affected_symbol in planned_delta.affected_symbols:
                await _write_delta_affected_symbol(
                    session=session,
                    delta_id=planned_delta.delta.id,
                    affected_symbol=affected_symbol,
                )
                edges_written += 1
    return ExtractorStats(nodes_written=nodes_written, edges_written=edges_written)


async def _write_snapshot(
    *, session: AsyncSession, snapshot: ModuleContractSnapshot
) -> None:
    await session.run(
        _WRITE_SNAPSHOT,
        snapshot_id=snapshot.id,
        snapshot_props=snapshot.model_dump(mode="json", exclude_none=True),
        surface_id=snapshot.producer_surface_id,
    )


async def _write_consumption(
    *,
    session: AsyncSession,
    snapshot_id: str,
    consumption: ModuleContractConsumption,
) -> None:
    edge_props = consumption.model_dump(mode="json", exclude_none=True)
    edge_props.pop("public_symbol_id")
    await session.run(
        _WRITE_CONSUMPTION,
        snapshot_id=snapshot_id,
        symbol_id=consumption.public_symbol_id,
        edge_props=edge_props,
    )


async def _write_delta(
    *,
    session: AsyncSession,
    delta: ModuleContractDelta,
    from_snapshot_id: str,
    to_snapshot_id: str,
) -> None:
    await session.run(
        _WRITE_DELTA,
        delta_id=delta.id,
        delta_props=delta.model_dump(mode="json", exclude_none=True),
        from_snapshot_id=from_snapshot_id,
        to_snapshot_id=to_snapshot_id,
    )


async def _write_delta_affected_symbol(
    *,
    session: AsyncSession,
    delta_id: str,
    affected_symbol: ModuleContractAffectedSymbol,
) -> None:
    edge_props = affected_symbol.model_dump(mode="json", exclude_none=True)
    edge_props.pop("public_symbol_id")
    await session.run(
        _WRITE_DELTA_AFFECTED_SYMBOL,
        delta_id=delta_id,
        symbol_id=affected_symbol.public_symbol_id,
        edge_props=edge_props,
    )


def _consumptions_by_qname(
    *,
    symbols: Mapping[str, PublicApiSymbol],
    consumptions: list[ModuleContractConsumption],
) -> dict[str, tuple[PublicApiSymbol, ModuleContractConsumption]]:
    symbol_by_id = {symbol.id: symbol for symbol in symbols.values()}
    result: dict[str, tuple[PublicApiSymbol, ModuleContractConsumption]] = {}
    for consumption in consumptions:
        symbol = symbol_by_id.get(consumption.public_symbol_id)
        if symbol is None:
            continue
        result[symbol.fqn] = (symbol, consumption)
    return result


def _stable_id(*parts: str) -> str:
    payload = "||".join(parts)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def _snapshot_key(
    snapshot: ModuleContractSnapshot,
) -> tuple[str, str, str, str, bool]:
    return (
        snapshot.consumer_module_name,
        snapshot.producer_module_name,
        snapshot.language.value,
        snapshot.commit_sha,
        snapshot.include_package,
    )


def _read_head_sha(repo_path: Path) -> str:
    try:
        git_dir, refs_root = _resolve_git_dirs(repo_path)
    except (FileNotFoundError, OSError, ValueError):
        return "unknown"

    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "unknown"
    if not head.startswith("ref: "):
        return head[:40]
    ref_name = head.removeprefix("ref: ").strip()
    ref_path = refs_root / ref_name
    try:
        return ref_path.read_text(encoding="utf-8").strip()[:40]
    except FileNotFoundError:
        return _read_packed_ref(refs_root, ref_name)


def _resolve_git_dirs(repo_path: Path) -> tuple[Path, Path]:
    git_path = repo_path / ".git"
    if git_path.is_dir():
        git_dir = git_path
    else:
        pointer = git_path.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise ValueError("invalid gitdir pointer")
        git_dir = (repo_path / pointer.removeprefix("gitdir: ").strip()).resolve()

    commondir_path = git_dir / "commondir"
    if commondir_path.exists():
        common_dir = (
            git_dir / commondir_path.read_text(encoding="utf-8").strip()
        ).resolve()
        return git_dir, common_dir
    return git_dir, git_dir


def _read_packed_ref(refs_root: Path, ref_name: str) -> str:
    packed_refs_path = refs_root / "packed-refs"
    try:
        for line in packed_refs_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "^")):
                continue
            sha, _, packed_ref_name = stripped.partition(" ")
            if packed_ref_name == ref_name:
                return sha[:40]
    except FileNotFoundError:
        return "unknown"
    return "unknown"
