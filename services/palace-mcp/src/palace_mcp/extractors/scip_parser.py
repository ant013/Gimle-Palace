"""SCIP file parser + path resolver for symbol index extractors.

Vendored scip_pb2 (palace_mcp.proto.scip_pb2) generated from the official
Sourcegraph SCIP proto. protobuf>=4.25 pinned for upb backend (handles
files >64 MiB that the pure-Python backend cannot).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.protobuf.message import DecodeError

from palace_mcp.extractors.foundation.errors import ExtractorErrorCode
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
)
from palace_mcp.proto import scip_pb2


@dataclass
class ScipPathRequiredError(Exception):
    """No .scip path configured for this project."""

    project: str
    action_required: str
    error_code: str = ExtractorErrorCode.SCIP_PATH_REQUIRED.value

    def __post_init__(self) -> None:
        super().__init__(
            f"No .scip path for project {self.project!r}. {self.action_required}"
        )


@dataclass
class ScipFileTooLargeError(Exception):
    """SCIP file exceeds configured size cap."""

    path: Path
    size_mb: int
    cap_mb: int

    def __post_init__(self) -> None:
        super().__init__(
            f".scip file {self.path} is {self.size_mb} MB, exceeds cap {self.cap_mb} MB"
        )


@dataclass
class ScipParseError(Exception):
    """Protobuf decode failed on .scip file."""

    path: Path
    cause: str

    def __post_init__(self) -> None:
        super().__init__(f"Failed to parse {self.path}: {self.cause}")


class FindScipPath:
    """Resolve .scip file path for a project slug."""

    @staticmethod
    def resolve(
        project: str,
        settings: Any,
        override: str | None = None,
    ) -> Path:
        """Per-call override > Settings dict. Raises ScipPathRequiredError if neither."""
        if override is not None:
            return Path(override)
        path = settings.palace_scip_index_paths.get(project)
        if path is None:
            raise ScipPathRequiredError(
                project=project,
                action_required=(
                    f"Set PALACE_SCIP_INDEX_PATHS env var to JSON dict including "
                    f"'{project}' key, or pass scip_path argument to "
                    f"palace.ingest.run_extractor"
                ),
            )
        return Path(path)


def parse_scip_file(
    path: Path,
    max_size_mb: int = 500,
) -> Any:
    """Parse SCIP protobuf with size guard.

    Raises ScipFileTooLargeError if file exceeds max_size_mb.
    Raises ScipParseError on protobuf decode failure.
    Raises FileNotFoundError if path does not exist.
    """
    size = path.stat().st_size
    if size > max_size_mb * 1024 * 1024:
        raise ScipFileTooLargeError(
            path=path,
            size_mb=size // (1024 * 1024),
            cap_mb=max_size_mb,
        )
    data = path.read_bytes()
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    try:
        index.ParseFromString(data)
    except DecodeError as e:
        raise ScipParseError(path=path, cause=str(e)) from e
    return index


# ---------------------------------------------------------------------------
# SCIP role bitmask constants (from SymbolRole enum in scip.proto)
# ---------------------------------------------------------------------------

_SCIP_ROLE_DEF = 1
_SCIP_ROLE_IMPORT = 2
_SCIP_ROLE_WRITE_ACCESS = 4
_SCIP_ROLE_READ_ACCESS = 8
_SCIP_ROLE_GENERATED = 16
_SCIP_ROLE_TEST = 32
_SCIP_ROLE_FORWARD_DEF = 64


def _scip_role_to_kind(symbol_roles: int) -> SymbolKind:
    """Map SCIP symbol_roles bitmask to SymbolKind."""
    if symbol_roles & _SCIP_ROLE_DEF:
        return SymbolKind.DEF
    if symbol_roles & _SCIP_ROLE_FORWARD_DEF:
        return SymbolKind.DECL
    if symbol_roles & _SCIP_ROLE_WRITE_ACCESS:
        return SymbolKind.ASSIGN
    return SymbolKind.USE


def _extract_qualified_name(scip_symbol: str) -> str:
    """Strip scheme + manager + version, keep package-name + descriptors.

    SCIP format: '<scheme> <manager> <package-name> <version> <descriptors...>'
    Result format: '<package-name> <descriptors-joined>'

    Q1 FQN decision (GIM-105, Variant B): version token excluded so the same
    symbol from different library versions yields the same qualified_name.
    This is the input to symbol_id_for() — a version-stripped qualified_name.

    Splitting is backtick-aware (GIM-123): SCIP grammar permits identifiers
    with embedded spaces when wrapped in backticks (e.g. `` `operator T()` ``
    in scip-clang for C++ operator overloads). Splitting on raw spaces would
    fragment such identifiers and corrupt the qualified_name.
    """
    parts = _split_scip_top_level(scip_symbol.strip())
    if len(parts) < 5:
        return scip_symbol.strip()
    package_name = parts[2]
    descriptor_chain = " ".join(p for p in parts[4:] if p)
    return f"{package_name} {descriptor_chain}"


def _split_scip_top_level(symbol: str) -> list[str]:
    """Split a SCIP symbol string on top-level spaces, respecting backtick
    escapes per the SCIP grammar.

    A backtick toggles 'escaped identifier' mode. Inside escaped mode, a
    doubled backtick (``) represents a literal backtick within the
    identifier — both backticks stay together and do NOT toggle the mode.
    Spaces encountered inside escaped mode are preserved as part of the
    current token; only top-level spaces split tokens.

    Examples:
        "scip-python python pkg 1.0 a/b"          -> 5 tokens, naive case
        "x y `name with space` z"                 -> 4 tokens (escaped name kept whole)
        "x `a``b` y"                              -> 3 tokens (`` is literal backtick)
    """
    parts: list[str] = []
    cur: list[str] = []
    in_escape = False
    i = 0
    n = len(symbol)
    while i < n:
        c = symbol[i]
        if c == "`":
            # Inside escaped mode, a doubled backtick is a literal — consume
            # both characters as part of the current token without toggling.
            if in_escape and i + 1 < n and symbol[i + 1] == "`":
                cur.append("``")
                i += 2
                continue
            cur.append(c)
            in_escape = not in_escape
            i += 1
            continue
        if c == " " and not in_escape:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if cur:
        parts.append("".join(cur))
    return parts


_SCIP_LANGUAGE_MAP: dict[str, Language] = {
    "python": Language.PYTHON,
    "typescript": Language.TYPESCRIPT,
    "TypeScriptReact": Language.TYPESCRIPT,
    "javascript": Language.JAVASCRIPT,
    "JavaScriptReact": Language.JAVASCRIPT,
    "java": Language.JAVA,
    "kotlin": Language.KOTLIN,
    "solidity": Language.SOLIDITY,
}


def _language_from_path(relative_path: str) -> Language:
    """Fallback: derive language from file extension when doc.language is empty."""
    if relative_path.endswith((".ts", ".tsx")):
        return Language.TYPESCRIPT
    if relative_path.endswith((".js", ".jsx")):
        return Language.JAVASCRIPT
    if relative_path.endswith(".py"):
        return Language.PYTHON
    if relative_path.endswith(".java"):
        return Language.JAVA
    if relative_path.endswith((".kt", ".kts")):
        return Language.KOTLIN
    if relative_path.endswith(".sol"):
        return Language.SOLIDITY
    if relative_path.endswith(".swift"):
        return Language.SWIFT
    return Language.UNKNOWN


def iter_scip_occurrences(
    index: Any,  # scip_pb2.Index — no stub for generated protobuf
    *,
    commit_sha: str,
    ingest_run_id: str = "",
    language: Language | None = None,
) -> Iterator[SymbolOccurrence]:
    """Yield SymbolOccurrence from a parsed SCIP Index.

    Each SCIP Document maps to a file; each Occurrence within it maps to
    a SymbolOccurrence with file_path, line, col derived from the SCIP range.
    language= overrides per-document detection when explicitly provided.
    """
    for doc in index.documents:
        file_path = doc.relative_path

        if language is not None:
            doc_lang = language
        else:
            doc_lang_str = getattr(doc, "language", "")
            doc_lang = _SCIP_LANGUAGE_MAP.get(doc_lang_str, Language.UNKNOWN)
            if doc_lang == Language.UNKNOWN:
                doc_lang = _language_from_path(file_path)

        for occ in doc.occurrences:
            if not occ.symbol or occ.symbol.startswith("local "):
                continue

            kind = _scip_role_to_kind(occ.symbol_roles)
            qname = _extract_qualified_name(occ.symbol)
            sym_id = symbol_id_for(qname)

            range_vals = list(occ.range)
            line = range_vals[0] if len(range_vals) > 0 else 0
            col_start = range_vals[1] if len(range_vals) > 1 else 0

            if len(range_vals) == 3:
                col_end = range_vals[2]
            elif len(range_vals) == 4:
                col_end = range_vals[3]
            else:
                col_end = col_start

            if col_end < col_start:
                col_end = col_start

            doc_key = f"{sym_id}:{file_path}:{line}:{col_start}"

            yield SymbolOccurrence(
                doc_key=doc_key,
                symbol_id=sym_id,
                symbol_qualified_name=qname,
                kind=kind,
                language=doc_lang,
                file_path=file_path,
                line=line,
                col_start=col_start,
                col_end=col_end,
                importance=0.0,
                commit_sha=commit_sha,
                ingest_run_id=ingest_run_id,
            )
