def test_create_ingest_run_sets_group_id() -> None:
    from palace_mcp.memory.cypher import CREATE_INGEST_RUN

    assert "group_id: $group_id" in CREATE_INGEST_RUN
    assert "outcome: null" in CREATE_INGEST_RUN
    assert "message: null" in CREATE_INGEST_RUN
    assert "next_action: null" in CREATE_INGEST_RUN


def test_finalize_ingest_run_persists_outcome_contract() -> None:
    from palace_mcp.memory.cypher import FINALIZE_INGEST_RUN

    assert "r.outcome" in FINALIZE_INGEST_RUN
    assert "r.message" in FINALIZE_INGEST_RUN
    assert "r.next_action" in FINALIZE_INGEST_RUN


def test_latest_ingest_run_accepts_optional_group_filter() -> None:
    from palace_mcp.memory.cypher import LATEST_INGEST_RUN_FOR_GROUP

    assert "r.group_id = $group_id" in LATEST_INGEST_RUN_FOR_GROUP
