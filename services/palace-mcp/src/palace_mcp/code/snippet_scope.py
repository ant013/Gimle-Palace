"""Multi-document assembly for get_code_snippet scope=file|type.

The single-symbol resolve/ambiguity/freshness logic stays in
native_get_code_snippet.py; this module owns the multi-file fan-out: which files
belong to a type, ordering, per-file whole-file reads, the size/count budget,
and per-document error capture. Kept graph-agnostic (the caller injects the
type-file lookup) so it is unit-testable without a live Neo4j.

Silent-failure contract: every truncation, drop, per-doc read failure and
scope downgrade is surfaced as a structured, top-level, machine-detectable
flag/count — never a bare boolean or a field reachable only inside documents[].
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from palace_mcp.code.snippet_provider import FreshnessResult, resolve_snippet

# Whole-file/type caps. Larger than the semantic-search hydration caps (200/16KB)
# but bounded so a huge file or a heavily-extended type cannot return megabytes.
_WHOLE_FILE_MAX_LINES = 1200
_WHOLE_FILE_MAX_BYTES = 64_000
_MAX_TOTAL_BYTES = 400_000
_MAX_TYPE_FILES = 12

# Kinds we treat as a "type" for whole_type. No `actor`/`extension` in the live
# writer vocabulary — unmapped kinds fall back to file scope (safe superset).
_TYPE_KINDS = frozenset({"class", "struct", "enum", "protocol"})

# Type-file discovery: moniker-prefix (extension members mangle under the base
# type moniker) guarded by module_name (belt-and-suspenders vs cross-module tail
# collisions). Owned here, executed by the caller which holds the session.
TYPE_FILES_QUERY = """
MATCH (m:Symbol)
WHERE m.group_id = $group_id
  AND m.module_name = $module_name
  AND m.qualified_name STARTS WITH $type_qn
WITH coalesce(m.file_path, m.path) AS file_path,
     sum(CASE WHEN m:Deprecated THEN 1 ELSE 0 END) AS dep_count,
     sum(CASE WHEN m:Deprecated THEN 0 ELSE 1 END) AS live_count
WHERE file_path IS NOT NULL
RETURN file_path, dep_count, live_count
""".strip()


@dataclass
class DocResult:
    file_path: str
    role: str  # "declaration" | "extension" | "file"
    source: str | None
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool
    truncated_lines: int
    truncated_reason: str | None
    language: str = ""
    error: str | None = None
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "role": self.role,
            "source": self.source,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "total_lines": self.total_lines,
            "truncated": self.truncated,
            "truncated_lines": self.truncated_lines,
            "truncated_reason": self.truncated_reason,
            "language": self.language,
            "error": self.error,
            "error_code": self.error_code,
        }


@dataclass
class ScopePlan:
    effective_scope: str  # "file" | "type"
    scope_downgraded: bool
    downgrade_reason: str | None


def plan_type_scope(kind: str, file_path: str) -> ScopePlan:
    """Decide the effective scope for a requested scope=type.

    Gate on file extension (reliable) not module_name. Non-Swift or non-type
    resolved symbols degrade to file scope (safe superset) — flagged, not silent.
    """
    if not file_path.endswith(".swift"):
        return ScopePlan("file", True, "whole_type is Swift-only (moniker model)")
    if kind not in _TYPE_KINDS:
        return ScopePlan(
            "file",
            True,
            "resolved symbol is a member, not a type; returned enclosing file",
        )
    return ScopePlan("type", False, None)


def order_type_files(declaration_file: str, files: list[str]) -> list[tuple[str, str]]:
    """Declaration file first (role=declaration), remaining lexicographic (extension).

    Lexicographic ordering is arbitrary w.r.t. relevance — hence dropped_files is
    reported as a path list, never a bare "kept the nearest N" count.
    """
    others = sorted(f for f in files if f != declaration_file)
    roles: list[tuple[str, str]] = []
    if declaration_file in files or not files:
        roles.append((declaration_file, "declaration"))
    return roles + [(f, "extension") for f in others]


def build_documents(
    file_roles: list[tuple[str, str]],
    *,
    project: str,
    repo_path: Path | None,
    commit_sha: str | None,
    freshness: FreshnessResult | None,
    resolve: Callable[..., tuple[Any, str | None, str | None]] | None = None,
) -> tuple[list[DocResult], dict[str, Any]]:
    """Read each (file, role) as a whole file under a shared byte budget.

    Returns (documents, rollup). rollup carries documents_total/failed/truncated
    and dropped_files (path list) — the honest, machine-detectable signals.
    """
    # Resolve at call time (not a default arg) so monkeypatching
    # snippet_scope.resolve_snippet in tests takes effect.
    resolve = resolve if resolve is not None else resolve_snippet
    dropped: list[str] = [fp for fp, _ in file_roles[_MAX_TYPE_FILES:]]
    capped = file_roles[:_MAX_TYPE_FILES]

    docs: list[DocResult] = []
    remaining = _MAX_TOTAL_BYTES
    failed = 0
    truncated_docs = 0

    for fp, role in capped:
        if remaining <= 0:
            dropped.append(fp)
            continue
        per_bytes = min(remaining, _WHOLE_FILE_MAX_BYTES)
        snip, code, msg = resolve(
            project=project,
            repo_path=repo_path,
            file_path=fp,
            line_start=1,
            line_end=None,
            commit_sha=commit_sha,
            freshness=freshness,
            max_lines=_WHOLE_FILE_MAX_LINES,
            max_bytes=per_bytes,
        )
        if snip is None:
            failed += 1
            docs.append(
                DocResult(
                    file_path=fp, role=role, source=None,
                    start_line=0, end_line=0, total_lines=0,
                    truncated=False, truncated_lines=0, truncated_reason=None,
                    error=msg, error_code=code,
                )
            )
            continue
        remaining -= snip.byte_count
        if snip.truncated:
            truncated_docs += 1
        docs.append(
            DocResult(
                file_path=fp, role=role, source=snip.source,
                start_line=snip.start_line, end_line=snip.end_line,
                total_lines=snip.total_lines, truncated=snip.truncated,
                truncated_lines=snip.truncated_lines,
                truncated_reason=snip.truncated_reason,
                language=getattr(snip, "language", ""),
            )
        )

    rollup = {
        "documents_total": len(docs),
        "documents_failed": failed,
        "documents_truncated": truncated_docs,
        "dropped_files": dropped,
    }
    return docs, rollup
