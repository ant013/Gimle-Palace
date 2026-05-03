"""Tests for per-document language detection in iter_scip_occurrences."""

from __future__ import annotations

from typing import Any

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.scip_parser import (
    _SCIP_LANGUAGE_MAP,
    _language_from_path,
    iter_scip_occurrences,
)
from palace_mcp.proto import scip_pb2


def _build_index_with_doc(
    *,
    language: str,
    relative_path: str = "src/example.py",
    sym: str = "scip-python python pkg 1.0.0 src/`f.py`/func().",
) -> Any:
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    index.metadata.tool_info.name = "test"
    doc = index.documents.add()
    doc.relative_path = relative_path
    doc.language = language
    occ = doc.occurrences.add()
    occ.symbol = sym
    occ.symbol_roles = 1
    occ.range.extend([1, 0, 10])
    return index


def _build_two_doc_index(
    *,
    lang1: str,
    path1: str,
    lang2: str,
    path2: str,
) -> Any:
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    index.metadata.tool_info.name = "test"

    doc1 = index.documents.add()
    doc1.relative_path = path1
    doc1.language = lang1
    occ1 = doc1.occurrences.add()
    occ1.symbol = "scip-typescript npm pkg 1.0.0 src/`a.ts`/A#."
    occ1.symbol_roles = 1
    occ1.range.extend([1, 0, 10])

    doc2 = index.documents.add()
    doc2.relative_path = path2
    doc2.language = lang2
    occ2 = doc2.occurrences.add()
    occ2.symbol = "scip-typescript npm pkg 1.0.0 src/`b.js`/B#."
    occ2.symbol_roles = 0
    occ2.range.extend([2, 0, 10])

    return index


class TestIterScipOccurrencesLanguageDetection:
    def test_python_doc_yields_python_language(self) -> None:
        index = _build_index_with_doc(language="python")
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.PYTHON

    def test_typescript_doc_yields_typescript_language(self) -> None:
        index = _build_index_with_doc(
            language="typescript",
            relative_path="src/app.ts",
            sym="scip-typescript npm pkg 1.0.0 src/`app.ts`/App#.",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.TYPESCRIPT

    def test_javascript_doc_yields_javascript_language(self) -> None:
        index = _build_index_with_doc(
            language="javascript",
            relative_path="src/util.js",
            sym="scip-typescript npm pkg 1.0.0 src/`util.js`/helper().",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.JAVASCRIPT

    def test_unknown_language_string_yields_unknown(self) -> None:
        index = _build_index_with_doc(language="cobol", relative_path="src/old.cob")
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.UNKNOWN

    def test_typescriptreact_doc_language_yields_typescript(self) -> None:
        # GIM-123: scip-typescript emits 'TypeScriptReact' for .tsx; previously
        # missing from _SCIP_LANGUAGE_MAP and only worked via extension fallback.
        index = _build_index_with_doc(
            language="TypeScriptReact",
            relative_path="src/Button.tsx",
            sym="scip-typescript npm pkg 1.0.0 src/`Button.tsx`/Button#.",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.TYPESCRIPT

    def test_javascriptreact_doc_language_yields_javascript(self) -> None:
        # GIM-123: same gap for .jsx → 'JavaScriptReact'.
        index = _build_index_with_doc(
            language="JavaScriptReact",
            relative_path="src/Button.jsx",
            sym="scip-typescript npm pkg 1.0.0 src/`Button.jsx`/Button#.",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.JAVASCRIPT

    def test_empty_language_falls_back_to_path_extension(self) -> None:
        """When doc.language is empty, derive from relative_path extension."""
        index = _build_index_with_doc(
            language="",
            relative_path="src/app.tsx",
            sym="scip-typescript npm pkg 1.0.0 src/`app.tsx`/App#.",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.TYPESCRIPT


class TestIterScipOccurrencesLanguageOverride:
    def test_explicit_language_param_overrides_doc_language(self) -> None:
        """language= kwarg overrides whatever doc.language says."""
        index = _build_index_with_doc(language="python")
        occs = list(
            iter_scip_occurrences(index, commit_sha="abc", language=Language.TYPESCRIPT)
        )
        assert occs[0].language == Language.TYPESCRIPT


class TestIterScipOccurrencesMixedLanguageDocs:
    def test_two_docs_yield_per_doc_languages(self) -> None:
        """Two documents with different languages get their own per-doc language."""
        index = _build_two_doc_index(
            lang1="typescript",
            path1="src/a.ts",
            lang2="javascript",
            path2="src/b.js",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert len(occs) == 2
        by_path = {o.file_path: o.language for o in occs}
        assert by_path["src/a.ts"] == Language.TYPESCRIPT
        assert by_path["src/b.js"] == Language.JAVASCRIPT


class TestSolidityLanguageDetection:
    """GIM-124: Solidity .sol language detection via doc.language and path extension."""

    def test_solidity_doc_language_yields_solidity(self) -> None:
        index = _build_index_with_doc(
            language="solidity",
            relative_path="contracts/Token.sol",
            sym="scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#.",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.SOLIDITY

    def test_sol_extension_fallback_yields_solidity(self) -> None:
        index = _build_index_with_doc(
            language="",
            relative_path="contracts/ERC20.sol",
            sym="scip-solidity ethereum contracts/ERC20.sol . contracts/ERC20.sol/`ERC20`#.",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.SOLIDITY

    def test_solidity_in_language_map(self) -> None:
        assert _SCIP_LANGUAGE_MAP["solidity"] == Language.SOLIDITY

    def test_sol_path_in_language_from_path(self) -> None:
        assert _language_from_path("contracts/A.sol") == Language.SOLIDITY

    def test_sol_path_nested_in_language_from_path(self) -> None:
        assert (
            _language_from_path("contracts/token/ERC20/ERC20.sol") == Language.SOLIDITY
        )


class TestSwiftLanguageDetection:
    def test_swift_doc_language_yields_swift(self) -> None:
        index = _build_index_with_doc(
            language="swift",
            relative_path="Sources/App/ContentView.swift",
            sym="scip-swift apple UwMiniCore . s%3A10UwMiniCore11WalletStoreC",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.SWIFT

    def test_swift_extension_fallback_yields_swift(self) -> None:
        index = _build_index_with_doc(
            language="",
            relative_path="Sources/App/ContentView.swift",
            sym="scip-swift apple UwMiniCore . s%3A10UwMiniCore11WalletStoreC",
        )
        occs = list(iter_scip_occurrences(index, commit_sha="abc"))
        assert occs[0].language == Language.SWIFT

    def test_swiftinterface_extension_fallback_yields_swift(self) -> None:
        assert (
            _language_from_path("SourcePackages/Modules/Foo.swiftinterface")
            == Language.SWIFT
        )

    def test_swift_in_language_map(self) -> None:
        assert _SCIP_LANGUAGE_MAP["swift"] == Language.SWIFT
