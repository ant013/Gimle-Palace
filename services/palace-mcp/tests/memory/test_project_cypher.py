from palace_mcp.memory.cypher import (
    ENTITY_COUNTS_BY_PROJECT,
    LIST_PROJECT_SLUGS,
    LOOKUP_PROJECT_NAMESPACE,
    PROJECT_INDEXED_COMMIT,
    UPSERT_PROJECT,
)
from palace_mcp.memory.schema import ProjectInfo


def test_indexed_commit_reads_last_seen_in_commit() -> None:
    # symbol_node_writer stamps the indexed commit as `last_seen_in_commit`,
    # not `commit_sha` — the query must coalesce both or it surfaces null
    # (dogfood W1: get_project_overview.indexed_commit was always null despite
    # 248k symbols carrying last_seen_in_commit).
    assert "last_seen_in_commit" in PROJECT_INDEXED_COMMIT
    assert "coalesce(n.last_seen_in_commit, n.commit_sha)" in PROJECT_INDEXED_COMMIT


def test_indexed_commit_excludes_deprecated() -> None:
    # pruned (stale-snapshot) nodes keep their old commit; excluding them keeps
    # the surfaced commit the live one.
    assert "NOT n:Deprecated" in PROJECT_INDEXED_COMMIT


def test_upsert_project_merges_by_slug() -> None:
    assert "MERGE (p:Project {slug: $slug})" in UPSERT_PROJECT


def test_upsert_project_sets_group_id_from_slug() -> None:
    assert "p.group_id" in UPSERT_PROJECT
    assert "'project/' + $slug" in UPSERT_PROJECT


def test_upsert_project_sets_cm_project_name() -> None:
    assert "p.cm_project_name" in UPSERT_PROJECT
    assert "coalesce($cm_project_name, p.cm_project_name)" in UPSERT_PROJECT


def test_upsert_project_preserves_source_created_at() -> None:
    assert "coalesce(p.source_created_at, $now)" in UPSERT_PROJECT


def test_list_project_slugs_returns_canonical_slug_field() -> None:
    assert "RETURN p.slug AS slug" in LIST_PROJECT_SLUGS
    assert "p.name AS slug" not in LIST_PROJECT_SLUGS


def test_lookup_project_namespace_matches_slug_or_cm_project_name() -> None:
    assert "p.slug = $value OR p.cm_project_name = $value" in LOOKUP_PROJECT_NAMESPACE


def test_project_info_has_required_fields() -> None:
    fields = ProjectInfo.model_fields
    for req in (
        "slug",
        "cm_project_name",
        "name",
        "tags",
        "source_created_at",
        "source_updated_at",
        "entity_counts",
        "code_index_stats",
    ):
        assert req in fields, f"ProjectInfo missing required field: {req}"


def test_entity_counts_by_project_returns_slug_not_display_name() -> None:
    assert "RETURN p.slug AS slug, type, cnt" in ENTITY_COUNTS_BY_PROJECT
    assert "RETURN p.name AS slug, type, cnt" not in ENTITY_COUNTS_BY_PROJECT
