"""Filter whitelist + Cypher WHERE-clause synthesis.

Keys are statically whitelisted per entity type. Values always pass as
named Cypher parameters. Unknown keys are collected separately so the
caller can log a `query.lookup.unknown_filter` warning.

graphiti-core 0.28.2 persists EntityNode.attributes as flat Neo4j node
properties (SET n += $attrs), so top-level filter syntax {prop: $val} works.
"""

from typing import Any, Literal

EntityType = Literal[
    "Project",
    "Iteration",
    "Episode",
    "Decision",
    "IterationNote",
    "Finding",
    "Module",
    "File",
    "Symbol",
    "APIEndpoint",
    "Model",
    "Repository",
    "ExternalLib",
    "Trace",
]


# Per-entity whitelist mapping filter-key → Cypher WHERE clause template.
# Conservative starting set; grows per use case. group_id / uuid / name
# are always valid and handled at the resolver level, not here.
_WHITELIST: dict[EntityType, dict[str, str]] = {
    "Project": {
        "slug": "n.slug = $slug",
    },
    "Iteration": {
        "kind": "n.kind = $kind",
        "number": "n.number = $number",
    },
    "Episode": {
        "kind": "n.kind = $kind",
        "source": "n.source = $source",
    },
    "Decision": {
        "author": "n.author = $author",
        "status": "n.status = $status",
    },
    "IterationNote": {
        "iteration_ref": "n.iteration_ref = $iteration_ref",
    },
    "Finding": {
        "severity": "n.severity = $severity",
        "category": "n.category = $category",
        "source": "n.source = $source",
    },
    "Module": {
        "path": "n.path = $path",
        "kind": "n.kind = $kind",
    },
    "File": {
        "path": "n.path = $path",
    },
    "Symbol": {
        "kind": "n.kind = $kind",
        "name": "n.name = $name",
        "file_path": "n.file_path = $file_path",
    },
    "APIEndpoint": {
        "method": "n.method = $method",
        "path": "n.path = $path",
    },
    "Model": {},
    "Repository": {
        "storage_kind": "n.storage_kind = $storage_kind",
    },
    "ExternalLib": {
        "version": "n.version = $version",
        "category": "n.category = $category",
    },
    "Trace": {
        "agent_id": "n.agent_id = $agent_id",
    },
}


def resolve_filters(
    entity_type: EntityType, filters: dict[str, Any]
) -> tuple[list[str], dict[str, Any], list[str]]:
    """Return (where_clauses, cypher_params, unknown_keys).

    Only keys in the whitelist produce clauses/params. Unknown keys are
    surfaced so the tool can log a structured warning.
    """
    allowed = _WHITELIST[entity_type]
    where_clauses: list[str] = []
    params: dict[str, Any] = {}
    unknown: list[str] = []

    for k, v in filters.items():
        clause = allowed.get(k)
        if clause is None:
            unknown.append(k)
            continue
        where_clauses.append(clause)
        params[k] = v

    return where_clauses, params, unknown
