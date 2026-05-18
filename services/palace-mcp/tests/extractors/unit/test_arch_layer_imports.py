"""Unit tests for arch_layer import scanner (GIM-243)."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.arch_layer.imports import scan_imports


def _setup_source(tmp_path: Path, rel: str, content: str) -> None:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


class TestSwiftImportScanner:
    def test_declared_import_found(self, tmp_path: Path) -> None:
        _setup_source(
            tmp_path,
            "Sources/UI/WalletView.swift",
            "import WalletCore\n\nstruct Foo {}\n",
        )
        result = scan_imports(
            tmp_path,
            swift_modules=frozenset({"WalletCore", "WalletUI"}),
            gradle_modules=frozenset(),
            module_source_roots={
                "WalletCore": "Sources/WalletCore",
                "WalletUI": "Sources/UI",
            },
        )
        facts = [(f.src_module, f.dst_module) for f in result.facts]
        assert ("WalletUI", "WalletCore") in facts

    def test_self_import_skipped(self, tmp_path: Path) -> None:
        _setup_source(
            tmp_path,
            "Sources/WalletCore/Foo.swift",
            "import WalletCore\n",
        )
        result = scan_imports(
            tmp_path,
            swift_modules=frozenset({"WalletCore"}),
            gradle_modules=frozenset(),
            module_source_roots={"WalletCore": "Sources/WalletCore"},
        )
        assert result.facts == ()

    def test_external_import_skipped(self, tmp_path: Path) -> None:
        _setup_source(
            tmp_path,
            "Sources/UI/View.swift",
            "import Foundation\nimport UIKit\n",
        )
        result = scan_imports(
            tmp_path,
            swift_modules=frozenset({"UI"}),
            gradle_modules=frozenset(),
            module_source_roots={"UI": "Sources/UI"},
        )
        assert result.facts == ()

    def test_file_outside_any_source_root_skipped(self, tmp_path: Path) -> None:
        _setup_source(tmp_path, "Misc/helper.swift", "import WalletCore\n")
        result = scan_imports(
            tmp_path,
            swift_modules=frozenset({"WalletCore"}),
            gradle_modules=frozenset(),
            module_source_roots={"WalletCore": "Sources/WalletCore"},
        )
        assert result.facts == ()


class TestKotlinImportScanner:
    def test_unambiguous_import(self, tmp_path: Path) -> None:
        _setup_source(
            tmp_path,
            "ui/src/main/UI.kt",
            "import core.WalletService\n\nclass UIClass {}\n",
        )
        result = scan_imports(
            tmp_path,
            swift_modules=frozenset(),
            gradle_modules=frozenset({"core", "ui"}),
            module_source_roots={"core": "core/src/main", "ui": "ui/src/main"},
        )
        facts = [(f.src_module, f.dst_module) for f in result.facts]
        assert ("ui", "core") in facts

    def test_ambiguous_import_produces_warning(self, tmp_path: Path) -> None:
        # "com.Module" prefix-matches both "co" and "com" → ambiguous
        _setup_source(
            tmp_path,
            "app/src/main/App.kt",
            "import com.Module\n",
        )
        result = scan_imports(
            tmp_path,
            swift_modules=frozenset(),
            gradle_modules=frozenset({"co", "com"}),
            module_source_roots={
                "co": "co/src/main",
                "com": "com/src/main",
                "app": "app/src/main",
            },
        )
        assert any("ambiguous" in w.message for w in result.warnings)


class TestEmptyModuleSet:
    def test_no_modules_returns_empty(self, tmp_path: Path) -> None:
        _setup_source(tmp_path, "Sources/A/B.swift", "import Something\n")
        result = scan_imports(
            tmp_path,
            swift_modules=frozenset(),
            gradle_modules=frozenset(),
            module_source_roots={},
        )
        assert result.facts == ()
        assert result.warnings == ()
