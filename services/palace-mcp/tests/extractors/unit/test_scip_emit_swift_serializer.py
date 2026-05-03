"""Tests for the Swift emitter's Python SCIP serializer bridge."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file
from palace_mcp.extractors.foundation.models import Language, SymbolKind


def _serializer_script() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "scip_emit_swift"
        / "scripts"
        / "build_scip.py"
    )


def test_swift_serializer_writes_canonical_scip(tmp_path: Path) -> None:
    payload = {
        "metadata": {
            "projectRoot": "/tmp/UwMini",
            "toolName": "palace-swift-scip-emit",
            "toolVersion": "0.1.0",
            "arguments": ["--output", "index.scip"],
        },
        "documents": [
            {
                "language": "swift",
                "relativePath": "Sources/UwMini/Wallet.swift",
                "occurrences": [
                    {
                        "range": [1, 0, 0],
                        "symbol": "scip-swift apple UwMini . s%3A6UwMini6WalletV",
                        "symbol_roles": 1,
                    },
                    {
                        "range": [4, 8, 8],
                        "symbol": "scip-swift apple UwMini . s%3A6UwMini6WalletV",
                        "symbol_roles": 0,
                    },
                ],
            }
        ],
    }

    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload))
    output_path = tmp_path / "index.scip"

    subprocess.run(
        [sys.executable, str(_serializer_script()), "--payload", str(payload_path), "--output", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    index = parse_scip_file(output_path)
    occurrences = list(iter_scip_occurrences(index, commit_sha="abc123"))

    assert len(occurrences) == 2
    assert occurrences[0].language == Language.SWIFT
    assert occurrences[0].kind == SymbolKind.DEF
    assert occurrences[1].kind == SymbolKind.USE
    assert occurrences[0].file_path == "Sources/UwMini/Wallet.swift"
