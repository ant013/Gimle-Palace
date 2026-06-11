"""Xcode project parser for arch_layer.

Extracts Xcode native targets, their source roots, and target dependencies
from committed ``project.pbxproj`` files. This is intentionally conservative:
it only models targets with Swift sources and only records dependencies that
resolve to other targets in the same project graph.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from palace_mcp.extractors.arch_layer.models import (
    Module,
    ModuleEdge,
    ParseResult,
    ParserWarning,
)

_OBJECT_START_RE = re.compile(r"^\s*([A-F0-9]{8,32}) /\*.*\*/ = \{")
@dataclass(frozen=True)
class _PbxObject:
    isa: str
    body: str


def parse_xcodeproj(repo_path: Path, *, project_id: str, run_id: str) -> ParseResult:
    pbxproj_paths = sorted(repo_path.glob("**/*.xcodeproj/project.pbxproj"))
    if not pbxproj_paths:
        return ParseResult(
            modules=(),
            edges=(),
            warnings=(ParserWarning(message="project.pbxproj not found"),),
        )

    modules: list[Module] = []
    edges: list[ModuleEdge] = []
    warnings: list[ParserWarning] = []
    seen_modules: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    for pbxproj_path in pbxproj_paths:
        result = _parse_project_file(
            pbxproj_path=pbxproj_path,
            repo_path=repo_path,
            project_id=project_id,
            run_id=run_id,
        )
        for module in result.modules:
            if module.slug in seen_modules:
                warnings.append(
                    ParserWarning(
                        message=(
                            f"xcodeproj: duplicate target {module.slug!r} across "
                            "project files — keeping first occurrence"
                        )
                    )
                )
                continue
            seen_modules.add(module.slug)
            modules.append(module)
        for edge in result.edges:
            edge_key = (edge.src_slug, edge.dst_slug, edge.declared_in)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append(edge)
        warnings.extend(result.warnings)

    return ParseResult(
        modules=tuple(modules),
        edges=tuple(edges),
        warnings=tuple(warnings),
    )


def _parse_project_file(
    *,
    pbxproj_path: Path,
    repo_path: Path,
    project_id: str,
    run_id: str,
) -> ParseResult:
    text = pbxproj_path.read_text(encoding="utf-8")
    objects = _parse_objects(text)
    manifest_path = str(pbxproj_path.relative_to(repo_path))

    groups = {oid: obj for oid, obj in objects.items() if obj.isa == "PBXGroup"}
    file_refs = {
        oid: obj for oid, obj in objects.items() if obj.isa == "PBXFileReference"
    }
    build_files = {oid: obj for oid, obj in objects.items() if obj.isa == "PBXBuildFile"}
    source_phases = {
        oid: obj for oid, obj in objects.items() if obj.isa == "PBXSourcesBuildPhase"
    }
    dependencies = {
        oid: obj for oid, obj in objects.items() if obj.isa == "PBXTargetDependency"
    }
    native_targets = {
        oid: obj for oid, obj in objects.items() if obj.isa == "PBXNativeTarget"
    }

    child_parents: dict[str, str] = {}
    for group_id, group in groups.items():
        for child_id in _list_field(group.body, "children"):
            child_parents.setdefault(child_id, group_id)

    target_names = {
        target_id: _string_field(target.body, "name")
        for target_id, target in native_targets.items()
    }

    modules: list[Module] = []
    edges: list[ModuleEdge] = []
    warnings: list[ParserWarning] = []

    for target_id, target in native_targets.items():
        target_name = target_names.get(target_id)
        if not target_name:
            continue

        swift_files = _target_swift_files(
            target=target,
            build_files=build_files,
            source_phases=source_phases,
            file_refs=file_refs,
            groups=groups,
            child_parents=child_parents,
        )
        if not swift_files:
            continue

        source_root = _common_source_root(swift_files, target_name=target_name)
        if source_root is None:
            warnings.append(
                ParserWarning(
                    message=(
                        f"xcodeproj: target {target_name!r} has Swift sources but "
                        "no resolvable common source root"
                    )
                )
            )
            continue

        modules.append(
            Module(
                project_id=project_id,
                slug=target_name,
                name=target_name,
                kind="swift_target",
                manifest_path=manifest_path,
                source_root=source_root,
                run_id=run_id,
            )
        )

    known_target_names = {module.slug for module in modules}
    for target_id, target in native_targets.items():
        src_name = target_names.get(target_id)
        if not src_name or src_name not in known_target_names:
            continue
        for dep_id in _list_field(target.body, "dependencies"):
            dep = dependencies.get(dep_id)
            if dep is None:
                continue
            dst_target_id = _reference_field(dep.body, "target")
            dst_name = target_names.get(dst_target_id or "")
            if not dst_name or dst_name not in known_target_names:
                continue
            edges.append(
                ModuleEdge(
                    src_slug=src_name,
                    dst_slug=dst_name,
                    scope="target_dep",
                    declared_in=manifest_path,
                    evidence_kind="manifest",
                    run_id=run_id,
                )
            )

    return ParseResult(
        modules=tuple(modules),
        edges=tuple(edges),
        warnings=tuple(warnings),
    )


def _parse_objects(text: str) -> dict[str, _PbxObject]:
    objects: dict[str, _PbxObject] = {}
    current_id: str | None = None
    current_lines: list[str] = []
    depth = 0

    for line in text.splitlines():
        if current_id is None:
            match = _OBJECT_START_RE.match(line)
            if match is None:
                continue
            current_id = match.group(1)
            current_lines = [line]
            depth = line.count("{") - line.count("}")
            if depth == 0:
                body = "\n".join(current_lines)
                isa = _string_field(body, "isa") or ""
                objects[current_id] = _PbxObject(isa=isa, body=body)
                current_id = None
                current_lines = []
            continue

        current_lines.append(line)
        depth += line.count("{") - line.count("}")
        if depth != 0:
            continue

        body = "\n".join(current_lines)
        isa = _string_field(body, "isa") or ""
        objects[current_id] = _PbxObject(isa=isa, body=body)
        current_id = None
        current_lines = []

    return objects


def _target_swift_files(
    *,
    target: _PbxObject,
    build_files: dict[str, _PbxObject],
    source_phases: dict[str, _PbxObject],
    file_refs: dict[str, _PbxObject],
    groups: dict[str, _PbxObject],
    child_parents: dict[str, str],
) -> list[PurePosixPath]:
    files: list[PurePosixPath] = []
    for phase_id in _list_field(target.body, "buildPhases"):
        phase = source_phases.get(phase_id)
        if phase is None:
            continue
        for build_file_id in _list_field(phase.body, "files"):
            build_file = build_files.get(build_file_id)
            if build_file is None:
                continue
            file_ref_id = _reference_field(build_file.body, "fileRef")
            if file_ref_id is None:
                continue
            file_ref = file_refs.get(file_ref_id)
            if file_ref is None:
                continue
            resolved = _resolve_file_ref_path(
                file_ref_id=file_ref_id,
                file_refs=file_refs,
                groups=groups,
                child_parents=child_parents,
            )
            if resolved is None or resolved.suffix.lower() != ".swift":
                continue
            files.append(resolved)
    return files


def _resolve_file_ref_path(
    *,
    file_ref_id: str,
    file_refs: dict[str, _PbxObject],
    groups: dict[str, _PbxObject],
    child_parents: dict[str, str],
) -> PurePosixPath | None:
    file_ref = file_refs[file_ref_id]
    path = _string_field(file_ref.body, "path")
    if not path:
        return None

    source_tree = (_string_field(file_ref.body, "sourceTree") or "<group>").strip()
    path_value = PurePosixPath(path)
    if source_tree == "SOURCE_ROOT":
        return path_value
    if source_tree != "<group>":
        return None

    parent_id = child_parents.get(file_ref_id)
    parent_path = _resolve_group_path(
        group_id=parent_id,
        groups=groups,
        child_parents=child_parents,
    )
    if parent_path is None:
        return path_value
    return parent_path / path_value


def _resolve_group_path(
    *,
    group_id: str | None,
    groups: dict[str, _PbxObject],
    child_parents: dict[str, str],
) -> PurePosixPath | None:
    if group_id is None:
        return PurePosixPath()

    group = groups.get(group_id)
    if group is None:
        return None

    source_tree = (_string_field(group.body, "sourceTree") or "<group>").strip()
    path = _string_field(group.body, "path")
    base: PurePosixPath | None

    if source_tree == "SOURCE_ROOT":
        base = PurePosixPath()
    elif source_tree == "<group>":
        base = _resolve_group_path(
            group_id=child_parents.get(group_id),
            groups=groups,
            child_parents=child_parents,
        )
        if base is None:
            return None
    else:
        return None

    return base / PurePosixPath(path) if path else base


def _common_source_root(
    paths: list[PurePosixPath], *, target_name: str
) -> str | None:
    directories = [str(path.parent) for path in paths if path.parent != PurePosixPath("")]
    if not directories:
        return ""
    common = os.path.commonpath(directories)
    if common not in ("", "."):
        return common

    preferred_root: str | None = None
    normalized_target = _normalize(target_name)
    counts: dict[str, int] = {}
    for path in paths:
        if not path.parts:
            continue
        candidate = path.parts[0]
        counts[candidate] = counts.get(candidate, 0) + 1
        normalized_candidate = _normalize(candidate)
        if normalized_candidate and normalized_candidate in normalized_target:
            preferred_root = candidate

    if preferred_root is not None:
        return preferred_root
    if counts:
        return max(counts.items(), key=lambda item: (item[1], -len(item[0])))[0]
    return ""


def _string_field(body: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*(\"[^\"]*\"|[^;]+);", body)
    if match is None:
        return None
    return match.group(1).strip().strip('"')


def _list_field(body: str, field: str) -> list[str]:
    match = re.search(
        rf"\b{re.escape(field)}\s*=\s*\((?P<inner>.*?)\);",
        body,
        re.DOTALL,
    )
    if match is None:
        return []
    return re.findall(r"\b([A-F0-9]{8,32})\b", match.group("inner"))


def _reference_field(body: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*([A-F0-9]{{8,32}})\b", body)
    if match is None:
        return None
    return match.group(1)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())
