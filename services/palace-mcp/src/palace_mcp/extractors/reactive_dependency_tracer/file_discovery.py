"""Swift/Kotlin file discovery for reactive_dependency_tracer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.reactive_dependency_tracer.diagnostics import (
    build_diagnostic,
)
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    DiagnosticSeverity,
    ReactiveDiagnostic,
    ReactiveDiagnosticCode,
)

DEFAULT_MAX_SWIFT_FILE_BYTES = 256 * 1024
_PRUNE_DIRS = frozenset({".git", ".build", ".swiftpm", "build", "DerivedData", "Pods"})
_GENERATED_OR_VENDOR_MARKERS = frozenset(
    {"generated", "vendor", "vendors", "pods", "deriveddata"}
)


@dataclass(frozen=True)
class DiscoveryResult:
    """Reactive source discovery output."""

    swift_files: tuple[Path, ...]
    kotlin_files: tuple[str, ...]
    diagnostics: tuple[ReactiveDiagnostic, ...]


def _rel_path(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _is_ignored(relative_path: str, ignore_paths: tuple[str, ...]) -> bool:
    return any(
        relative_path == ignored or relative_path.startswith(f"{ignored}/")
        for ignored in ignore_paths
    )


def discover_reactive_files(
    *,
    repo_root: Path,
    ignore_paths: tuple[str, ...] = (),
    max_swift_file_bytes: int = DEFAULT_MAX_SWIFT_FILE_BYTES,
    group_id: str = "discovery",
    project: str = "discovery",
    commit_sha: str = "discovery",
    run_id: str = "discovery",
) -> DiscoveryResult:
    """Discover Swift files and emit structured skip diagnostics."""

    swift_files: list[Path] = []
    kotlin_files: list[str] = []
    diagnostics: list[ReactiveDiagnostic] = []

    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue

        relative_path = _rel_path(path, repo_root)
        if _is_ignored(relative_path, ignore_paths):
            continue

        lower_parts = {part.lower() for part in path.relative_to(repo_root).parts[:-1]}
        if any(part in _PRUNE_DIRS for part in path.relative_to(repo_root).parts[:-1]):
            if path.suffix == ".swift":
                diagnostics.append(
                    build_diagnostic(
                        group_id=group_id,
                        project=project,
                        commit_sha=commit_sha,
                        run_id=run_id,
                        language=Language.SWIFT,
                        diagnostic_code=ReactiveDiagnosticCode.SWIFT_GENERATED_OR_VENDOR_SKIPPED,
                        severity=DiagnosticSeverity.INFO,
                        file_path=relative_path,
                        message=f"Skipped generated or vendor Swift file: {relative_path}",
                    )
                )
            continue

        if lower_parts & _GENERATED_OR_VENDOR_MARKERS:
            if path.suffix == ".swift":
                diagnostics.append(
                    build_diagnostic(
                        group_id=group_id,
                        project=project,
                        commit_sha=commit_sha,
                        run_id=run_id,
                        language=Language.SWIFT,
                        diagnostic_code=ReactiveDiagnosticCode.SWIFT_GENERATED_OR_VENDOR_SKIPPED,
                        severity=DiagnosticSeverity.INFO,
                        file_path=relative_path,
                        message=f"Skipped generated or vendor Swift file: {relative_path}",
                    )
                )
            continue

        if path.suffix == ".swift":
            if path.stat().st_size > max_swift_file_bytes:
                diagnostics.append(
                    build_diagnostic(
                        group_id=group_id,
                        project=project,
                        commit_sha=commit_sha,
                        run_id=run_id,
                        language=Language.SWIFT,
                        diagnostic_code=ReactiveDiagnosticCode.SWIFT_FILE_TOO_LARGE,
                        severity=DiagnosticSeverity.WARNING,
                        file_path=relative_path,
                        message=f"Swift file exceeded size cap: {relative_path}",
                    )
                )
                continue
            swift_files.append(Path(relative_path))
            continue

        if path.suffix == ".kt":
            kotlin_files.append(relative_path)
            diagnostics.append(
                build_diagnostic(
                    group_id=group_id,
                    project=project,
                    commit_sha=commit_sha,
                    run_id=run_id,
                    language=Language.KOTLIN,
                    diagnostic_code=ReactiveDiagnosticCode.KOTLIN_TOOLING_UNAVAILABLE,
                    severity=DiagnosticSeverity.INFO,
                    file_path=relative_path,
                    message=f"Kotlin reactive extraction is deferred in v1: {relative_path}",
                )
            )
            contents = path.read_text(encoding="utf-8")
            if "@Composable" in contents or "androidx.compose" in contents:
                diagnostics.append(
                    build_diagnostic(
                        group_id=group_id,
                        project=project,
                        commit_sha=commit_sha,
                        run_id=run_id,
                        language=Language.KOTLIN,
                        diagnostic_code=ReactiveDiagnosticCode.COMPOSE_STABILITY_REPORT_UNAVAILABLE,
                        severity=DiagnosticSeverity.INFO,
                        file_path=relative_path,
                        message=(
                            "Compose stability contract ingestion is deferred in v1: "
                            f"{relative_path}"
                        ),
                    )
                )

    return DiscoveryResult(
        swift_files=tuple(swift_files),
        kotlin_files=tuple(kotlin_files),
        diagnostics=tuple(diagnostics),
    )
