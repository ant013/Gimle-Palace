"""Resolve incremental symbol, edge, seed, and public-API deltas.

Capture the pre-write baseline before mutating Symbol/PublicApi state, then
resolve against the current graph after the symbol-writer stale-edge sweep and
all relevant edge/public-API writers have completed for the same commit.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from neo4j import AsyncDriver


EdgeType = Literal[
    "CALLS",
    "REFERENCES",
    "EXTENDS",
    "CONFORMS_TO",
    "EXTENSION_OF",
    "EXISTENTIAL_USE",
]
SymbolChangeKind = Literal["added", "removed", "moved"]
EdgeChangeKind = Literal["added", "removed"]
PublicApiChangeKind = Literal["added", "removed", "signature_changed"]

_EDGE_TYPE_QUERY = "CALLS|REFERENCES|EXTENDS|CONFORMS_TO|EXTENSION_OF|EXISTENTIAL_USE"
_PUBLIC_SEED_ACCESS = frozenset({"public", "open"})
_SEED_FLAG_FIELDS = (
    "is_main_entry",
    "is_iboutlet",
    "is_ibaction",
    "is_objc_members",
    "is_ns_managed",
    "is_property_wrapper",
    "is_codable",
    "is_swift_app_storage",
    "is_env_key",
)

_LOAD_ACTIVE_SYMBOLS = """
MATCH (s:Symbol {group_id: $group_id})
WHERE s.file_path IN $file_paths
  AND s.deleted_at IS NULL
  AND NOT s:Deprecated
RETURN
  s.qualified_name AS qualified_name,
  s.file_path AS file_path,
  s.module_name AS module_name,
  coalesce(s.access_modifier, '') AS access_modifier,
  coalesce(s.is_main_entry, false) AS is_main_entry,
  coalesce(s.is_iboutlet, false) AS is_iboutlet,
  coalesce(s.is_ibaction, false) AS is_ibaction,
  coalesce(s.is_objc_members, false) AS is_objc_members,
  coalesce(s.is_ns_managed, false) AS is_ns_managed,
  coalesce(s.is_property_wrapper, false) AS is_property_wrapper,
  coalesce(s.is_codable, false) AS is_codable,
  coalesce(s.is_swift_app_storage, false) AS is_swift_app_storage,
  coalesce(s.is_env_key, false) AS is_env_key
ORDER BY qualified_name
"""

_LOAD_ACTIVE_EDGES = f"""
MATCH (source:Symbol {{group_id: $group_id}})
      -[rel:{_EDGE_TYPE_QUERY}]->
      (target:Symbol {{group_id: $group_id}})
WHERE source.file_path IN $file_paths
  AND source.deleted_at IS NULL
  AND NOT source:Deprecated
  AND target.deleted_at IS NULL
  AND NOT target:Deprecated
RETURN
  source.qualified_name AS source,
  target.qualified_name AS target,
  type(rel) AS relationship_type
ORDER BY source, relationship_type, target
"""

_LOAD_PUBLIC_API_SYMBOLS = """
MATCH (symbol:PublicApiSymbol {project: $project, commit_sha: $commit_sha})
WHERE symbol.source_artifact_path IN $file_paths
RETURN
  symbol.fqn AS fqn,
  symbol.module_name AS module_name,
  symbol.source_artifact_path AS source_artifact_path,
  symbol.signature_hash AS signature_hash
