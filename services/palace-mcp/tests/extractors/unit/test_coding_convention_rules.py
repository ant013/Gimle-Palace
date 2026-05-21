from __future__ import annotations

from palace_mcp.extractors.coding_convention.models import ConventionSignal
from palace_mcp.extractors.coding_convention.rules import (
    ConventionRule,
    load_rules,
    register_rules,
)


class _DuplicateTypeRule(ConventionRule):
    kind = "naming.type_class"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        return []


class _AnotherDuplicateTypeRule(ConventionRule):
    kind = "naming.type_class"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        return []


def test_load_rules_returns_deterministic_builtins() -> None:
    assert [rule.kind for rule in load_rules()] == [
        "async_cancel",
        "idiom.collection_init",
        "idiom.computed_vs_property",
        "naming.module_protocol",
        "naming.test_class",
        "naming.type_class",
        "structural.adt_pattern",
        "structural.error_modeling",
    ]


def test_register_rules_rejects_duplicate_kinds() -> None:
    try:
        register_rules((_DuplicateTypeRule(), _AnotherDuplicateTypeRule()))
    except ValueError as exc:
        assert str(exc) == "Duplicate coding convention rule kind: naming.type_class"
    else:
        raise AssertionError("duplicate rule kinds should fail fast")
