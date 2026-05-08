from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from palace_mcp.extractors.testability_di.models import (
    DiStyle,
    DiPattern,
    FindingSeverity,
    Language,
    SourceFile,
    TestDouble,
    TestDoubleKind,
    UntestableSite,
    UntestableCategory,
)

_SWIFT_INIT_RE = re.compile(r"\binit\s*\([^)]*:\s*[A-Z][A-Za-z0-9_<>.?]*")
_KOTLIN_INIT_RE = re.compile(
    r"\bclass\s+\w+\s*\([^)]*:\s*[A-Z][A-Za-z0-9_<>.?]*",
    re.MULTILINE,
)
_SWIFT_PROPERTY_RE = re.compile(r"@(?:Injected|LazyInjected|InjectedObject)\b")
_KOTLIN_PROPERTY_RE = re.compile(r"@Inject\s+lateinit\s+var\b|\bby\s+inject\s*\(")
_SWIFT_SERVICE_LOCATOR_RE = re.compile(
    r"\b(?:ServiceLocator\.shared|Resolver\.(?:root|resolve)\b|\w+\.resolve\s*\()"
)
_KOTLIN_SERVICE_LOCATOR_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9_]*\.getInstance\s*\(\)|\b\w+\.get\s*\(\)"
)
_SWIFT_FRAMEWORKS: dict[str, re.Pattern[str]] = {
    "resolver": re.compile(r"\bimport\s+Resolver\b|@Injected\b"),
    "swinject": re.compile(r"\bimport\s+Swinject\b"),
    "factory": re.compile(r"\bimport\s+Factory\b"),
    "needle": re.compile(r"\bimport\s+NeedleFoundation\b"),
}
_KOTLIN_FRAMEWORKS: dict[str, re.Pattern[str]] = {
    "hilt": re.compile(r"\bdagger\.hilt\b|@InstallIn\b|SingletonComponent"),
    "dagger": re.compile(r"\bimport\s+dagger\.(?!hilt)"),
    "koin": re.compile(r"\bimport\s+org\.koin\b|\bby\s+inject\s*\("),
}
_SWIFT_DOUBLE_FRAMEWORKS: dict[TestDoubleKind, re.Pattern[str]] = {
    "cuckoo": re.compile(r"\bimport\s+Cuckoo\b"),
}
_KOTLIN_DOUBLE_FRAMEWORKS: dict[TestDoubleKind, re.Pattern[str]] = {
    "mockk": re.compile(r"\bmockk\s*<"),
    "mockito": re.compile(r"\bmock\s*<"),
}
_SWIFT_DOUBLE_DECL_RE = re.compile(
    r"\b(?:final\s+)?(?:class|struct|protocol)\s+"
    r"(?P<name>[A-Za-z0-9_]+?(?P<suffix>Fake|Stub|Spy|Mock))"
    r"(?:\s*:\s*(?P<target>[A-Za-z0-9_]+))?"
)
_KOTLIN_DOUBLE_DECL_RE = re.compile(
    r"\b(?:class|object|interface)\s+"
    r"(?P<name>[A-Za-z0-9_]+?(?P<suffix>Fake|Stub|Spy|Mock))"
    r"(?:\s*:\s*(?P<target>[A-Za-z0-9_]+))?"
)


def extract_di_patterns(
    sources: list[SourceFile], *, project_id: str, run_id: str
) -> list[DiPattern]:
    counts: Counter[tuple[str, Language, DiStyle, str | None]] = Counter()

    for source in sources:
        if source.is_test:
            continue
        if _matches_init_injection(source):
            counts[(source.module, source.language, "init_injection", None)] += 1
        if _matches_property_injection(source):
            counts[(source.module, source.language, "property_injection", None)] += 1
        for framework_name in _frameworks_for_source(source):
            counts[
                (source.module, source.language, "framework_bound", framework_name)
            ] += 1
        if not _is_composition_root(source) and _matches_service_locator(source):
            counts[(source.module, source.language, "service_locator", None)] += 1

    patterns: list[DiPattern] = []
    for key, sample_count in sorted(counts.items()):
        module = key[0]
        language = key[1]
        style = key[2]
        framework: str | None = key[3]
        patterns.append(
            DiPattern(
                project_id=project_id,
                module=module,
                language=language,
                style=style,
                framework=framework,
                sample_count=sample_count,
                outliers=0,
                confidence="heuristic",
                run_id=run_id,
            )
        )
    return patterns


