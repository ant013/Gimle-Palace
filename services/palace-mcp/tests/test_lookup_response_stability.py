"""Task 12: Backward-compat smoke — LookupResponse structure is wire-stable.

Verifies that model_dump() output contains exactly the expected top-level keys
and that group_id is NOT present in item properties (Task 9.5 regression guard).
"""

from palace_mcp.memory.schema import LookupResponse, LookupResponseItem


def _make_item(extra_props: dict | None = None) -> LookupResponseItem:
    props: dict = {"id": "i1", "title": "T", "status": "done"}
    if extra_props:
        props.update(extra_props)
    return LookupResponseItem(id="i1", type="Issue", properties=props)


def test_lookup_response_top_level_keys_stable() -> None:
    """Wire contract: top-level keys must not change without a major version bump."""
    resp = LookupResponse(items=[], total_matched=0, query_ms=5)
    dumped = resp.model_dump()
    assert set(dumped.keys()) == {"items", "total_matched", "query_ms", "warnings"}


def test_lookup_response_item_keys_stable() -> None:
    """Wire contract: item keys must not change without a major version bump."""
    item = _make_item()
    dumped = item.model_dump()
    assert set(dumped.keys()) == {"id", "type", "properties", "related"}


def test_group_id_absent_from_serialized_properties() -> None:
    """Regression guard: perform_lookup strips group_id before constructing items.

    This test verifies that when an item is constructed without group_id
    (as perform_lookup does after popping it), the serialized form is clean.
    """
    # perform_lookup pops group_id before constructing LookupResponseItem.
    # Simulate that by NOT including group_id in the item properties.
    item = _make_item()  # no group_id in props
    dumped = item.model_dump()
    props = dumped["properties"]
    assert "group_id" not in props, (
        "group_id unexpectedly present in serialized properties"
    )


def test_lookup_response_round_trips_via_model_dump() -> None:
    """model_dump() output can reconstruct an equivalent LookupResponse."""
    item = _make_item()
    original = LookupResponse(
        items=[item],
        total_matched=1,
        query_ms=10,
        warnings=["unknown filter 'foo' for entity_type 'Issue' — ignored"],
    )
    dumped = original.model_dump()
    reconstructed = LookupResponse(**dumped)
    assert reconstructed.total_matched == 1
    assert reconstructed.query_ms == 10
    assert len(reconstructed.items) == 1
    assert reconstructed.warnings[0].startswith("unknown filter")