ORDER BY source_artifact_path, module_name, fqn
"""


@dataclass(frozen=True)
class SymbolSnapshot:
    qualified_name: str
    file_path: str | None
    module_name: str | None
    access_modifier: str
    is_main_entry: bool = False
    is_iboutlet: bool = False
    is_ibaction: bool = False
    is_objc_members: bool = False
    is_ns_managed: bool = False
    is_property_wrapper: bool = False
    is_codable: bool = False
    is_swift_app_storage: bool = False
    is_env_key: bool = False


@dataclass(frozen=True)
class EdgeSnapshot:
    source: str
    target: str
    relationship_type: EdgeType


@dataclass(frozen=True)
class PublicApiSnapshot:
    fqn: str
    module_name: str
    source_artifact_path: str
    signature_hash: str


@dataclass(frozen=True)
class DeltaResolutionBaseline:
    group_id: str
    project: str
    previous_commit_sha: str | None
    affected_paths: frozenset[str]
    symbols: tuple[SymbolSnapshot, ...]
    edges: tuple[EdgeSnapshot, ...]
    public_api_symbols: tuple[PublicApiSnapshot, ...]


@dataclass(frozen=True)
class SymbolDelta:
    qualified_name: str
    change_kind: SymbolChangeKind
    previous_file_path: str | None = None
    current_file_path: str | None = None
    previous_module_name: str | None = None
    current_module_name: str | None = None


@dataclass(frozen=True)
class EdgeDelta:
    source: str
    target: str
    relationship_type: EdgeType
    change_kind: EdgeChangeKind


@dataclass(frozen=True)
class SeedDelta:
    qualified_name: str
    previous_is_seed: bool
    current_is_seed: bool


@dataclass(frozen=True)
class PublicApiDelta:
    fqn: str
    module_name: str
    source_artifact_path: str
    change_kind: PublicApiChangeKind
    previous_signature_hash: str | None = None
    current_signature_hash: str | None = None


@dataclass(frozen=True)
class ResolvedDelta:
    symbol_deltas: tuple[SymbolDelta, ...]
    edge_deltas: tuple[EdgeDelta, ...]
    seed_deltas: tuple[SeedDelta, ...]
    public_api_deltas: tuple[PublicApiDelta, ...]


async def capture_delta_resolution_baseline(
    driver: "AsyncDriver",
    *,
    group_id: str,
    project: str,
    previous_commit_sha: str | None,
    changed_paths: set[str],
    removed_paths: set[str],
) -> DeltaResolutionBaseline:
    """Read the pre-write snapshot for the affected file/artifact paths."""
    affected_paths = frozenset(changed_paths | removed_paths)
    if not affected_paths:
        return DeltaResolutionBaseline(
            group_id=group_id,
            project=project,
            previous_commit_sha=previous_commit_sha,
            affected_paths=frozenset(),
            symbols=(),
            edges=(),
            public_api_symbols=(),
        )

    symbols = await _load_symbol_snapshots(
        driver,
        group_id=group_id,
        file_paths=affected_paths,
    )
    edges = await _load_edge_snapshots(
        driver,
        group_id=group_id,
        file_paths=affected_paths,
    )
    public_api_symbols: tuple[PublicApiSnapshot, ...] = ()
    if previous_commit_sha is not None:
        public_api_symbols = await _load_public_api_snapshots(
            driver,
            project=project,
            commit_sha=previous_commit_sha,
            file_paths=affected_paths,
        )
    return DeltaResolutionBaseline(
        group_id=group_id,
        project=project,
        previous_commit_sha=previous_commit_sha,
        affected_paths=affected_paths,
        symbols=symbols,
        edges=edges,
        public_api_symbols=public_api_symbols,
    )


async def resolve_delta_resolution(
    driver: "AsyncDriver",
    *,
    baseline: DeltaResolutionBaseline,
    current_commit_sha: str | None,
) -> ResolvedDelta:
    """Resolve delta after the current commit's writers have materialized state."""
    if not baseline.affected_paths:
        return ResolvedDelta((), (), (), ())

    current_symbols = await _load_symbol_snapshots(
        driver,
        group_id=baseline.group_id,
        file_paths=baseline.affected_paths,
    )
    current_edges = await _load_edge_snapshots(
        driver,
        group_id=baseline.group_id,
        file_paths=baseline.affected_paths,
    )
    current_public_api_symbols: tuple[PublicApiSnapshot, ...] = ()
    if current_commit_sha is not None:
        current_public_api_symbols = await _load_public_api_snapshots(
            driver,
            project=baseline.project,
            commit_sha=current_commit_sha,
            file_paths=baseline.affected_paths,
        )
    return diff_delta_snapshots(
        baseline=baseline,
        current_symbols=current_symbols,
        current_edges=current_edges,
        current_public_api_symbols=current_public_api_symbols,
    )


