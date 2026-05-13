from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.testability_di.models import Language, SourceFile

_IGNORED_DIRS = {
    ".build",
    ".git",
    ".gradle",
    ".idea",
    ".swiftpm",
    "__pycache__",
    "DerivedData",
    "Pods",
    "build",
    "dist",
    "node_modules",
    "vendor",
}
_SUPPORTED_SUFFIXES: dict[str, Language] = {
    ".swift": "swift",
    ".kt": "kotlin",
}
_TEST_DIR_NAMES = {"androidtest", "spec", "specs", "test", "tests", "uitest", "uitests"}


def scan_repository(*, repo_path: Path) -> list[SourceFile]:
    sources: list[SourceFile] = []
    for path in sorted(repo_path.rglob("*")):
        if not path.is_file():
            continue
        language = _SUPPORTED_SUFFIXES.get(path.suffix)
        if language is None:
            continue
        relative_path = path.relative_to(repo_path).as_posix()
        if _is_ignored_path(relative_path):
            continue
        sources.append(
            SourceFile(
                relative_path=relative_path,
                module=_infer_module(relative_path),
                language=language,
                is_test=_is_test_path(relative_path),
                text=path.read_text(encoding="utf-8"),
            )
        )
    return sources


def _infer_module(relative_path: str) -> str:
    parts = relative_path.split("/")
    if "Sources" in parts:
        index = parts.index("Sources")
        if index + 1 < len(parts):
            return parts[index + 1]
    if "Tests" in parts:
        index = parts.index("Tests")
        if index + 1 < len(parts):
            return parts[index + 1]
    if "src" in parts:
        index = parts.index("src")
        if index > 0:
            return parts[index - 1]
    return parts[0] if parts else "root"


def _is_test_path(relative_path: str) -> bool:
    parts = relative_path.split("/")
    lowered_parts = [part.lower() for part in parts]
    if any(part in _TEST_DIR_NAMES for part in lowered_parts):
        return True
    filename = lowered_parts[-1]
    return filename.endswith("tests.swift") or filename.endswith("test.kt")


def _is_ignored_path(relative_path: str) -> bool:
    return any(part in _IGNORED_DIRS for part in relative_path.split("/"))
