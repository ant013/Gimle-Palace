from __future__ import annotations

import re

from palace_mcp.extractors.coding_convention.models import ConventionSignal
from palace_mcp.extractors.coding_convention.rules._base import (
    ConventionRule,
    build_signal,
)

_SWIFT_TYPE_RE = re.compile(
    r"^\s*(?:public|private|internal|fileprivate|open|final|indirect|static|\s)*"
    r"(class|struct)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_KOTLIN_TYPE_RE = re.compile(
    r"^\s*(?:public|private|internal|open|data|sealed|\s)*"
    r"(class|object)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_SWIFT_TEST_CLASS_RE = re.compile(
    r"^\s*(?:public|private|internal|final|\s)*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_KOTLIN_TEST_CLASS_RE = re.compile(
    r"^\s*(?:public|private|internal|open|data|\s)*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_SWIFT_PROTOCOL_RE = re.compile(
    r"^\s*(?:public|private|internal|\s)*protocol\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_KOTLIN_INTERFACE_RE = re.compile(
    r"^\s*(?:public|private|internal|sealed|\s)*interface\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_SWIFT_ENUM_RE = re.compile(
    r"^\s*(?:public|private|internal|indirect|\s)*enum\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_KOTLIN_SEALED_RE = re.compile(
    r"^\s*sealed\s+(class|interface)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_KOTLIN_ENUM_RE = re.compile(
    r"^\s*enum\s+class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_SWIFT_CLASS_HIERARCHY_RE = re.compile(
    r"^\s*(?:public|private|internal|open|final|\s)*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*",
    re.MULTILINE,
)
_SWIFT_THROWS_RE = re.compile(r"^\s*func\s+\w+\s*\([^)]*\)\s+throws\b", re.MULTILINE)
_SWIFT_RESULT_RE = re.compile(
    r"^\s*func\s+\w+\s*\([^)]*\)\s*->\s*Result<", re.MULTILINE
)
_SWIFT_NULLABLE_RE = re.compile(
    r"^\s*func\s+\w+\s*\([^)]*\)\s*->\s*[^=\n]+\?", re.MULTILINE
)
_KOTLIN_RESULT_RE = re.compile(r"^\s*fun\s+\w+\s*\([^)]*\)\s*:\s*Result<", re.MULTILINE)
_KOTLIN_NULLABLE_RE = re.compile(
    r"^\s*fun\s+\w+\s*\([^)]*\)\s*:\s*[^=\n]+\?", re.MULTILINE
)
_SWIFT_COLLECTION_LITERAL_RE = re.compile(r"=\s*\[\s*\]")
_SWIFT_COLLECTION_CONSTRUCTOR_RE = re.compile(
    r"=\s*(?:Array<[^>]+>\(\)|\[[^\]]+\]\(\))"
)
_KOTLIN_COLLECTION_FACTORY_RE = re.compile(r"=\s*(?:listOf|mutableListOf|emptyList)\(")
_KOTLIN_COLLECTION_CONSTRUCTOR_RE = re.compile(r"=\s*ArrayList(?:<[^>]+>)?\(")
_SWIFT_LAZY_RE = re.compile(r"^\s*lazy\s+var\s+(?P<name>\w+)", re.MULTILINE)
_SWIFT_COMPUTED_RE = re.compile(r"^\s*var\s+(?P<name>\w+)[^{=\n]*\{", re.MULTILINE)
_KOTLIN_LAZY_RE = re.compile(r"^\s*val\s+(?P<name>\w+).*by\s+lazy\s*\{", re.MULTILINE)
_KOTLIN_COMPUTED_RE = re.compile(
    r"^\s*val\s+(?P<name>\w+)[^=\n]*\s+get\(\)\s*=", re.MULTILINE
)


class TypeClassRule(ConventionRule):
    kind = "naming.type_class"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        signals: list[ConventionSignal] = []
        for pattern in (_SWIFT_TYPE_RE, _KOTLIN_TYPE_RE):
            for match in pattern.finditer(text):
                name = match.group("name")
                signals.append(
                    build_signal(
                        module=module,
                        rel_path=rel_path,
                        text=text,
                        offset=match.start(),
                        kind=self.kind,
                        choice=_class_naming_choice(name),
                        evidence=name,
                    )
                )
        return signals


class TestClassRule(ConventionRule):
    kind = "naming.test_class"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        if not _is_test_file(rel_path):
            return []

        signals: list[ConventionSignal] = []
        for pattern in (_SWIFT_TEST_CLASS_RE, _KOTLIN_TEST_CLASS_RE):
            for match in pattern.finditer(text):
                name = match.group("name")
                signals.append(
                    build_signal(
                        module=module,
                        rel_path=rel_path,
                        text=text,
                        offset=match.start(),
                        kind=self.kind,
                        choice=_test_class_choice(name),
                        evidence=name,
                    )
                )
        return signals