def extract_test_doubles(
    sources: list[SourceFile], *, project_id: str, run_id: str
) -> list[TestDouble]:
    seen: set[tuple[str, Language, TestDoubleKind, str | None, str]] = set()
    findings: list[TestDouble] = []

    for source in sources:
        if not source.is_test:
            continue
        for framework_kind in _framework_double_kinds(source):
            key: tuple[str, Language, TestDoubleKind, str | None, str] = (
                source.module,
                source.language,
                framework_kind,
                None,
                source.relative_path,
            )
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                TestDouble(
                    project_id=project_id,
                    module=source.module,
                    language=source.language,
                    kind=framework_kind,
                    target_symbol=None,
                    test_file=source.relative_path,
                    run_id=run_id,
                )
            )
        for kind, target_symbol in _hand_rolled_double_matches(source):
            key = (
                source.module,
                source.language,
                kind,
                target_symbol,
                source.relative_path,
            )
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                TestDouble(
                    project_id=project_id,
                    module=source.module,
                    language=source.language,
                    kind=kind,
                    target_symbol=target_symbol,
                    test_file=source.relative_path,
                    run_id=run_id,
                )
            )
    return findings


def extract_untestable_sites(
    sources: list[SourceFile], *, project_id: str, run_id: str
) -> list[UntestableSite]:
    findings: list[UntestableSite] = []

    for source in sources:
        if source.is_test or _is_composition_root(source):
            continue
        for line_number, line in enumerate(source.text.splitlines(), start=1):
            for category, symbol, severity, message in _line_findings(source, line):
                findings.append(
                    UntestableSite(
                        project_id=project_id,
                        module=source.module,
                        language=source.language,
                        file=source.relative_path,
                        start_line=line_number,
                        end_line=line_number,
                        category=category,
                        symbol_referenced=symbol,
                        severity=severity,
                        message=message,
                        run_id=run_id,
                    )
                )
    return findings


def _matches_init_injection(source: SourceFile) -> bool:
    if source.language == "swift":
        return _SWIFT_INIT_RE.search(source.text) is not None
    return _KOTLIN_INIT_RE.search(source.text) is not None


def _matches_property_injection(source: SourceFile) -> bool:
    if source.language == "swift":
        return _SWIFT_PROPERTY_RE.search(source.text) is not None
    return _KOTLIN_PROPERTY_RE.search(source.text) is not None


def _matches_service_locator(source: SourceFile) -> bool:
    if source.language == "swift":
        return _SWIFT_SERVICE_LOCATOR_RE.search(source.text) is not None
    return _KOTLIN_SERVICE_LOCATOR_RE.search(source.text) is not None


def _frameworks_for_source(source: SourceFile) -> list[str]:
    patterns = _SWIFT_FRAMEWORKS if source.language == "swift" else _KOTLIN_FRAMEWORKS
    return [
        framework
        for framework, pattern in patterns.items()
        if pattern.search(source.text) is not None
    ]


def _framework_double_kinds(source: SourceFile) -> list[TestDoubleKind]:
    patterns = (
        _SWIFT_DOUBLE_FRAMEWORKS
        if source.language == "swift"
        else _KOTLIN_DOUBLE_FRAMEWORKS
    )
    return [
        kind
        for kind, pattern in patterns.items()
        if pattern.search(source.text) is not None
    ]


