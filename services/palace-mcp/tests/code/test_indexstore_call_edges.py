from __future__ import annotations

from unittest.mock import patch

from palace_mcp.code import indexstore as _is
from palace_mcp.code.indexstore import (
    CallEdgeRecord,
    _ROLE_CALL,
    _ROLE_DECLARATION,
    _ROLE_DEFINITION,
    _ROLE_REFERENCE,
    _ROLE_REL_CALLEDBY,
    _ROLE_REL_CONTAINEDBY,
    _is_call_site,
    _resolve_call_edge,
    collect_call_edges,
)


class _FakeStringRef:
    def __init__(self, value: str) -> None:
        self._value = value

    def decode(self) -> str:
        return self._value


class _FakeBoundLib:
    UnitApplierF = staticmethod(lambda fn: fn)
    DepApplierF = staticmethod(lambda fn: fn)
    OccApplierF = staticmethod(lambda fn: fn)
    RelationApplierF = staticmethod(lambda fn: fn)

    def __init__(self, occurrences: list[dict[str, object]]) -> None:
        self._occurrences = occurrences

    def indexstore_store_create(self, *_: object) -> int:
        return 1

    def indexstore_store_dispose(self, *_: object) -> None:
        return None

    def indexstore_store_units_apply_f(self, *_: object) -> bool:
        callback = _[-1]
        return bool(callback(None, b"unit-1"))

    def indexstore_unit_reader_create(self, *_: object) -> object:
        return object()

    def indexstore_unit_reader_dispose(self, *_: object) -> None:
        return None

    def indexstore_unit_reader_dependencies_apply_f(self, *_: object) -> bool:
        callback = _[-1]
        dep = {"name": "rec-1"}
        return bool(callback(None, dep))

    def indexstore_unit_dependency_get_kind(self, *_: object) -> int:
        return _is._UNIT_DEP_RECORD

    def indexstore_unit_dependency_get_name(
        self, dep: dict[str, str]
    ) -> _FakeStringRef:
        return _FakeStringRef(dep["name"])

    def indexstore_record_reader_create(self, *_: object) -> object:
        return object()

    def indexstore_record_reader_dispose(self, *_: object) -> None:
        return None

    def indexstore_record_reader_occurrences_apply_f(self, *_: object) -> bool:
        callback = _[-1]
        for occurrence in self._occurrences:
            if callback(None, occurrence) is False:
                break
        return True

    def indexstore_occurrence_get_roles(self, occurrence: dict[str, object]) -> int:
        return int(occurrence["roles"])

    def indexstore_occurrence_get_symbol(
        self, occurrence: dict[str, object]
    ) -> dict[str, str]:
        return occurrence["symbol"]  # type: ignore[return-value]

    def indexstore_occurrence_relations_apply_f(
        self, occurrence: dict[str, object], *_: object
    ) -> bool:
        callback = _[-1]
        for relation in occurrence.get("relations", []):  # type: ignore[assignment]
            if callback(None, relation) is False:
                break
        return True

    def indexstore_symbol_get_usr(self, symbol: dict[str, str]) -> _FakeStringRef:
        return _FakeStringRef(symbol["usr"])

    def indexstore_symbol_relation_get_roles(self, relation: dict[str, object]) -> int:
        return int(relation["roles"])

    def indexstore_symbol_relation_get_symbol(
        self, relation: dict[str, object]
    ) -> dict[str, str]:
        return relation["symbol"]  # type: ignore[return-value]


def test_is_call_site_filters_non_call_roles() -> None:
    assert _is_call_site(_ROLE_CALL) is True
    assert _is_call_site(_ROLE_REFERENCE) is False
    assert _is_call_site(_ROLE_DECLARATION) is False
    assert _is_call_site(_ROLE_DEFINITION) is False


def test_resolve_call_edge_uses_swift_usr_bridge() -> None:
    edge = _resolve_call_edge(
        "s:10UwMiniCore1GVyyF",
        [
            (
                _ROLE_REL_CALLEDBY | _ROLE_REL_CONTAINEDBY,
                "s:10UwMiniCore1FVyyF",
            )
        ],
    )

    assert edge == CallEdgeRecord(
        source="UwMiniCore s%3A10UwMiniCore1FVyyF",
        target="UwMiniCore s%3A10UwMiniCore1GVyyF",
    )


def test_collect_call_edges_counts_missing_relation() -> None:
    fake_lib = _FakeBoundLib(
        [
            {
                "roles": _ROLE_REFERENCE,
                "symbol": {"usr": "s:10UwMiniCore1RVyyF"},
                "relations": [],
            },
            {
                "roles": _ROLE_CALL,
                "symbol": {"usr": "s:10UwMiniCore1GVyyF"},
                "relations": [
                    {
                        "roles": _ROLE_REL_CALLEDBY | _ROLE_REL_CONTAINEDBY,
                        "symbol": {"usr": "s:10UwMiniCore1FVyyF"},
                    }
                ],
            },
            {
                "roles": _ROLE_CALL,
                "symbol": {"usr": "s:10UwMiniCore1HVyyF"},
                "relations": [],
            },
        ]
    )

    with patch("palace_mcp.code.indexstore._get_lib", return_value=fake_lib):
        result = collect_call_edges("/tmp/fake-indexstore")

    assert result.edges == (
        CallEdgeRecord(
            source="UwMiniCore s%3A10UwMiniCore1FVyyF",
            target="UwMiniCore s%3A10UwMiniCore1GVyyF",
        ),
    )
    assert result.counters == {
        "calls_seen": 2,
        "missing_relation": 1,
    }
    assert result.records_scanned == 1
    assert result.occurrences_scanned == 3
