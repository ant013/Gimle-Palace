"""Extractor orchestrator for reactive_dependency_tracer."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from graphiti_core import Graphiti

from palace_mcp.audit.contracts import Severity

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.reactive_dependency_tracer.diagnostics import (
    build_diagnostic,
    redact_message,
)
from palace_mcp.extractors.reactive_dependency_tracer.file_discovery import (
    DiscoveryResult,
    discover_reactive_files,
)
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    DiagnosticSeverity,
    ReactiveDiagnostic,
    ReactiveDiagnosticCode,
)
from palace_mcp.extractors.reactive_dependency_tracer.neo4j_writer import (
    write_reactive_graph,
)
from palace_mcp.extractors.reactive_dependency_tracer.normalizer import (
    NormalizedReactiveFile,
    normalize_swift_helper_file,
)
from palace_mcp.extractors.reactive_dependency_tracer.swift_helper_contract import (
    MAX_FILES_PER_RUN,
    SUPPORTED_SCHEMA_VERSION,
    SwiftHelperDocument,
    SwiftHelperFile,
    parse_swift_helper_contract,
)

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

_HELPER_JSON_FILENAME = "reactive_facts.json"

_AUDIT_QUERY = """\
MATCH (d:ReactiveDiagnostic {project: $project})
RETURN
    d.diagnostic_code   AS diagnostic_code,
    d.severity          AS severity,
    d.file_path         AS file_path,
    d.message_redacted  AS message,
    d.language          AS language,
    d.run_id            AS run_id
ORDER BY
    CASE d.severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
    d.file_path
