from palace_mcp.memory.cypher import (
    LIST_PROJECT_SLUGS,
    LOOKUP_PROJECT_NAMESPACE,
    UPSERT_PROJECT,
)
from palace_mcp.memory.schema import ProjectInfo


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
    ):
        assert req in fields, f"ProjectInfo missing required field: {req}"
