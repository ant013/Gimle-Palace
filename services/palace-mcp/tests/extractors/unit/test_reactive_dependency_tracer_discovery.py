"""Unit tests for reactive_dependency_tracer file discovery."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.reactive_dependency_tracer.file_discovery import (
    DEFAULT_MAX_SWIFT_FILE_BYTES,
    discover_reactive_files,
)
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    ReactiveDiagnosticCode,
)


def test_discovery_finds_swift_and_records_skips(tmp_path: Path) -> None:
    (tmp_path / "Sources/App").mkdir(parents=True)
    (tmp_path / "Sources/App/CounterView.swift").write_text(
        "struct CounterView {}\n", encoding="utf-8"
    )
    (tmp_path / "Pods/Foo").mkdir(parents=True)
    (tmp_path / "Pods/Foo/Generated.swift").write_text(
        "struct Generated {}\n", encoding="utf-8"
    )
    (tmp_path / "Generated").mkdir(parents=True)
    (tmp_path / "Generated/Auto.swift").write_text("struct Auto {}\n", encoding="utf-8")
    (tmp_path / "Android").mkdir(parents=True)
    (tmp_path / "Android/App.kt").write_text(
        "import androidx.compose.runtime.Composable\n@Composable fun App() {}\n",
        encoding="utf-8",
    )
    (tmp_path / "Sources/App/Large.swift").write_text(
        "x" * (DEFAULT_MAX_SWIFT_FILE_BYTES + 1),
        encoding="utf-8",
    )

    result = discover_reactive_files(repo_root=tmp_path)

    assert [path.as_posix() for path in result.swift_files] == [
        "Sources/App/CounterView.swift"
    ]
    codes = [diagnostic.diagnostic_code for diagnostic in result.diagnostics]
    assert ReactiveDiagnosticCode.SWIFT_GENERATED_OR_VENDOR_SKIPPED in codes
    assert ReactiveDiagnosticCode.SWIFT_FILE_TOO_LARGE in codes
    assert ReactiveDiagnosticCode.KOTLIN_TOOLING_UNAVAILABLE in codes
    assert ReactiveDiagnosticCode.COMPOSE_STABILITY_REPORT_UNAVAILABLE in codes


def test_discovery_without_swift_is_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "Android").mkdir(parents=True)
    (tmp_path / "Android/App.kt").write_text("fun main() {}\n", encoding="utf-8")

    result = discover_reactive_files(repo_root=tmp_path)

    assert result.swift_files == ()
    assert result.kotlin_files == ("Android/App.kt",)


def test_discovery_respects_ignore_paths(tmp_path: Path) -> None:
    (tmp_path / "Sources/App").mkdir(parents=True)
    (tmp_path / "Sources/App/Keep.swift").write_text(
        "struct Keep {}\n", encoding="utf-8"
    )
    (tmp_path / "Sources/Ignore").mkdir(parents=True)
    (tmp_path / "Sources/Ignore/Skip.swift").write_text(
        "struct Skip {}\n", encoding="utf-8"
    )

    result = discover_reactive_files(
        repo_root=tmp_path,
        ignore_paths=("Sources/Ignore",),
    )

    assert [path.as_posix() for path in result.swift_files] == [
        "Sources/App/Keep.swift"
    ]