def _hand_rolled_double_matches(
    source: SourceFile,
) -> list[tuple[Literal["spy", "stub", "fake", "mock"], str | None]]:
    pattern = (
        _SWIFT_DOUBLE_DECL_RE if source.language == "swift" else _KOTLIN_DOUBLE_DECL_RE
    )
    matches: list[tuple[Literal["spy", "stub", "fake", "mock"], str | None]] = []
    for match in pattern.finditer(source.text):
        suffix = match.group("suffix")
        name = match.group("name")
        if suffix is None or name is None:
            continue
        target_symbol = match.group("target")
        if target_symbol is None:
            target_symbol = name[: -len(suffix)]
        matches.append((_double_kind_from_suffix(suffix), target_symbol))
    return matches


def _line_findings(
    source: SourceFile, line: str
) -> list[tuple[UntestableCategory, str, FindingSeverity, str]]:
    candidates: list[tuple[UntestableCategory, str, FindingSeverity, str]] = []
    if source.language == "swift":
        if "Date()" in line:
            candidates.append(_site(source, "direct_clock", "Date()"))
        if "Calendar.current" in line:
            candidates.append(_site(source, "direct_clock", "Calendar.current"))
        if "URLSession.shared" in line:
            candidates.append(_site(source, "direct_session", "URLSession.shared"))
        if "UserDefaults.standard" in line:
            candidates.append(
                _site(source, "direct_preferences", "UserDefaults.standard")
            )
        if "FileManager.default" in line:
            candidates.append(_site(source, "direct_filesystem", "FileManager.default"))
        if "ServiceLocator.shared" in line:
            candidates.append(_site(source, "service_locator", "ServiceLocator.shared"))
        return candidates

    if "Instant.now()" in line:
        candidates.append(_site(source, "direct_clock", "Instant.now()"))
    if "Calendar.getInstance()" in line:
        candidates.append(_site(source, "direct_clock", "Calendar.getInstance()"))
    if "SessionManager.getInstance()" in line:
        candidates.append(
            _site(source, "service_locator", "SessionManager.getInstance()")
        )
        return candidates
    if "Preferences.getInstance()" in line:
        candidates.append(
            _site(source, "direct_preferences", "Preferences.getInstance()")
        )
        return candidates
    generic_match = re.search(r"\b([A-Z][A-Za-z0-9_]*)\.getInstance\(\)", line)
    if generic_match is not None:
        symbol = generic_match.group(0)
        class_name = generic_match.group(1).lower()
        if "pref" in class_name:
            candidates.append(_site(source, "direct_preferences", symbol))
        elif "file" in class_name:
            candidates.append(_site(source, "direct_filesystem", symbol))
        elif "session" in class_name:
            candidates.append(_site(source, "direct_session", symbol))
        else:
            candidates.append(_site(source, "service_locator", symbol))
    return candidates


def _site(
    source: SourceFile, category: UntestableCategory, symbol: str
) -> tuple[UntestableCategory, str, FindingSeverity, str]:
    severity = "high" if category == "service_locator" else _resource_severity(source)
    message = (
        "Service locator usage hides dependencies from tests."
        if category == "service_locator"
        else f"Direct {symbol} access should be abstracted for tests."
    )
    return category, symbol, severity, message


def _resource_severity(source: SourceFile) -> FindingSeverity:
    critical_path_hints = ("wallet", "crypto", "seed", "key", "payment", "transaction")
    lowered_path = source.relative_path.lower()
    if any(hint in lowered_path for hint in critical_path_hints):
        return "high"
    return "medium"


def _double_kind_from_suffix(
    suffix: str,
) -> Literal["spy", "stub", "fake", "mock"]:
    lowered = suffix.lower()
    if lowered == "spy":
        return "spy"
    if lowered == "stub":
        return "stub"
    if lowered == "fake":
        return "fake"
    return "mock"


def _is_composition_root(source: SourceFile) -> bool:
    lowered = source.relative_path.lower()
    hints = (
        "appdelegate",
        "approot",
        "assembler",
        "assembly",
        "bootstrap",
        "compositionroot",
        "container",
        "di",
        "module",
        "scenedelegate",
    )
    return any(hint in lowered for hint in hints)
