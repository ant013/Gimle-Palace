"""Neo4j writer for reactive_dependency_tracer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from neo4j import AsyncDriver
from pydantic import BaseModel

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    REACTIVE_TRACER_SOURCE,
    ReactiveEdge,
    ReactiveEdgeKind,
)
from palace_mcp.extractors.reactive_dependency_tracer.normalizer import (
    NormalizedReactiveFile,
)

_DELETE_FILE_SCOPE = """
MATCH (n)
WHERE n.source = $source
  AND n.project = $project
  AND n.commit_sha = $commit_sha
  AND n.language = $language
  AND n.file_path = $file_path
  AND (n:ReactiveComponent OR n:ReactiveState OR n:ReactiveEffect OR n:ReactiveDiagnostic)
DETACH DELETE n
"""

_DELETE_RUN_SCOPE = """
MATCH (n:ReactiveDiagnostic)
WHERE n.source = $source
  AND n.project = $project
  AND n.commit_sha = $commit_sha
  AND n.language = $language
  AND n.file_path IS NULL
DETACH DELETE n
"""

_MERGE_COMPONENT = """
MERGE (node:ReactiveComponent {id: $node_id})
SET node += $node_props
"""

_MERGE_STATE = """
MERGE (node:ReactiveState {id: $node_id})
SET node += $node_props
"""

_MERGE_EFFECT = """
MERGE (node:ReactiveEffect {id: $node_id})
SET node += $node_props
"""

_MERGE_DIAGNOSTIC = """
MERGE (node:ReactiveDiagnostic {id: $node_id})
SET node += $node_props
"""

_MERGE_DIAGNOSTIC_FOR = """
MATCH (diag:ReactiveDiagnostic {id: $diagnostic_id})
MATCH (target {id: $target_id})
MERGE (diag)-[rel:DIAGNOSTIC_FOR {id: $relationship_id}]->(target)
SET rel += $relationship_props
"""

_EDGE_QUERY_BY_KIND: dict[ReactiveEdgeKind, str] = {
    ReactiveEdgeKind.DECLARES_STATE: """
MATCH (src {id: $source_id})
MATCH (dst {id: $target_id})
MERGE (src)-[rel:DECLARES_STATE {id: $relationship_id}]->(dst)
SET rel += $relationship_props
""",
    ReactiveEdgeKind.READS_STATE: """
MATCH (src {id: $source_id})
MATCH (dst {id: $target_id})
MERGE (src)-[rel:READS_STATE {id: $relationship_id}]->(dst)
SET rel += $relationship_props
""",
    ReactiveEdgeKind.WRITES_STATE: """
MATCH (src {id: $source_id})
MATCH (dst {id: $target_id})
MERGE (src)-[rel:WRITES_STATE {id: $relationship_id}]->(dst)
SET rel += $relationship_props
""",
    ReactiveEdgeKind.BINDS_TO: """
MATCH (src {id: $source_id})
MATCH (dst {id: $target_id})
MERGE (src)-[rel:BINDS_TO {id: $relationship_id}]->(dst)
SET rel += $relationship_props
""",
    ReactiveEdgeKind.TRIGGERS_EFFECT: """
MATCH (src {id: $source_id})
MATCH (dst {id: $target_id})
MERGE (src)-[rel:TRIGGERS_EFFECT {id: $relationship_id}]->(dst)
SET rel += $relationship_props
""",
    ReactiveEdgeKind.HAS_LIFECYCLE_EFFECT: """
MATCH (src {id: $source_id})
MATCH (dst {id: $target_id})
MERGE (src)-[rel:HAS_LIFECYCLE_EFFECT {id: $relationship_id}]->(dst)
SET rel += $relationship_props
""",
    ReactiveEdgeKind.CALLS_REACTIVE_COMPONENT: """
