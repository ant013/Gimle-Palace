from palace_mcp.memory.cypher import UPSERT_PROJECT
from palace_mcp.memory.schema import ProjectInfo


def test_upsert_project_merges_by_slug() -> None:
    assert "MERGE (p:Project {slug: $slug})" in UPSERT_PROJECT


def test_upsert_project_sets_group_id_from_slug() -> None:
    assert "p.group_id" in UPSERT_PROJECT
    assert "'project/' + $slug" in UPSERT_PROJECT


def test_upsert_project_preserves_source_created_at() -> None:
    assert "coalesce(p.source_created_at, $now)" in UPSERT_PROJECT


def test_project_info_has_required_fields() -> None:
    fields = ProjectInfo.model_fields
    for req in (
        "slug",
        "name",
        "tags",
        "source_created_at",
        "source_updated_at",
        "entity_counts",
    ):
        assert req in fields, f"ProjectInfo missing required field: {req}"
