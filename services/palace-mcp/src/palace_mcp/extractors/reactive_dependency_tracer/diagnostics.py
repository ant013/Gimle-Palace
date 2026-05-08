"""Diagnostic helpers for reactive_dependency_tracer."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.reactive_dependency_tracer.identifiers import (
    diagnostic_id_for,
)
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    MAX_REDACTED_MESSAGE_LEN,
    DiagnosticSeverity,
    Range,
    ReactiveDiagnostic,
    ReactiveDiagnosticCode,
)


def redact_message(message: str) -> str:
    """Bound and sanitize diagnostic text for graph persistence."""

    home = str(Path.home())
    sanitized = message.replace(home, "~").replace("\r", " ").replace("\n", " ")
    return sanitized[:MAX_REDACTED_MESSAGE_LEN]


def build_diagnostic(
    *,
    group_id: str,
    project: str,
    commit_sha: str,
    run_id: str,
    language: Language,
    diagnostic_code: ReactiveDiagnosticCode,
    severity: DiagnosticSeverity,
    file_path: str | None = None,
    ref: str | None = None,
    message: str | None = None,
    range: Range | None = None,
) -> ReactiveDiagnostic:
    return ReactiveDiagnostic(
        id=diagnostic_id_for(
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
            diagnostic_code=diagnostic_code,
            file_path=file_path,
            ref=ref,
            range=range,
        ),
        group_id=group_id,
        project=project,
        commit_sha=commit_sha,
        run_id=run_id,
        language=language,
        file_path=file_path,
        ref=ref,
        diagnostic_code=diagnostic_code,
        severity=severity,
        message_redacted=redact_message(message) if message is not None else None,
        range=range,
    )