MATCH (src {id: $source_id})
MATCH (dst {id: $target_id})
MERGE (src)-[rel:CALLS_REACTIVE_COMPONENT {id: $relationship_id}]->(dst)
SET rel += $relationship_props
""",
}


@dataclass(frozen=True)
class ReactiveWriteSummary:
    """Counter-precise summary from Neo4j write operations."""

    nodes_created: int = 0
    relationships_created: int = 0
    properties_set: int = 0


async def write_reactive_graph(
    *,
    driver: AsyncDriver,
    batches: tuple[NormalizedReactiveFile, ...],
) -> ReactiveWriteSummary:
    """Write validated normalized batches with per-file transaction isolation."""

    total = ReactiveWriteSummary()
    async with driver.session() as session:
        for batch in batches:
            try:
                _validate_batch_scope(batch)
            except ValueError:
                continue
            summary = await session.execute_write(_write_batch, batch)
            total = ReactiveWriteSummary(
                nodes_created=total.nodes_created + summary.nodes_created,
                relationships_created=(
                    total.relationships_created + summary.relationships_created
                ),
                properties_set=total.properties_set + summary.properties_set,
            )
    return total


def _validate_batch_scope(batch: NormalizedReactiveFile) -> None:
    file_path = batch.file_path
    for component in batch.components:
        if file_path is not None and component.file_path != file_path:
            raise ValueError("batch file_path mismatch")
        if component.language != batch.language:
            raise ValueError("batch language mismatch")
    for state in batch.states:
        if file_path is not None and state.file_path != file_path:
            raise ValueError("batch file_path mismatch")
        if state.language != batch.language:
            raise ValueError("batch language mismatch")
    for effect in batch.effects:
        if file_path is not None and effect.file_path != file_path:
            raise ValueError("batch file_path mismatch")
        if effect.language not in {Language.UNKNOWN, batch.language}:
            raise ValueError("batch language mismatch")
    for diagnostic in batch.diagnostics:
        if file_path is None:
            if diagnostic.file_path is not None:
                raise ValueError("run batch cannot contain file-level diagnostic")
        elif diagnostic.file_path != file_path:
            raise ValueError("diagnostic file_path mismatch")
        if diagnostic.language != batch.language:
            raise ValueError("diagnostic language mismatch")
    for edge in batch.edges:
        if file_path is not None and edge.file_path != file_path:
            raise ValueError("edge file_path mismatch")


async def _write_batch(tx: Any, batch: NormalizedReactiveFile) -> ReactiveWriteSummary:
    summary = ReactiveWriteSummary()
    if batch.file_path is None:
        delete_summary = await _consume(
            tx,
            _DELETE_RUN_SCOPE,
            source=REACTIVE_TRACER_SOURCE,
            project=_project_for(batch),
            commit_sha=_commit_sha_for(batch),
            language=batch.language.value,
        )
    else:
        delete_summary = await _consume(
            tx,
            _DELETE_FILE_SCOPE,
            source=REACTIVE_TRACER_SOURCE,
            project=_project_for(batch),
            commit_sha=_commit_sha_for(batch),
            language=batch.language.value,
            file_path=batch.file_path,
        )
    summary = _add(summary, delete_summary)

    for component in batch.components:
        summary = _add(
            summary,
            await _consume(
                tx,
                _MERGE_COMPONENT,
                node_id=component.id,
                node_props=_neo4j_node_props(component),
            ),
        )
    for state in batch.states:
        summary = _add(
            summary,
            await _consume(
                tx,
                _MERGE_STATE,
                node_id=state.id,
                node_props=_neo4j_node_props(state),
            ),
        )
    for effect in batch.effects:
        summary = _add(
            summary,
            await _consume(
                tx,
                _MERGE_EFFECT,
                node_id=effect.id,
                node_props=_neo4j_node_props(effect),
            ),
        )
    for diagnostic in batch.diagnostics:
        summary = _add(
            summary,
            await _consume(
                tx,
                _MERGE_DIAGNOSTIC,
                node_id=diagnostic.id,
                node_props=_neo4j_node_props(diagnostic),
            ),
        )
        if diagnostic.ref is None:
            continue
        target_id = batch.ref_to_node_id.get(diagnostic.ref)
        if target_id is None:
            continue
        summary = _add(
            summary,
            await _consume(
                tx,
                _MERGE_DIAGNOSTIC_FOR,
                diagnostic_id=diagnostic.id,
                target_id=target_id,
                relationship_id=f"{diagnostic.id}:{target_id}",
                relationship_props={"ref": diagnostic.ref},
            ),
        )
    for edge in batch.edges:
        summary = _add(summary, await _write_edge(tx, edge))
    return summary


def _project_for(batch: NormalizedReactiveFile) -> str:
    for component in batch.components:
        return component.project
    for state in batch.states:
        return state.project
    for effect in batch.effects:
        return effect.project
    for diagnostic in batch.diagnostics:
        return diagnostic.project
    return ""


def _commit_sha_for(batch: NormalizedReactiveFile) -> str:
    for component in batch.components:
        return component.commit_sha
    for state in batch.states:
        return state.commit_sha
    for effect in batch.effects:
        return effect.commit_sha
    for diagnostic in batch.diagnostics:
        return diagnostic.commit_sha
    return ""


async def _write_edge(tx: Any, edge: ReactiveEdge) -> ReactiveWriteSummary:
    query = _EDGE_QUERY_BY_KIND[edge.edge_kind]
    props = {
        "id": edge.id,
        "confidence": edge.confidence.value,
        "line": edge.line,
        "resolution_status": edge.resolution_status.value,
    }
    if edge.access_path is not None:
        props["access_path"] = edge.access_path
    if edge.binding_kind is not None:
        props["binding_kind"] = edge.binding_kind
    if edge.trigger_expression_kind is not None:
        props["trigger_kind"] = edge.trigger_expression_kind.value
    return await _consume(
        tx,
        query,
        source_id=edge.source_id,
        target_id=edge.target_id,
        relationship_id=edge.id,
        relationship_props=props,
    )


def _neo4j_node_props(node: BaseModel) -> dict[str, object]:
    props: dict[str, object] = {
        key: value
        for key, value in node.model_dump(mode="json", exclude_none=True).items()
    }
    range_props = props.pop("range", None)
    if isinstance(range_props, dict):
        start_line = range_props.get("start_line")
        start_col = range_props.get("start_col")
        end_line = range_props.get("end_line")
        end_col = range_props.get("end_col")
        if isinstance(start_line, int):
            props["range_start_line"] = start_line
        if isinstance(start_col, int):
            props["range_start_col"] = start_col
        if isinstance(end_line, int):
            props["range_end_line"] = end_line
        if isinstance(end_col, int):
            props["range_end_col"] = end_col
    return props


def _add(
    left: ReactiveWriteSummary, right: ReactiveWriteSummary
) -> ReactiveWriteSummary:
    return ReactiveWriteSummary(
        nodes_created=left.nodes_created + right.nodes_created,
        relationships_created=left.relationships_created + right.relationships_created,
        properties_set=left.properties_set + right.properties_set,
    )


async def _consume(tx: Any, query: str, **params: object) -> ReactiveWriteSummary:
    result = await tx.run(query, **params)
    summary = await result.consume()
    counters = summary.counters
    return ReactiveWriteSummary(
        nodes_created=counters.nodes_created,
        relationships_created=counters.relationships_created,
        properties_set=counters.properties_set,
    )