def diff_delta_snapshots(
    *,
    baseline: DeltaResolutionBaseline,
    current_symbols: Iterable[SymbolSnapshot],
    current_edges: Iterable[EdgeSnapshot],
    current_public_api_symbols: Iterable[PublicApiSnapshot],
) -> ResolvedDelta:
    """Compare the affected baseline snapshot with the current snapshot."""
    prior_symbols = {row.qualified_name: row for row in baseline.symbols}
    next_symbols = {row.qualified_name: row for row in current_symbols}

    symbol_deltas: list[SymbolDelta] = []
    seed_deltas: list[SeedDelta] = []
    for qualified_name in sorted(set(prior_symbols) | set(next_symbols)):
        previous = prior_symbols.get(qualified_name)
        current = next_symbols.get(qualified_name)
        if previous is None and current is not None:
            symbol_deltas.append(
                SymbolDelta(
                    qualified_name=qualified_name,
                    change_kind="added",
                    current_file_path=current.file_path,
                    current_module_name=current.module_name,
                )
            )
            continue
        if previous is not None and current is None:
            symbol_deltas.append(
                SymbolDelta(
                    qualified_name=qualified_name,
                    change_kind="removed",
                    previous_file_path=previous.file_path,
                    previous_module_name=previous.module_name,
                )
            )
            continue
        assert previous is not None and current is not None
        if (
            previous.file_path != current.file_path
            or previous.module_name != current.module_name
        ):
            symbol_deltas.append(
                SymbolDelta(
                    qualified_name=qualified_name,
                    change_kind="moved",
                    previous_file_path=previous.file_path,
                    current_file_path=current.file_path,
                    previous_module_name=previous.module_name,
                    current_module_name=current.module_name,
                )
            )
        previous_is_seed = _is_seed(previous)
        current_is_seed = _is_seed(current)
        if previous_is_seed != current_is_seed:
            seed_deltas.append(
                SeedDelta(
                    qualified_name=qualified_name,
                    previous_is_seed=previous_is_seed,
                    current_is_seed=current_is_seed,
                )
            )

    prior_edges = set(baseline.edges)
    next_edges = set(current_edges)
    edge_deltas = sorted(
        [
            EdgeDelta(
                source=edge.source,
                target=edge.target,
                relationship_type=edge.relationship_type,
                change_kind="removed",
            )
            for edge in prior_edges - next_edges
        ]
        + [
            EdgeDelta(
                source=edge.source,
                target=edge.target,
                relationship_type=edge.relationship_type,
                change_kind="added",
            )
            for edge in next_edges - prior_edges
        ],
        key=lambda edge: (
            edge.change_kind,
            edge.relationship_type,
            edge.source,
            edge.target,
        ),
    )

    prior_public_api = {
        _public_api_key(row): row for row in baseline.public_api_symbols
    }
    next_public_api = {_public_api_key(row): row for row in current_public_api_symbols}
    public_api_deltas: list[PublicApiDelta] = []
    for key in sorted(set(prior_public_api) | set(next_public_api)):
        previous_public_api = prior_public_api.get(key)
        current_public_api = next_public_api.get(key)
        source_artifact_path, module_name, fqn = key
        if previous_public_api is None and current_public_api is not None:
            public_api_deltas.append(
                PublicApiDelta(
                    fqn=fqn,
                    module_name=module_name,
                    source_artifact_path=source_artifact_path,
                    change_kind="added",
                    current_signature_hash=current_public_api.signature_hash,
                )
            )
            continue
        if previous_public_api is not None and current_public_api is None:
            public_api_deltas.append(
                PublicApiDelta(
                    fqn=fqn,
                    module_name=module_name,
                    source_artifact_path=source_artifact_path,
                    change_kind="removed",
                    previous_signature_hash=previous_public_api.signature_hash,
                )
            )
            continue
        assert previous_public_api is not None and current_public_api is not None
        if previous_public_api.signature_hash != current_public_api.signature_hash:
            public_api_deltas.append(
                PublicApiDelta(
                    fqn=fqn,
                    module_name=module_name,
                    source_artifact_path=source_artifact_path,
                    change_kind="signature_changed",
                    previous_signature_hash=previous_public_api.signature_hash,
                    current_signature_hash=current_public_api.signature_hash,
                )
            )

    return ResolvedDelta(
        symbol_deltas=tuple(
            sorted(
                symbol_deltas,
                key=lambda delta: (delta.change_kind, delta.qualified_name),
            )
        ),
        edge_deltas=tuple(edge_deltas),
        seed_deltas=tuple(sorted(seed_deltas, key=lambda delta: delta.qualified_name)),
        public_api_deltas=tuple(
            sorted(
                public_api_deltas,
                key=lambda delta: (
                    delta.change_kind,
                    delta.source_artifact_path,
                    delta.module_name,
                    delta.fqn,
                ),
            )
        ),
    )


