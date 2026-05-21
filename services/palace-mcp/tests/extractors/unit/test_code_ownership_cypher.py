from __future__ import annotations

from palace_mcp.extractors.code_ownership.churn_aggregator import _CHURN_CYPHER
from palace_mcp.extractors.code_ownership.neo4j_writer import _DELETE_BY_PATH_CYPHER


def test_churn_query_combines_file_match_and_merge_filter() -> None:
    assert "WHERE coalesce(f.file_path, f.path) = p" in _CHURN_CYPHER
    assert "AND NOT c.is_merge" in _CHURN_CYPHER


def test_delete_query_matches_relationship_before_where() -> None:
    assert (
        "MATCH (f:File {project_id: $proj})-[r:OWNED_BY {source: $source}]->()"
        in _DELETE_BY_PATH_CYPHER
    )
