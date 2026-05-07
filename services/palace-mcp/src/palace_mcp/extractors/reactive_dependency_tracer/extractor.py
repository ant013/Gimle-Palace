"""Extractor orchestrator for reactive_dependency_tracer."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
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
    parse_swift_helper_contract,
)

_HELPER_JSON_FILENAME = "reactive_facts.json"


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
            document = parse_swift_helper_contract(
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
                    diagnostic_code=ReactiveDiagnosticCode.SWIFT_PARSE_FAILED,
                    severity=DiagnosticSeverity.ERROR,
                    message=redact_message(str(exc)),
                )
            )
            summary = await write_reactive_graph(driver=driver, batches=tuple(batches))
            return ExtractorStats(
                nodes_written=summary.nodes_created,
                edges_written=summary.relationships_created,
            )

        for helper_file in document.files:
            batches.append(
                normalize_swift_helper_file(
                    helper_file,
                    group_id=ctx.group_id,
                    project=ctx.project_slug,
                    commit_sha=commit_sha,
                    run_id=ctx.run_id,
                    language=Language.SWIFT,
                    component_symbol_keys={},
                )
            )

        summary = await write_reactive_graph(driver=driver, batches=tuple(batches))
        return ExtractorStats(
            nodes_written=summary.nodes_created,
            edges_written=summary.relationships_created,
        )


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
