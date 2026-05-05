"""Static guard for spec §3.4 invariant 1 + acceptance #11.

Hotspot extractor must never SET :File.project_id or :File.path; both are
owned by git_history (first-writer-wins).
"""

from __future__ import annotations

import re
from pathlib import Path

import palace_mcp.extractors.hotspot.neo4j_writer as writer_module

_WRITER_SOURCE_PATH = Path(writer_module.__file__)

_FORBIDDEN_PATTERNS = (
    re.compile(r"SET\s+f\.project_id\b"),
    re.compile(r"SET\s+f\.path\b"),
)


def test_hotspot_writer_does_not_set_file_project_id_or_path():
    src = _WRITER_SOURCE_PATH.read_text(encoding="utf-8")
    matches: list[str] = []
    for pat in _FORBIDDEN_PATTERNS:
        for m in pat.finditer(src):
            matches.append(f"{pat.pattern!r} at offset {m.start()}: {m.group(0)!r}")
    assert not matches, (
        "hotspot/neo4j_writer.py violates spec §3.4 invariant 1 — "
        "must not SET :File.project_id or :File.path. Matches:\n  "
        + "\n  ".join(matches)
    )
