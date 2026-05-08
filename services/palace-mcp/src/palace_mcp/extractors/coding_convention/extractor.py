"""Coding convention extractor scaffolding (Roadmap #6)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorConfigError,
    ExtractorError,
    ExtractorRunContext,
    ExtractorRuntimeError,
    ExtractorStats,
)
from palace_mcp.extractors.coding_convention.models import (
    ConventionExtractionSummary,
    ConventionFinding,
    ConventionSignal,
    ConventionViolation,
)
from palace_mcp.extractors.coding_convention.neo4j_writer import (
    replace_project_snapshot,
)
from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run,
    finalize_ingest_run,
)

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

_STOP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".build",
        "build",
        "dist",
        "node_modules",
        "Pods",
        "Carthage",
        "SourcePackages",
        "DerivedData",
        "__pycache__",
    }
)
_SUPPORTED_SUFFIXES: frozenset[str] = frozenset({".swift", ".kt"})
_MIN_SAMPLE_COUNT = 5
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


class CodingConventionExtractor(BaseExtractor):
    """Scaffold for project-specific coding convention extraction."""

    name: ClassVar[str] = "coding_convention"
    description: ClassVar[str] = (
        "Detect dominant Swift and Kotlin coding conventions together with outliers."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX convention_lookup IF NOT EXISTS "
        "FOR (c:Convention) ON (c.project_id, c.module, c.kind)",
        "CREATE INDEX convention_violation_severity IF NOT EXISTS "
        "FOR (v:ConventionViolation) ON (v.project_id, v.severity)",
    ]

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        def severity_from_outlier_ratio(raw_value: object) -> Severity:
            if isinstance(raw_value, (int, float)):
                ratio = float(raw_value)
            elif isinstance(raw_value, str) and raw_value:
                ratio = float(raw_value)
            else:
                ratio = 0.0
            if ratio >= 0.1:
                return Severity.HIGH
            if ratio > 0:
                return Severity.MEDIUM
            return Severity.LOW

        return AuditContract(
            extractor_name="coding_convention",
            template_name="coding_convention.md",
            query="""
MATCH (c:Convention {project_id: $project})
OPTIONAL MATCH (v:ConventionViolation {
  project_id: $project,
  module: c.module,
  kind: c.kind
})
WITH c, collect(v {
  .file,
  .start_line,
  .end_line,
  .message,
  .severity
}) AS violations,
CASE
  WHEN c.sample_count < 5 THEN 0.0
  WHEN c.sample_count = 0 THEN 0.0
  ELSE toFloat(c.outliers) / toFloat(c.sample_count)
END AS outlier_ratio
RETURN c.module AS module,
       c.kind AS kind,
       c.dominant_choice AS dominant_choice,
       c.confidence AS confidence,
       c.sample_count AS sample_count,
       c.outliers AS outliers,
       violations AS violations,
       outlier_ratio AS outlier_ratio
