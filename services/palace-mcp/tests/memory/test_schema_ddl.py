from palace_mcp.memory.cypher import CREATE_INDEXES


def test_no_old_label_indexes() -> None:
    joined = " ".join(CREATE_INDEXES)
    for label in ("Issue", "Comment", "Agent", "IngestRun"):
        assert f"(n:{label})" not in joined, (
            f"old label {label!r} still in CREATE_INDEXES — should have been removed in GIM-75"
        )


def test_create_indexes_are_idempotent() -> None:
    for stmt in CREATE_INDEXES:
        assert "IF NOT EXISTS" in stmt, "all index statements must be idempotent"


def test_project_slug_unique_constraint() -> None:
    from palace_mcp.memory.cypher import CREATE_CONSTRAINTS

    assert any(
        "CONSTRAINT project_slug" in c and "REQUIRE p.slug IS UNIQUE" in c
        for c in CREATE_CONSTRAINTS
    )


def test_project_group_id_index() -> None:
    from palace_mcp.memory.cypher import CREATE_INDEXES

    assert any(
        "INDEX project_group_id" in idx and "FOR (p:Project)" in idx
        for idx in CREATE_INDEXES
    )
