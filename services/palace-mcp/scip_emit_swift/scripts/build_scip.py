#!/usr/bin/env python3
"""Serialize Swift emitter JSON payloads into canonical SCIP protobuf."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_import_path() -> None:
    package_root = Path(__file__).resolve().parents[2]
    src_path = package_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


_bootstrap_import_path()

from palace_mcp.proto import scip_pb2


def _build_index(payload: dict) -> scip_pb2.Index:
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = payload["metadata"]["toolName"]
    metadata.tool_info.version = payload["metadata"]["toolVersion"]
    metadata.tool_info.arguments.extend(payload["metadata"].get("arguments", []))
    metadata.project_root = payload["metadata"]["projectRoot"]
    index.metadata.CopyFrom(metadata)

    for doc_payload in payload.get("documents", []):
        doc = index.documents.add()
        doc.language = doc_payload["language"]
        doc.relative_path = doc_payload["relativePath"]
        for occurrence_payload in doc_payload.get("occurrences", []):
            occ = doc.occurrences.add()
            occ.range.extend(occurrence_payload["range"])
            occ.symbol = occurrence_payload["symbol"]
            occ.symbol_roles = occurrence_payload["symbol_roles"]

    return index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload_path = Path(args.payload)
    output_path = Path(args.output)

    payload = json.loads(payload_path.read_text())
    index = _build_index(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(index.SerializeToString())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