ORDER BY outlier_ratio DESC, c.module, c.kind
LIMIT 100
""".strip(),
            severity_column="outlier_ratio",
            severity_mapper=severity_from_outlier_ratio,
        )

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        del graphiti
        from palace_mcp.mcp_server import get_driver

        driver = get_driver()
        if driver is None:
            raise ExtractorConfigError(
                "Neo4j driver not available for coding_convention"
            )

        await create_ingest_run(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            extractor_name=self.name,
        )

        try:
            summary = collect_conventions(
                project_id=ctx.project_slug,
                repo_path=ctx.repo_path,
                run_id=ctx.run_id,
            )
            await replace_project_snapshot(
                driver,
                project_id=ctx.project_slug,
                findings=summary.findings,
                violations=summary.violations,
            )
            await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
        except ExtractorError as exc:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code=exc.error_code,
            )
            raise
        except OSError as exc:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code="extractor_runtime_error",
            )
            raise ExtractorRuntimeError(str(exc)) from exc
        except Exception as exc:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code="unknown",
            )
            raise ExtractorRuntimeError(str(exc)) from exc

        return ExtractorStats(
            nodes_written=len(summary.findings) + len(summary.violations),
            edges_written=0,
        )


def collect_conventions(
    *, project_id: str, repo_path: Path, run_id: str
) -> ConventionExtractionSummary:
    grouped: dict[tuple[str, str], list[ConventionSignal]] = defaultdict(list)

    for path in _iter_source_files(repo_path):
        rel_path = path.relative_to(repo_path).as_posix()
        module = _infer_module(rel_path, project_id)
        text = path.read_text(encoding="utf-8")
        for signal in _extract_signals(module=module, rel_path=rel_path, text=text):
            grouped[(signal.module, signal.kind)].append(signal)

    findings: list[ConventionFinding] = []
    violations: list[ConventionViolation] = []
    for (module, kind), signals in sorted(grouped.items()):
        counts = Counter(signal.choice for signal in signals)
        dominant_choice, dominant_count = max(
            counts.items(), key=lambda item: (item[1], item[0])
        )
        sample_count = len(signals)
        if sample_count < _MIN_SAMPLE_COUNT:
            continue
        outliers = sample_count - dominant_count
        findings.append(
            ConventionFinding(
                project_id=project_id,
                module=module,
                kind=kind,
                dominant_choice=dominant_choice,
                confidence="heuristic",
                sample_count=sample_count,
                outliers=outliers,
                run_id=run_id,
            )
        )
        severity = _violation_severity(sample_count=sample_count, outliers=outliers)
        for signal in signals:
            if signal.choice == dominant_choice:
                continue
            violations.append(
                ConventionViolation(
                    project_id=project_id,
                    module=module,
                    kind=kind,
                    file=signal.file,
                    start_line=signal.start_line,
                    end_line=signal.end_line,
                    message=signal.message,
                    severity=severity,
                    run_id=run_id,
                )
            )

    return ConventionExtractionSummary(findings=findings, violations=violations)


def _iter_source_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file() or path.suffix not in _SUPPORTED_SUFFIXES:
            continue
        rel = path.relative_to(repo_path)
        if any(part in _STOP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files)


def _infer_module(rel_path: str, fallback: str) -> str:
    parts = rel_path.split("/")
    if "Sources" in parts:
        idx = parts.index("Sources")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if "Tests" in parts:
        idx = parts.index("Tests")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if "src" in parts:
        idx = parts.index("src")
        if idx > 0:
            return parts[idx - 1]
    return parts[0] if parts else fallback


def _extract_signals(
    *, module: str, rel_path: str, text: str
) -> list[ConventionSignal]:
    signals: list[ConventionSignal] = []
    is_test_file = _is_test_file(rel_path)

    for match in _SWIFT_TYPE_RE.finditer(text):
        signals.append(
            _build_signal(
                module=module,
                rel_path=rel_path,
                match=match,
                kind="naming.type_class",
                choice=_class_naming_choice(match.group("name")),
                name=match.group("name"),
            )
        )
    for match in _KOTLIN_TYPE_RE.finditer(text):
        signals.append(
            _build_signal(
                module=module,
                rel_path=rel_path,
                match=match,
                kind="naming.type_class",
                choice=_class_naming_choice(match.group("name")),
                name=match.group("name"),
            )
        )

    if is_test_file:
        for match in _SWIFT_TEST_CLASS_RE.finditer(text):
            signals.append(
                _build_signal(
                    module=module,
                    rel_path=rel_path,
                    match=match,
                    kind="naming.test_class",
                    choice=_test_class_choice(match.group("name")),
                    name=match.group("name"),
                )
            )
        for match in _KOTLIN_TEST_CLASS_RE.finditer(text):
            signals.append(
                _build_signal(
                    module=module,
                    rel_path=rel_path,
                    match=match,
                    kind="naming.test_class",
                    choice=_test_class_choice(match.group("name")),
                    name=match.group("name"),
                )
            )

    for match in _SWIFT_PROTOCOL_RE.finditer(text):
        signals.append(
            _build_signal(
                module=module,
                rel_path=rel_path,
                match=match,
                kind="naming.module_protocol",
                choice=_protocol_choice(match.group("name")),
                name=match.group("name"),
            )
        )
    for match in _KOTLIN_INTERFACE_RE.finditer(text):
        signals.append(
            _build_signal(
                module=module,
                rel_path=rel_path,
                match=match,
                kind="naming.module_protocol",
                choice=_protocol_choice(match.group("name")),
                name=match.group("name"),
            )
        )

    for match in _SWIFT_ENUM_RE.finditer(text):
        signals.append(
            _build_signal(
                module=module,
                rel_path=rel_path,
                match=match,
                kind="structural.adt_pattern",
                choice="enum",
                name=match.group("name"),
            )
        )
    for match in _KOTLIN_SEALED_RE.finditer(text):
        signals.append(
            _build_signal(
                module=module,
                rel_path=rel_path,
                match=match,
                kind="structural.adt_pattern",
                choice="sealed",
                name=match.group("name"),
            )
        )
    for match in _KOTLIN_ENUM_RE.finditer(text):
        signals.append(
            _build_signal(
                module=module,
                rel_path=rel_path,
                match=match,
                kind="structural.adt_pattern",
                choice="enum",
                name=match.group("name"),
            )
        )
    for match in _SWIFT_CLASS_HIERARCHY_RE.finditer(text):
        signals.append(
            _build_signal(
                module=module,
                rel_path=rel_path,
                match=match,
                kind="structural.adt_pattern",
                choice="class_hierarchy",
                name=match.group("name"),
            )
        )

    signals.extend(
        _pattern_signals(
            module=module,
            rel_path=rel_path,
            text=text,
            kind="structural.error_modeling",
            patterns=[
                (_SWIFT_THROWS_RE, "throws"),
                (_SWIFT_RESULT_RE, "result"),
                (_SWIFT_NULLABLE_RE, "nullable"),
                (_KOTLIN_RESULT_RE, "result"),
                (_KOTLIN_NULLABLE_RE, "nullable"),
            ],
        )
    )
    signals.extend(
        _pattern_signals(
            module=module,
            rel_path=rel_path,
            text=text,
            kind="idiom.collection_init",
            patterns=[
                (_SWIFT_COLLECTION_LITERAL_RE, "literal_empty"),
                (_SWIFT_COLLECTION_CONSTRUCTOR_RE, "constructor"),
                (_KOTLIN_COLLECTION_FACTORY_RE, "factory"),
                (_KOTLIN_COLLECTION_CONSTRUCTOR_RE, "constructor"),
            ],
        )
    )
    signals.extend(
        _pattern_signals(
            module=module,
            rel_path=rel_path,
            text=text,
            kind="idiom.computed_vs_property",
            patterns=[
                (_SWIFT_LAZY_RE, "lazy_property"),
                (_SWIFT_COMPUTED_RE, "computed_property"),
                (_KOTLIN_LAZY_RE, "lazy_property"),
                (_KOTLIN_COMPUTED_RE, "computed_property"),
            ],
        )
    )
    return signals


def _pattern_signals(
    *,
    module: str,
    rel_path: str,
    text: str,
    kind: str,
    patterns: list[tuple[re.Pattern[str], str]],
) -> list[ConventionSignal]:
    signals: list[ConventionSignal] = []
    for pattern, choice in patterns:
        for match in pattern.finditer(text):
            signals.append(
                _build_signal(
                    module=module,
                    rel_path=rel_path,
                    match=match,
                    kind=kind,
                    choice=choice,
                    name=choice,
                )
            )
    return signals


def _build_signal(
    *,
    module: str,
    rel_path: str,
    match: re.Match[str],
    kind: str,
    choice: str,
    name: str,
) -> ConventionSignal:
    line = match.string.count("\n", 0, match.start()) + 1
    return ConventionSignal(
        module=module,
        kind=kind,
        choice=choice,
        file=rel_path,
        start_line=line,
        end_line=line,
        message=f"{kind} prefers {choice}; found {name} in {rel_path}",
    )


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


def _violation_severity(*, sample_count: int, outliers: int) -> str:
    if outliers == 0:
        return "low"
    if sample_count >= 5 and (outliers / sample_count) >= 0.1:
        return "high"
    return "medium"
