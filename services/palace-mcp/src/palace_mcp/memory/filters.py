"""Filter whitelist + Cypher WHERE-clause synthesis.

Keys are statically whitelisted per entity type. Values always pass as
named Cypher parameters. Unknown keys are collected separately so the
caller can log a `query.lookup.unknown_filter` warning.
"""

from typing import Any, Literal

EntityType = Literal["Issue", "Comment", "Agent"]


# Per-entity whitelist mapping filter-key → Cypher WHERE clause template.
# `$param` slots in the clause match the filter-key name.
_WHITELIST: dict[EntityType, dict[str, str]] = {
    "Issue": {
        "key": "n.key = $key",
        "status": "n.status = $status",
        "assignee_name": "EXISTS { MATCH (n)-[:ASSIGNED_TO]->(ag:Agent {name: $assignee_name}) }",
        "source_updated_at_gte": "n.source_updated_at >= $source_updated_at_gte",
        "source_updated_at_lte": "n.source_updated_at <= $source_updated_at_lte",
    },
    "Comment": {
        "issue_key": "EXISTS { MATCH (n)-[:ON]->(i:Issue {key: $issue_key}) }",
        "author_name": "EXISTS { MATCH (n)-[:AUTHORED_BY]->(ag:Agent {name: $author_name}) }",
        "source_created_at_gte": "n.source_created_at >= $source_created_at_gte",
    },
    "Agent": {
        "name": "n.name = $name",
        "url_key": "n.url_key = $url_key",
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