"""


def _reactive_severity_mapper(value: str | None) -> Severity:
    mapping = {
        "error": Severity.HIGH,
        "warning": Severity.MEDIUM,
        "info": Severity.INFORMATIONAL,
    }
    return mapping.get(str(value).lower() if value else "", Severity.INFORMATIONAL)
_PATH_DIAGNOSTIC_CODES = {
    "path_empty": ReactiveDiagnosticCode.PATH_EMPTY,
    "path_parent_traversal": ReactiveDiagnosticCode.PATH_PARENT_TRAVERSAL,
    "path_absolute_outside_repo": ReactiveDiagnosticCode.PATH_ABSOLUTE_OUTSIDE_REPO,
    "path_symlink_escape": ReactiveDiagnosticCode.PATH_SYMLINK_ESCAPE,
    "path_windows_separator": ReactiveDiagnosticCode.PATH_WINDOWS_SEPARATOR,
    "invalid helper ref": ReactiveDiagnosticCode.INVALID_HELPER_REF,
    "helper_json_too_large": ReactiveDiagnosticCode.HELPER_JSON_TOO_LARGE,
    "max edges per file exceeded": ReactiveDiagnosticCode.MAX_EDGES_PER_FILE_EXCEEDED,
}


class ReactiveDependencyTracerExtractor(BaseExtractor):
    """Orchestrate discovery, helper parsing, normalization, and graph writes."""

    name: ClassVar[str] = "reactive_dependency_tracer"
    description: ClassVar[str] = (
        "Ingest pre-generated Swift reactive dependency facts and structured "
        "skip diagnostics into Neo4j."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT reactive_component_id_unique IF NOT EXISTS "
        "FOR (n:ReactiveComponent) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT reactive_state_id_unique IF NOT EXISTS "
        "FOR (n:ReactiveState) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT reactive_effect_id_unique IF NOT EXISTS "
        "FOR (n:ReactiveEffect) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT reactive_diagnostic_id_unique IF NOT EXISTS "
        "FOR (n:ReactiveDiagnostic) REQUIRE n.id IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX reactive_component_lookup IF NOT EXISTS "
        "FOR (n:ReactiveComponent) ON (n.project, n.commit_sha, n.language, n.file_path)",
        "CREATE INDEX reactive_state_lookup IF NOT EXISTS "
        "FOR (n:ReactiveState) ON (n.project, n.commit_sha, n.language, n.file_path)",
        "CREATE INDEX reactive_effect_lookup IF NOT EXISTS "
        "FOR (n:ReactiveEffect) ON (n.component_id, n.effect_kind)",
        "CREATE INDEX reactive_diagnostic_lookup IF NOT EXISTS "
        "FOR (n:ReactiveDiagnostic) ON (n.project, n.commit_sha, n.language, n.file_path, n.diagnostic_code)",
    ]

    def audit_contract(self) -> AuditContract:
        from palace_mcp.audit.contracts import AuditContract

        return AuditContract(
            extractor_name="reactive_dependency_tracer",
            template_name="reactive_dependency_tracer.md",
            query=_AUDIT_QUERY,
            severity_column="severity",
            max_findings=50,
            severity_mapper=_reactive_severity_mapper,
        )

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        del graphiti
        from palace_mcp.mcp_server import get_driver

        driver = get_driver()
        if driver is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available — call set_driver() before run_extractor",
                recoverable=False,
                action="retry",
            )

        await ensure_custom_schema(driver)

        commit_sha = _read_head_sha(ctx.repo_path)
        discovery = discover_reactive_files(
            repo_root=ctx.repo_path,
            group_id=ctx.group_id,
            project=ctx.project_slug,
            commit_sha=commit_sha,
            run_id=ctx.run_id,
        )
        batches = _diagnostic_batches_from_discovery(discovery)

        if not discovery.swift_files:
            summary = await write_reactive_graph(driver=driver, batches=tuple(batches))
            return ExtractorStats(
                nodes_written=summary.nodes_created,
                edges_written=summary.relationships_created,
            )

        helper_path = ctx.repo_path / _HELPER_JSON_FILENAME
        if not helper_path.exists():
            batches.append(
                _run_diagnostic_batch(
                    group_id=ctx.group_id,
                    project=ctx.project_slug,
                    commit_sha=commit_sha,
                    run_id=ctx.run_id,
                    diagnostic_code=ReactiveDiagnosticCode.SWIFT_HELPER_UNAVAILABLE,
                    severity=DiagnosticSeverity.WARNING,
                    message=(
                        f"Expected pre-generated helper JSON at {_HELPER_JSON_FILENAME}"
                    ),
                )
            )
            summary = await write_reactive_graph(driver=driver, batches=tuple(batches))
            return ExtractorStats(
                nodes_written=summary.nodes_created,
                edges_written=summary.relationships_created,
            )

        try:
            parsed = _parse_helper_payload(
                helper_path.read_text(encoding="utf-8"),
                repo_root=ctx.repo_path,
            )
        except ValueError as exc:
            batches.append(
                _run_diagnostic_batch(
                    group_id=ctx.group_id,
                    project=ctx.project_slug,
                    commit_sha=commit_sha,
                    run_id=ctx.run_id,
                    diagnostic_code=_diagnostic_code_for_message(str(exc)),
                    severity=DiagnosticSeverity.ERROR,
                    message=redact_message(str(exc)),
                )
            )
            summary = await write_reactive_graph(driver=driver, batches=tuple(batches))
            return ExtractorStats(
                nodes_written=summary.nodes_created,
                edges_written=summary.relationships_created,
            )

        for diagnostic in parsed.run_diagnostics:
            batches.append(
                _diagnostic_batch_from_helper_diagnostic(
                    diagnostic=diagnostic,
                    group_id=ctx.group_id,
                    project=ctx.project_slug,
                    commit_sha=commit_sha,
                    run_id=ctx.run_id,
                )
            )

        for failure in parsed.file_failures:
            batches.append(
                _file_failure_batch(
                    group_id=ctx.group_id,
                    project=ctx.project_slug,
                    commit_sha=commit_sha,
                    run_id=ctx.run_id,
                    file_path=failure.file_path,
                    diagnostic_code=failure.diagnostic_code,
                    message=failure.message,
                )
            )

        for helper_file in parsed.files:
            component_symbol_keys = await _lookup_component_symbol_keys(
                driver=driver,
                group_id=ctx.group_id,
                project=ctx.project_slug,
                commit_sha=commit_sha,
                language=Language.SWIFT,
                helper_file=helper_file,
            )
            batches.append(
                normalize_swift_helper_file(
                    helper_file,
                    group_id=ctx.group_id,
                    project=ctx.project_slug,
                    commit_sha=commit_sha,
                    run_id=ctx.run_id,
                    language=Language.SWIFT,
                    component_symbol_keys=component_symbol_keys,
                )
            )

        summary = await write_reactive_graph(driver=driver, batches=tuple(batches))
        return ExtractorStats(
            nodes_written=summary.nodes_created,
            edges_written=summary.relationships_created,
        )


class _ParsedHelperPayload:
    def __init__(
        self,
        *,
        files: tuple[SwiftHelperFile, ...],
        run_diagnostics: tuple[Any, ...],
        file_failures: tuple["_FileFailure", ...],
    ) -> None:
        self.files = files
        self.run_diagnostics = run_diagnostics
        self.file_failures = file_failures


class _FileFailure:
    def __init__(
        self,
        *,
        file_path: str | None,
        diagnostic_code: ReactiveDiagnosticCode,
        message: str,
    ) -> None:
        self.file_path = file_path
        self.diagnostic_code = diagnostic_code
        self.message = message


def _diagnostic_batches_from_discovery(
    discovery: DiscoveryResult,
) -> list[NormalizedReactiveFile]:
    grouped: dict[tuple[str | None, Language], list[ReactiveDiagnostic]] = defaultdict(
        list
    )
    for diagnostic in discovery.diagnostics:
        grouped[(diagnostic.file_path, diagnostic.language)].append(diagnostic)

    batches: list[NormalizedReactiveFile] = []
    for (file_path, language), diagnostics in sorted(
        grouped.items(), key=lambda item: (item[0][0] or "", item[0][1].value)
    ):
        batches.append(
            NormalizedReactiveFile(
                file_path=file_path,
                language=language,
                components=(),
                states=(),
                effects=(),
                edges=(),
                diagnostics=tuple(diagnostics),
                ref_to_node_id={},
            )
        )
    return batches


def _run_diagnostic_batch(
    *,
    group_id: str,
    project: str,
    commit_sha: str,
    run_id: str,
    diagnostic_code: ReactiveDiagnosticCode,
    severity: DiagnosticSeverity,
    message: str,
) -> NormalizedReactiveFile:
    diagnostic = build_diagnostic(
        group_id=group_id,
        project=project,
        commit_sha=commit_sha,
        run_id=run_id,
        language=Language.SWIFT,
        diagnostic_code=diagnostic_code,
        severity=severity,
        file_path=None,
        message=message,
    )
    return NormalizedReactiveFile(
        file_path=None,
        language=Language.SWIFT,
        components=(),
        states=(),
        effects=(),
        edges=(),
        diagnostics=(diagnostic,),
        ref_to_node_id={},
    )


def _diagnostic_batch_from_helper_diagnostic(
    *,
    diagnostic: Any,
    group_id: str,
    project: str,
    commit_sha: str,
    run_id: str,
) -> NormalizedReactiveFile:
    persisted = build_diagnostic(
        group_id=group_id,
        project=project,
        commit_sha=commit_sha,
        run_id=run_id,
        language=Language.SWIFT,
        diagnostic_code=diagnostic.code,
        severity=diagnostic.severity,
        file_path=None,
        ref=diagnostic.ref,
        range=diagnostic.range,
        message=diagnostic.message,
    )
    return NormalizedReactiveFile(
        file_path=None,
        language=Language.SWIFT,
        components=(),
        states=(),
        effects=(),
        edges=(),
        diagnostics=(persisted,),
        ref_to_node_id={},
    )


def _file_failure_batch(
    *,
    group_id: str,
    project: str,
    commit_sha: str,
    run_id: str,
    file_path: str | None,
    diagnostic_code: ReactiveDiagnosticCode,
    message: str,
) -> NormalizedReactiveFile:
    diagnostic = build_diagnostic(
        group_id=group_id,
        project=project,
        commit_sha=commit_sha,
        run_id=run_id,
        language=Language.SWIFT,
        diagnostic_code=diagnostic_code,
        severity=DiagnosticSeverity.ERROR,
        file_path=file_path,
        message=message,
    )
    return NormalizedReactiveFile(
        file_path=file_path,
        language=Language.SWIFT,
        components=(),
        states=(),
        effects=(),
        edges=(),
        diagnostics=(diagnostic,),
        ref_to_node_id={},
        replace_existing_facts=False,
    )


def _parse_helper_payload(payload: str, *, repo_root: Path) -> _ParsedHelperPayload:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise ValueError("top-level helper payload must be an object")

    raw_schema_version = raw.get("schema_version")
    if raw_schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"schema_version {raw_schema_version} is unsupported")

    try:
        envelope = SwiftHelperDocument.model_validate(
            {
                **raw,
                "files": (),
            }
        )
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    raw_files = raw.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("files must be an array")
    if len(raw_files) > MAX_FILES_PER_RUN:
        raise ValueError("max files per run exceeded")

    parsed_files: list[SwiftHelperFile] = []
    file_failures: list[_FileFailure] = []
    top_level: dict[str, Any] = {
        "tool_name": envelope.tool_name,
        "tool_version": envelope.tool_version,
        "schema_version": envelope.schema_version,
        "swift_syntax_version": envelope.swift_syntax_version,
        "swift_toolchain": envelope.swift_toolchain,
        "run_diagnostics": [],
    }
    for raw_file in raw_files:
        try:
            parsed = parse_swift_helper_contract(
                json.dumps({**top_level, "files": [raw_file]}),
                repo_root=repo_root,
            )
        except ValueError as exc:
            file_failures.append(
                _FileFailure(
                    file_path=_safe_failure_path(raw_file),
                    diagnostic_code=_diagnostic_code_for_message(str(exc)),
                    message=redact_message(str(exc)),
                )
            )
            continue
        parsed_files.append(parsed.files[0])

    return _ParsedHelperPayload(
        files=tuple(parsed_files),
        run_diagnostics=envelope.run_diagnostics,
        file_failures=tuple(file_failures),
    )


def _safe_failure_path(raw_file: object) -> str | None:
    if not isinstance(raw_file, dict):
        return None
    path = raw_file.get("path")
    if not isinstance(path, str):
        return None
    stripped = path.strip()
    if (
        not stripped
        or "\\" in stripped
        or stripped.startswith("/")
        or stripped.startswith("~")
        or ".." in Path(stripped).parts
    ):
        return None
    return Path(stripped).as_posix()


def _diagnostic_code_for_message(message: str) -> ReactiveDiagnosticCode:
    if "schema_version" in message and "unsupported" in message:
        return ReactiveDiagnosticCode.SWIFT_HELPER_VERSION_UNSUPPORTED
    for needle, code in _PATH_DIAGNOSTIC_CODES.items():
        if needle in message:
            return code
    return ReactiveDiagnosticCode.SWIFT_PARSE_FAILED


async def _lookup_component_symbol_keys(
    *,
    driver: Any,
    group_id: str,
    project: str,
    commit_sha: str,
    language: Language,
    helper_file: SwiftHelperFile,
) -> dict[str, str]:
    entries = [
        {
            "component_ref": component.component_ref,
            "symbol_key": component.qualified_name,
            "symbol_id": symbol_id_for(component.qualified_name),
        }
        for component in helper_file.components
    ]
    if not entries:
        return {}

    async with driver.session() as session:
        rows = await session.execute_read(
            _read_component_symbol_matches,
            entries=entries,
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
            language=language.value,
        )

    return {
        row["component_ref"]: row["symbol_key"]
        for row in rows
        if row["has_match"] is True
    }


async def _read_component_symbol_matches(
    tx: Any, **params: object
) -> list[dict[str, object]]:
    result = await tx.run(
        """
        UNWIND $entries AS entry
        OPTIONAL MATCH (shadow:SymbolOccurrenceShadow {
            group_id: $group_id,
            symbol_id: entry.symbol_id,
            symbol_qualified_name: entry.symbol_key
        })
        WITH entry, count(shadow) AS shadow_matches
        OPTIONAL MATCH (public:PublicApiSymbol {
            project: $project,
            commit_sha: $commit_sha,
            language: $language,
            symbol_qualified_name: entry.symbol_key
        })
        WITH entry, shadow_matches, count(public) AS public_matches
        RETURN entry.component_ref AS component_ref,
               entry.symbol_key AS symbol_key,
               shadow_matches > 0 OR public_matches > 0 AS has_match
        """,
        **params,
    )
    rows = await result.data()
    return [
        {
            "component_ref": row["component_ref"],
            "symbol_key": row["symbol_key"],
            "has_match": row["has_match"],
        }
        for row in rows
    ]


def _read_head_sha(repo_path: Path) -> str:
    try:
        git_dir, refs_root = _resolve_git_dirs(repo_path)
    except (FileNotFoundError, OSError, ValueError):
        return "unknown"

    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "unknown"
    if not head.startswith("ref: "):
        return head[:40]
    ref_name = head.removeprefix("ref: ").strip()
    ref_path = refs_root / ref_name
    try:
        return ref_path.read_text(encoding="utf-8").strip()[:40]
    except FileNotFoundError:
        return _read_packed_ref(refs_root, ref_name)


def _resolve_git_dirs(repo_path: Path) -> tuple[Path, Path]:
    git_path = repo_path / ".git"
    if git_path.is_dir():
        git_dir = git_path
    else:
        pointer = git_path.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise ValueError("invalid gitdir pointer")
        git_dir = (repo_path / pointer.removeprefix("gitdir: ").strip()).resolve()

    commondir_path = git_dir / "commondir"
    if commondir_path.exists():
        common_dir = (
            git_dir / commondir_path.read_text(encoding="utf-8").strip()
        ).resolve()
        return git_dir, common_dir
    return git_dir, git_dir


def _read_packed_ref(refs_root: Path, ref_name: str) -> str:
    packed_refs_path = refs_root / "packed-refs"
    try:
        for line in packed_refs_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "^")):
                continue
            sha, _, packed_ref_name = stripped.partition(" ")
            if packed_ref_name == ref_name:
                return sha[:40]
    except FileNotFoundError:
        return "unknown"
    return "unknown"
