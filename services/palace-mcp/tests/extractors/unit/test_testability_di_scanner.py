from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.testability_di.scanner import scan_repository


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_scan_repository_collects_swift_and_kotlin_sources(tmp_path: Path) -> None:
    _write(
        tmp_path / "Sources" / "WalletKit" / "WalletService.swift",
        "final class WalletService {}\n",
    )
    _write(
        tmp_path
        / "app"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "example"
        / "WalletRepo.kt",
        "class WalletRepo\n",
    )

    sources = scan_repository(repo_path=tmp_path)

    assert [(source.module, source.language) for source in sources] == [
        ("WalletKit", "swift"),
        ("app", "kotlin"),
    ]


def test_scan_repository_marks_test_and_non_test_paths(tmp_path: Path) -> None:
    _write(
        tmp_path / "Tests" / "WalletKitTests" / "WalletServiceTests.swift",
        "final class WalletServiceTests {}\n",
    )
    _write(
        tmp_path
        / "app"
        / "src"
        / "test"
        / "kotlin"
        / "com"
        / "example"
        / "WalletTest.kt",
        "class WalletTest\n",
    )
    _write(
        tmp_path
        / "app"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "example"
        / "WalletRepo.kt",
        "class WalletRepo\n",
    )

    sources = {
        source.relative_path: source for source in scan_repository(repo_path=tmp_path)
    }

    assert sources["Tests/WalletKitTests/WalletServiceTests.swift"].is_test is True
    assert sources["app/src/test/kotlin/com/example/WalletTest.kt"].is_test is True
    assert sources["app/src/main/kotlin/com/example/WalletRepo.kt"].is_test is False


def test_scan_repository_skips_ignored_directories(tmp_path: Path) -> None:
    _write(
        tmp_path / "Sources" / "WalletKit" / "WalletService.swift",
        "final class WalletService {}\n",
    )
    _write(
        tmp_path / ".build" / "debug" / "Generated.swift",
        "final class Generated {}\n",
    )
    _write(
        tmp_path / "vendor" / "ThirdParty" / "Dependency.kt",
        "class Dependency\n",
    )
    _write(
        tmp_path / "DerivedData" / "Temp.swift",
        "final class Temp {}\n",
    )

    sources = scan_repository(repo_path=tmp_path)

    assert [source.relative_path for source in sources] == [
        "Sources/WalletKit/WalletService.swift"
    ]
