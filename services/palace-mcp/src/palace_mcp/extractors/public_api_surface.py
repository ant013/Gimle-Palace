"""Public API surface extractor for Kotlin `.api` and Swift `.swiftinterface` artifacts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from graphiti_core import Graphiti
from neo4j import AsyncDriver, AsyncSession

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import (
    Language,
    PublicApiArtifactKind,
    PublicApiSurface,
    PublicApiSymbol,
    PublicApiSymbolKind,
    PublicApiVisibility,
)

_ARTIFACT_ROOT = Path(".palace/public-api")
_KOTLIN_ARTIFACT_DIR = _ARTIFACT_ROOT / "kotlin"
_SWIFT_ARTIFACT_DIR = _ARTIFACT_ROOT / "swift"
_KOTLIN_TOOL_HEADER = re.compile(r"^//\s*tool:\s*(?P<name>\S+)\s+(?P<version>.+)$")
_KOTLIN_TYPE = re.compile(
    r"^(?P<visibility>public|protected)\s+"
    r"(?P<mods>(?:\w+\s+)*)"
    r"(?P<kind>class|interface|object)\s+"
    r"(?P<fqn>[\w.$]+)\s*\{$"
)
_KOTLIN_CONSTRUCTOR = re.compile(
    r"^(?P<visibility>public|protected)\s+constructor(?:\s+\w+)?\((?P<params>.*)\)$"
)
_KOTLIN_FUNCTION = re.compile(
    r"^(?P<visibility>public|protected)\s+"
    r"(?P<mods>(?:\w+\s+)*)fun\s+"
    r"(?P<name>[\w$<>]+)\((?P<params>.*)\)"
    r"(?::\s*(?P<return_type>.+))?$"
)
_KOTLIN_PROPERTY = re.compile(
    r"^(?P<visibility>public|protected)\s+"
    r"(?P<mods>(?:\w+\s+)*)"
    r"(?P<kind>val|var)\s+"
    r"(?P<name>[\w$]+):\s*(?P<value_type>.+)$"
)
_SWIFT_COMPILER_HEADER = re.compile(r"^//\s*swift-compiler-version:\s*(?P<version>.+)$")
_SWIFT_NAMED_DECL = re.compile(
    r"^(?P<visibility>public|open|package)\s+"
    r"(?P<kind>struct|class|enum|protocol|typealias)\s+"
    r"(?P<name>[A-Za-z_][\w.]*)"
)
_SWIFT_EXTENSION = re.compile(
    r"^(?:(?P<visibility>public|package)\s+)?extension\s+(?P<name>[A-Za-z_][\w.]*)\s*\{$"
)
_SWIFT_FUNCTION = re.compile(
    r"^(?P<visibility>public|open|package)\s+func\s+"
    r"(?P<name>[A-Za-z_][\w]*)\((?P<params>[^)]*)\)"
)
_SWIFT_INIT = re.compile(
    r"^(?P<visibility>public|open|package)\s+init\((?P<params>[^)]*)\)"
)
_SWIFT_PROPERTY = re.compile(
    r"^(?P<visibility>public|open|package)\s+"
    r"(?P<kind>var|let)\s+"
    r"(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<value_type>.+?)(?:\s*\{.*)?$"
)
_WRITE_SURFACE = """
MERGE (surface:PublicApiSurface {id: $surface_id})
SET surface += $surface_props
"""
_WRITE_SYMBOL = """
MATCH (surface:PublicApiSurface {id: $surface_id})
MERGE (symbol:PublicApiSymbol {id: $symbol_id})
SET symbol += $symbol_props
MERGE (surface)-[:EXPORTS]->(symbol)
WITH symbol
OPTIONAL MATCH (shadow:SymbolOccurrenceShadow {
    group_id: $group_id,
    symbol_qualified_name: $symbol_qualified_name
})
FOREACH (_ IN CASE WHEN shadow IS NULL THEN [] ELSE [1] END |
    MERGE (symbol)-[:BACKED_BY_SYMBOL]->(shadow)
)
RETURN shadow IS NOT NULL AS has_backing
"""


@dataclass(frozen=True)
class DiscoveredArtifact:
    path: Path
    relative_path: str
    module_name: str
    language: Language
    artifact_kind: PublicApiArtifactKind


@dataclass(frozen=True)
class _SwiftScope:
    fqn: str
    visibility: PublicApiVisibility


class PublicApiSurfaceExtractor(BaseExtractor):
    name: ClassVar[str] = "public_api_surface"
    description: ClassVar[str] = (
        "Ingest exported Kotlin and Swift public API snapshots from committed "
        "repo artifacts into Neo4j as PublicApiSurface/PublicApiSymbol facts."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT public_api_surface_id_unique IF NOT EXISTS "
        "FOR (n:PublicApiSurface) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT public_api_symbol_id_unique IF NOT EXISTS "
        "FOR (n:PublicApiSymbol) REQUIRE n.id IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX public_api_surface_lookup IF NOT EXISTS "
        "FOR (n:PublicApiSurface) ON (n.project, n.module_name, n.language, n.commit_sha)",
        "CREATE INDEX public_api_symbol_lookup IF NOT EXISTS "
        "FOR (n:PublicApiSymbol) ON (n.project, n.module_name, n.language, n.commit_sha, n.visibility)",
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

        artifacts = discover_public_api_artifacts(ctx.repo_path)
        if not artifacts:
            raise ExtractorError(
                error_code=ExtractorErrorCode.PUBLIC_API_ARTIFACTS_REQUIRED,
                message=(
                    "No public API artifacts found. Expected committed files under "
                    "'.palace/public-api/kotlin/*.api' or '.palace/public-api/swift/*.swiftinterface'."
                ),
                recoverable=False,
                action="manual_cleanup",
            )

        commit_sha = _read_head_sha(ctx.repo_path)
        parsed: list[tuple[PublicApiSurface, list[PublicApiSymbol]]] = []
        for artifact in artifacts:
            if artifact.language == Language.KOTLIN:
                parsed.append(
                    parse_kotlin_api_dump(
                        project=ctx.project_slug,
                        group_id=ctx.group_id,
                        artifact=artifact,
                        commit_sha=commit_sha,
                    )
                )
                continue
            if artifact.language == Language.SWIFT:
                parsed.append(
                    parse_swift_interface(
                        project=ctx.project_slug,
                        group_id=ctx.group_id,
                        artifact=artifact,
                        commit_sha=commit_sha,
                    )
                )
                continue

        stats = await _write_public_api_graph(driver=driver, parsed=parsed)
        return stats


def discover_public_api_artifacts(repo_path: Path) -> list[DiscoveredArtifact]:
    artifacts: list[DiscoveredArtifact] = []
    for path in sorted((repo_path / _KOTLIN_ARTIFACT_DIR).glob("*.api")):
        artifacts.append(
            DiscoveredArtifact(
                path=path,
                relative_path=path.relative_to(repo_path).as_posix(),
                module_name=path.stem,
                language=Language.KOTLIN,
                artifact_kind=PublicApiArtifactKind.KOTLIN_BCV_API,
            )
        )
    for path in sorted((repo_path / _SWIFT_ARTIFACT_DIR).glob("*.swiftinterface")):
        artifacts.append(
            DiscoveredArtifact(
                path=path,
                relative_path=path.relative_to(repo_path).as_posix(),
                module_name=path.stem,
                language=Language.SWIFT,
                artifact_kind=PublicApiArtifactKind.SWIFTINTERFACE,
            )
        )
    return artifacts


def parse_kotlin_api_dump(
    *,
    project: str,
    group_id: str,
    artifact: DiscoveredArtifact,
    commit_sha: str,
) -> tuple[PublicApiSurface, list[PublicApiSymbol]]:
    lines = artifact.path.read_text(encoding="utf-8").splitlines()
    tool_name = "kotlin-bcv"
    tool_version = "unknown"
    current_type_fqn: str | None = None
    symbols: list[PublicApiSymbol] = []

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if header := _KOTLIN_TOOL_HEADER.match(line):
            tool_name = header.group("name")
            tool_version = header.group("version")
            continue
        if line == "}":
            current_type_fqn = None
            continue
        if type_match := _KOTLIN_TYPE.match(line):
            visibility = _kotlin_visibility(type_match.group("visibility"))
            current_type_fqn = type_match.group("fqn")
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.KOTLIN,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=current_type_fqn,
                    display_name=current_type_fqn.rsplit(".", 1)[-1],
                    kind=_kotlin_type_kind(
                        type_match.group("mods"), type_match.group("kind")
                    ),
                    visibility=visibility,
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )
            continue
        if current_type_fqn is None:
            continue
        if constructor_match := _KOTLIN_CONSTRUCTOR.match(line):
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.KOTLIN,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=f"{current_type_fqn}.init({_normalize_params(constructor_match.group('params'))})",
                    display_name="init",
                    kind=PublicApiSymbolKind.INITIALIZER,
                    visibility=_kotlin_visibility(
                        constructor_match.group("visibility")
                    ),
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )
            continue
        if function_match := _KOTLIN_FUNCTION.match(line):
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.KOTLIN,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=(
                        f"{current_type_fqn}.{function_match.group('name')}"
                        f"({_normalize_params(function_match.group('params'))})"
                    ),
                    display_name=function_match.group("name"),
                    kind=PublicApiSymbolKind.FUNCTION,
                    visibility=_kotlin_visibility(function_match.group("visibility")),
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )
            continue
        if property_match := _KOTLIN_PROPERTY.match(line):
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.KOTLIN,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=f"{current_type_fqn}.{property_match.group('name')}",
                    display_name=property_match.group("name"),
                    kind=PublicApiSymbolKind.PROPERTY,
                    visibility=_kotlin_visibility(property_match.group("visibility")),
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )

    surface = _make_surface(
        project=project,
        group_id=group_id,
        module_name=artifact.module_name,
        language=Language.KOTLIN,
        commit_sha=commit_sha,
        artifact=artifact,
        tool_name=tool_name,
        tool_version=tool_version,
    )
    return surface, symbols


def parse_swift_interface(
    *,
    project: str,
    group_id: str,
    artifact: DiscoveredArtifact,
    commit_sha: str,
) -> tuple[PublicApiSurface, list[PublicApiSymbol]]:
    lines = artifact.path.read_text(encoding="utf-8").splitlines()
    tool_version = "unknown"
    scopes: list[_SwiftScope] = []
    symbols: list[PublicApiSymbol] = []

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if compiler := _SWIFT_COMPILER_HEADER.match(line):
            tool_version = compiler.group("version")
            continue
        if line == "}":
            if scopes:
                scopes.pop()
            continue
        if extension_match := _SWIFT_EXTENSION.match(line):
            visibility = _swift_visibility(
                extension_match.group("visibility") or "public"
            )
            scope_name = extension_match.group("name")
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.SWIFT,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=f"{scope_name}.extension",
                    display_name="extension",
                    kind=PublicApiSymbolKind.EXTENSION,
                    visibility=visibility,
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )
            scopes.append(_SwiftScope(fqn=scope_name, visibility=visibility))
            continue
        if named_decl := _SWIFT_NAMED_DECL.match(line):
            visibility = _swift_visibility(named_decl.group("visibility"))
            name = named_decl.group("name")
            kind = _swift_named_kind(named_decl.group("kind"))
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.SWIFT,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=name,
                    display_name=name.rsplit(".", 1)[-1],
                    kind=kind,
                    visibility=visibility,
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )
            if kind in {
                PublicApiSymbolKind.CLASS,
                PublicApiSymbolKind.STRUCT,
                PublicApiSymbolKind.ENUM,
                PublicApiSymbolKind.PROTOCOL,
            } and line.endswith("{"):
                scopes.append(_SwiftScope(fqn=name, visibility=visibility))
            continue
        if init_match := _SWIFT_INIT.match(line):
            if not scopes:
                continue
            params = _normalize_params(init_match.group("params"))
            scope = scopes[-1]
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.SWIFT,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=f"{scope.fqn}.init({params})",
                    display_name="init",
                    kind=PublicApiSymbolKind.INITIALIZER,
                    visibility=_swift_visibility(init_match.group("visibility")),
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )
            continue
        if function_match := _SWIFT_FUNCTION.match(line):
            scope_fqn = scopes[-1].fqn if scopes else ""
            params = _normalize_params(function_match.group("params"))
            base_fqn = (
                f"{scope_fqn}.{function_match.group('name')}"
                if scope_fqn
                else function_match.group("name")
            )
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.SWIFT,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=f"{base_fqn}({params})",
                    display_name=function_match.group("name"),
                    kind=PublicApiSymbolKind.FUNCTION,
                    visibility=_swift_visibility(function_match.group("visibility")),
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )
            continue
        if property_match := _SWIFT_PROPERTY.match(line):
            scope_fqn = scopes[-1].fqn if scopes else ""
            base_fqn = (
                f"{scope_fqn}.{property_match.group('name')}"
                if scope_fqn
                else property_match.group("name")
            )
            symbols.append(
                _make_symbol(
                    project=project,
                    group_id=group_id,
                    module_name=artifact.module_name,
                    language=Language.SWIFT,
                    commit_sha=commit_sha,
                    artifact_kind=artifact.artifact_kind,
                    fqn=base_fqn,
                    display_name=property_match.group("name"),
                    kind=PublicApiSymbolKind.PROPERTY,
                    visibility=_swift_visibility(property_match.group("visibility")),
                    signature=line,
                    source_artifact_path=artifact.relative_path,
                    source_line=line_no,
                )
            )

    surface = _make_surface(
        project=project,
        group_id=group_id,
        module_name=artifact.module_name,
        language=Language.SWIFT,
        commit_sha=commit_sha,
        artifact=artifact,
        tool_name="swiftc",
        tool_version=tool_version,
    )
    return surface, symbols


async def _write_public_api_graph(
    *,
    driver: AsyncDriver,
    parsed: list[tuple[PublicApiSurface, list[PublicApiSymbol]]],
) -> ExtractorStats:
    nodes_written = 0
    edges_written = 0
    async with driver.session() as session:
        for surface, symbols in parsed:
            await session.run(
                _WRITE_SURFACE,
                surface_id=surface.id,
                surface_props=surface.model_dump(mode="json", exclude_none=True),
            )
            nodes_written += 1
            for symbol in symbols:
                if await _write_symbol(session=session, surface=surface, symbol=symbol):
                    edges_written += 1
                nodes_written += 1
                edges_written += 1
    return ExtractorStats(nodes_written=nodes_written, edges_written=edges_written)


async def _write_symbol(
    *, session: AsyncSession, surface: PublicApiSurface, symbol: PublicApiSymbol
) -> bool:
    result = await session.run(
        _WRITE_SYMBOL,
        surface_id=surface.id,
        symbol_id=symbol.id,
        symbol_props=symbol.model_dump(mode="json", exclude_none=True),
        group_id=surface.group_id,
        symbol_qualified_name=symbol.symbol_qualified_name,
    )
    record = await result.single()
    return bool(record and record["has_backing"])


def _make_surface(
    *,
    project: str,
    group_id: str,
    module_name: str,
    language: Language,
    commit_sha: str,
    artifact: DiscoveredArtifact,
    tool_name: str,
    tool_version: str,
) -> PublicApiSurface:
    return PublicApiSurface(
        id=_stable_id(
            project,
            module_name,
            language.value,
            commit_sha,
            artifact.relative_path,
            artifact.artifact_kind.value,
            tool_name,
        ),
        group_id=group_id,
        project=project,
        module_name=module_name,
        language=language,
        commit_sha=commit_sha,
        artifact_path=artifact.relative_path,
        artifact_kind=artifact.artifact_kind,
        tool_name=tool_name,
        tool_version=tool_version,
    )


def _make_symbol(
    *,
    project: str,
    group_id: str,
    module_name: str,
    language: Language,
    commit_sha: str,
    artifact_kind: PublicApiArtifactKind,
    fqn: str,
    display_name: str,
    kind: PublicApiSymbolKind,
    visibility: PublicApiVisibility,
    signature: str,
    source_artifact_path: str,
    source_line: int,
) -> PublicApiSymbol:
    normalized_signature = _normalize_signature(signature)
    return PublicApiSymbol(
        id=_stable_id(
            project,
            module_name,
            language.value,
            fqn,
            _stable_id(normalized_signature),
            artifact_kind.value,
            commit_sha,
        ),
        group_id=group_id,
        project=project,
        module_name=module_name,
        language=language,
        commit_sha=commit_sha,
        fqn=fqn,
        display_name=display_name,
        kind=kind,
        visibility=visibility,
        signature=normalized_signature,
        signature_hash=_stable_id(normalized_signature),
        source_artifact_path=source_artifact_path,
        source_line=source_line,
        symbol_qualified_name=fqn,
    )


def _kotlin_visibility(raw_visibility: str) -> PublicApiVisibility:
    if raw_visibility == "public":
        return PublicApiVisibility.PUBLIC
    return PublicApiVisibility.PROTECTED


def _swift_visibility(raw_visibility: str) -> PublicApiVisibility:
    return PublicApiVisibility(raw_visibility)


def _kotlin_type_kind(modifiers: str, declared_kind: str) -> PublicApiSymbolKind:
    if declared_kind == "interface":
        return PublicApiSymbolKind.INTERFACE
    if "enum" in modifiers.split():
        return PublicApiSymbolKind.ENUM
    return PublicApiSymbolKind.CLASS


def _swift_named_kind(declared_kind: str) -> PublicApiSymbolKind:
    return {
        "class": PublicApiSymbolKind.CLASS,
        "struct": PublicApiSymbolKind.STRUCT,
        "enum": PublicApiSymbolKind.ENUM,
        "protocol": PublicApiSymbolKind.PROTOCOL,
        "typealias": PublicApiSymbolKind.TYPEALIAS,
    }.get(declared_kind, PublicApiSymbolKind.UNKNOWN)


def _normalize_params(params: str) -> str:
    return _normalize_signature(params)


def _normalize_signature(signature: str) -> str:
    return " ".join(signature.strip().split())


def _stable_id(*parts: str) -> str:
    payload = "||".join(parts)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def _read_head_sha(repo_path: Path) -> str:
    git_path = repo_path / ".git"
    if git_path.is_dir():
        head_path = git_path / "HEAD"
        ref_root = git_path
    else:
        pointer = git_path.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            return "unknown"
        ref_root = (repo_path / pointer.removeprefix("gitdir: ").strip()).resolve()
        head_path = ref_root / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "unknown"
    if not head.startswith("ref: "):
        return head[:40]
    ref_path = ref_root / head.removeprefix("ref: ").strip()
    try:
        return ref_path.read_text(encoding="utf-8").strip()[:40]
    except FileNotFoundError:
        return "unknown"
