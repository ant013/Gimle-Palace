import pytest
from pydantic import ValidationError

from palace_mcp.memory.schema import (
    HealthResponse,
    LookupRequest,
    LookupResponse,
    LookupResponseItem,
)


def test_lookup_request_rejects_unknown_entity_type() -> None:
    with pytest.raises(ValidationError):
        LookupRequest(entity_type="Bogus")  # type: ignore[arg-type]


def test_lookup_request_limit_bounds() -> None:
    LookupRequest(entity_type="Issue", limit=1)
    LookupRequest(entity_type="Issue", limit=100)
    with pytest.raises(ValidationError):
        LookupRequest(entity_type="Issue", limit=0)
    with pytest.raises(ValidationError):
        LookupRequest(entity_type="Issue", limit=101)


def test_lookup_response_item_related_accepts_none_dict_list() -> None:
    item = LookupResponseItem(
        id="abc",
        type="Comment",
        properties={"body": "..."},
        related={"author": None, "issue": {"id": "i1"}, "comments": [{"id": "c1"}]},
    )
    assert item.related["author"] is None
    assert isinstance(item.related["issue"], dict)
    assert isinstance(item.related["comments"], list)


def test_health_response_shape() -> None:
    h = HealthResponse(
        neo4j_reachable=True,
        entity_counts={"Issue": 31, "Comment": 52, "Agent": 12},
        last_ingest_started_at="2026-04-17T06:00:00+00:00",
        last_ingest_finished_at="2026-04-17T06:00:02+00:00",
        last_ingest_duration_ms=2000,
        last_ingest_errors=[],
    )
    assert h.entity_counts["Issue"] == 31


def test_lookup_response_shape() -> None:
    r = LookupResponse(
        items=[],
        total_matched=0,
        query_ms=5,
    )
    assert r.total_matched == 0