async def _load_symbol_snapshots(
    driver: "AsyncDriver",
    *,
    group_id: str,
    file_paths: Iterable[str],
) -> tuple[SymbolSnapshot, ...]:
    rows = await _run_query(
        driver,
        _LOAD_ACTIVE_SYMBOLS,
        group_id=group_id,
        file_paths=sorted(set(file_paths)),
    )
    return tuple(_symbol_snapshot_from_row(row) for row in rows)


async def _load_edge_snapshots(
    driver: "AsyncDriver",
    *,
    group_id: str,
    file_paths: Iterable[str],
) -> tuple[EdgeSnapshot, ...]:
    rows = await _run_query(
        driver,
        _LOAD_ACTIVE_EDGES,
        group_id=group_id,
        file_paths=sorted(set(file_paths)),
    )
    return tuple(_edge_snapshot_from_row(row) for row in rows)


async def _load_public_api_snapshots(
    driver: "AsyncDriver",
    *,
    project: str,
    commit_sha: str,
    file_paths: Iterable[str],
) -> tuple[PublicApiSnapshot, ...]:
    rows = await _run_query(
        driver,
        _LOAD_PUBLIC_API_SYMBOLS,
        project=project,
        commit_sha=commit_sha,
        file_paths=sorted(set(file_paths)),
    )
    return tuple(_public_api_snapshot_from_row(row) for row in rows)


async def _run_query(
    driver: "AsyncDriver",
    query: str,
    **params: object,
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(query, params)
        return await result.data()


def _public_api_key(snapshot: PublicApiSnapshot) -> tuple[str, str, str]:
    return (snapshot.source_artifact_path, snapshot.module_name, snapshot.fqn)


def _is_seed(snapshot: SymbolSnapshot) -> bool:
    if snapshot.access_modifier in _PUBLIC_SEED_ACCESS:
        return True
    return any(getattr(snapshot, field) for field in _SEED_FLAG_FIELDS)


def _symbol_snapshot_from_row(row: dict[str, Any]) -> SymbolSnapshot:
    return SymbolSnapshot(
        qualified_name=str(row["qualified_name"]),
        file_path=str(row["file_path"]) if row["file_path"] is not None else None,
        module_name=(
            str(row["module_name"]) if row["module_name"] is not None else None
        ),
        access_modifier=str(row["access_modifier"]),
        is_main_entry=bool(row["is_main_entry"]),
        is_iboutlet=bool(row["is_iboutlet"]),
        is_ibaction=bool(row["is_ibaction"]),
        is_objc_members=bool(row["is_objc_members"]),
        is_ns_managed=bool(row["is_ns_managed"]),
        is_property_wrapper=bool(row["is_property_wrapper"]),
        is_codable=bool(row["is_codable"]),
        is_swift_app_storage=bool(row["is_swift_app_storage"]),
        is_env_key=bool(row["is_env_key"]),
    )


def _edge_snapshot_from_row(row: dict[str, Any]) -> EdgeSnapshot:
    relationship_type = str(row["relationship_type"])
    allowed_relationship_types: frozenset[EdgeType] = frozenset(
        {
            "CALLS",
            "REFERENCES",
            "EXTENDS",
            "CONFORMS_TO",
            "EXTENSION_OF",
            "EXISTENTIAL_USE",
        }
    )
    if relationship_type not in allowed_relationship_types:
        raise ValueError(f"Unsupported relationship_type '{relationship_type}'")
    return EdgeSnapshot(
        source=str(row["source"]),
        target=str(row["target"]),
        relationship_type=relationship_type,
    )


def _public_api_snapshot_from_row(row: dict[str, Any]) -> PublicApiSnapshot:
    return PublicApiSnapshot(
        fqn=str(row["fqn"]),
        module_name=str(row["module_name"]),
        source_artifact_path=str(row["source_artifact_path"]),
        signature_hash=str(row["signature_hash"]),
    )
