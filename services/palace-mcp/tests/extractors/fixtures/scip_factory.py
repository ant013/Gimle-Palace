"""Factory for building synthetic SCIP Index protos for testing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from palace_mcp.proto import scip_pb2


def build_minimal_scip_index(
    *,
    language: str = "python",
    relative_path: str = "src/example.py",
    symbols: list[tuple[str, int]] | None = None,
) -> Any:
    """Build a minimal SCIP Index with one document and configurable symbols.

    symbols: list of (symbol_string, scip_role_int) tuples.
    Default: one def symbol.
    """
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = "test"
    metadata.tool_info.version = "0.0.1"
    metadata.project_root = "file:///test"
    index.metadata.CopyFrom(metadata)

    doc = index.documents.add()
    doc.relative_path = relative_path
    doc.language = language

    if symbols is None:
        symbols = [("scip-python python example . example_func .", 0)]

    for sym_str, role in symbols:
        occ = doc.occurrences.add()
        occ.range.extend([1, 0, 10])
        occ.symbol = sym_str
        occ.symbol_roles = role

    return index


def build_typescript_scip_index(
    *,
    relative_path: str = "src/example.ts",
    symbols: list[tuple[str, int]] | None = None,
) -> Any:
    """Build a minimal SCIP Index for TypeScript/JavaScript testing.

    Uses 'typescript' as doc.language and scip-typescript as tool_info.name.
    """
    if symbols is None:
        symbols = [
            (
                "scip-typescript npm example 1.0.0 src/`example.ts`/ExampleClass#.",
                1,
            )
        ]
    return build_minimal_scip_index(
        language="typescript",
        relative_path=relative_path,
        symbols=symbols,
    )


def build_jvm_scip_index(
    *,
    relative_path: str = "src/main/java/com/example/Example.java",
    language: str = "java",
    symbols: list[tuple[str, int]] | None = None,
) -> Any:
    """Build a minimal SCIP Index for Java/Kotlin testing.

    Uses configurable language ('java' or 'kotlin') and scip-java scheme.
    """
    if symbols is None:
        symbols = [
            (
                "semanticdb maven com.example 1.0.0 com/example/Example#run().",
                1,
            )
        ]
    return build_minimal_scip_index(
        language=language,
        relative_path=relative_path,
        symbols=symbols,
    )


def build_solidity_scip_index(
    *,
    relative_path: str = "contracts/Token.sol",
    symbols: list[tuple[str, int]] | None = None,
) -> Any:
    """Build a minimal SCIP Index for Solidity testing.

    Uses 'solidity' as doc.language and scip-solidity scheme.
    """
    if symbols is None:
        symbols = [
            (
                "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#.",
                1,
            )
        ]
    return build_minimal_scip_index(
        language="solidity",
        relative_path=relative_path,
        symbols=symbols,
    )


def build_swift_scip_index(
    *,
    documents: list[tuple[str, list[tuple[str, int]]]] | None = None,
) -> Any:
    """Build a minimal multi-document SCIP Index for Swift testing."""
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = "palace-swift-scip-emit"
    metadata.tool_info.version = "0.1.0"
    metadata.project_root = "file:///test"
    index.metadata.CopyFrom(metadata)

    if documents is None:
        documents = [
            (
                "Sources/UwMiniCore/State/WalletStore.swift",
                [
                    ("scip-swift apple UwMiniCore . s%3A10UwMiniCore11WalletStoreC", 1),
                    (
                        "scip-swift apple UwMiniCore . s%3A10UwMiniCore11WalletStoreC6select8walletIDySi_tF",
                        1,
                    ),
                ],
            ),
            (
                "Sources/UwMiniApp/ContentView.swift",
                [
                    (
                        "scip-swift apple UwMiniCore . s%3A10UwMiniCore11WalletStoreC6select8walletIDySi_tF",
                        0,
                    ),
                ],
            ),
            (
                "Pods/Foo/Foo.swift",
                [
                    (
                        "scip-swift apple UwMiniCore . s%3A10UwMiniCore11WalletStoreC6select8walletIDySi_tF",
                        0,
                    ),
                ],
            ),
        ]

    for relative_path, symbols in documents:
        doc = index.documents.add()
        doc.relative_path = relative_path
        doc.language = "swift"
        for i, (sym_str, role) in enumerate(symbols, start=1):
            occ = doc.occurrences.add()
            occ.range.extend([i, 0, 10])
            occ.symbol = sym_str
            occ.symbol_roles = role

    return index


def write_scip_fixture(index: Any, path: Path) -> Path:
    """Serialize SCIP Index to a file."""
    path.write_bytes(index.SerializeToString())
    return path