class ModuleProtocolRule(ConventionRule):
    kind = "naming.module_protocol"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        signals: list[ConventionSignal] = []
        for pattern in (_SWIFT_PROTOCOL_RE, _KOTLIN_INTERFACE_RE):
            for match in pattern.finditer(text):
                name = match.group("name")
                signals.append(
                    build_signal(
                        module=module,
                        rel_path=rel_path,
                        text=text,
                        offset=match.start(),
                        kind=self.kind,
                        choice=_protocol_choice(name),
                        evidence=name,
                    )
                )
        return signals


class AdtPatternRule(ConventionRule):
    kind = "structural.adt_pattern"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        signals: list[ConventionSignal] = []
        for pattern, choice in (
            (_SWIFT_ENUM_RE, "enum"),
            (_KOTLIN_SEALED_RE, "sealed"),
            (_KOTLIN_ENUM_RE, "enum"),
            (_SWIFT_CLASS_HIERARCHY_RE, "class_hierarchy"),
        ):
            for match in pattern.finditer(text):
                signals.append(
                    build_signal(
                        module=module,
                        rel_path=rel_path,
                        text=text,
                        offset=match.start(),
                        kind=self.kind,
                        choice=choice,
                        evidence=match.group("name"),
                    )
                )
        return signals


class ErrorModelingRule(ConventionRule):
    kind = "structural.error_modeling"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        return _pattern_signals(
            module=module,
            rel_path=rel_path,
            text=text,
            kind=self.kind,
            patterns=(
                (_SWIFT_THROWS_RE, "throws"),
                (_SWIFT_RESULT_RE, "result"),
                (_SWIFT_NULLABLE_RE, "nullable"),
                (_KOTLIN_RESULT_RE, "result"),
                (_KOTLIN_NULLABLE_RE, "nullable"),
            ),
        )


class CollectionInitRule(ConventionRule):
    kind = "idiom.collection_init"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        return _pattern_signals(
            module=module,
            rel_path=rel_path,
            text=text,
            kind=self.kind,
            patterns=(
                (_SWIFT_COLLECTION_LITERAL_RE, "literal_empty"),
                (_SWIFT_COLLECTION_CONSTRUCTOR_RE, "constructor"),
                (_KOTLIN_COLLECTION_FACTORY_RE, "factory"),
                (_KOTLIN_COLLECTION_CONSTRUCTOR_RE, "constructor"),
            ),
        )


class ComputedVsPropertyRule(ConventionRule):
    kind = "idiom.computed_vs_property"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        return _pattern_signals(
            module=module,
            rel_path=rel_path,
            text=text,
            kind=self.kind,
            patterns=(
                (_SWIFT_LAZY_RE, "lazy_property"),
                (_SWIFT_COMPUTED_RE, "computed_property"),
                (_KOTLIN_LAZY_RE, "lazy_property"),
                (_KOTLIN_COMPUTED_RE, "computed_property"),
            ),
        )


def _pattern_signals(
    *,
    module: str,
    rel_path: str,
    text: str,
    kind: str,
    patterns: tuple[tuple[re.Pattern[str], str], ...],
) -> list[ConventionSignal]:
    signals: list[ConventionSignal] = []
    for pattern, choice in patterns:
        for match in pattern.finditer(text):
            signals.append(
                build_signal(
                    module=module,
                    rel_path=rel_path,
                    text=text,
                    offset=match.start(),
                    kind=kind,
                    choice=choice,
                    evidence=choice,
                )
            )
    return signals


def _is_test_file(rel_path: str) -> bool:
    lowered = rel_path.lower()
    return (
        lowered.startswith("tests/")
        or lowered.startswith("test/")
        or "/tests/" in lowered
        or "/test/" in lowered
        or "/src/test/" in lowered
        or lowered.endswith("tests.swift")
    )


def _class_naming_choice(name: str) -> str:
    if name.upper() == name and "_" in name:
        return "upper_snake"
    if name[:1].isupper() and "_" not in name:
        return "upper_camel"
    return "other"


def _test_class_choice(name: str) -> str:
    if name.endswith("Tests"):
        return "suffix_tests"
    if name.startswith("Test"):
        return "prefix_test"
    if name.endswith("Spec"):
        return "suffix_spec"
    return "other"


def _protocol_choice(name: str) -> str:
    if name.endswith("Protocol"):
        return "suffix_protocol"
    if name.endswith("able"):
        return "suffix_able"
    if name.endswith("ing"):
        return "suffix_ing"
    return "other"


RULES = (
    TypeClassRule(),
    TestClassRule(),
    ModuleProtocolRule(),
    AdtPatternRule(),
    ErrorModelingRule(),
    CollectionInitRule(),
    ComputedVsPropertyRule(),
)
