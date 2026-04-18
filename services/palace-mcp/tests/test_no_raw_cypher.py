"""Zero-Cypher gate — spec §9 acceptance criterion.

Ensures that no palace_mcp source file contains raw Cypher strings
(MATCH, MERGE, CREATE, DELETE as standalone query keywords).
The only permitted Cypher usage is inside graphiti-core internals,
not in our own code.

Excluded paths:
- tests/ (test fixtures may reference Cypher for assertion purposes)
- scripts/ (spike scripts may contain Cypher for exploration)
- Any __pycache__ directories
"""

from __future__ import annotations

import re
from pathlib import Path

# Source root for palace-mcp
_SRC_ROOT = Path(__file__).parent.parent / "src" / "palace_mcp"

# Patterns that indicate raw Cypher in Python source.
# We match standalone query keywords that would only appear in actual Cypher.
_CYPHER_PATTERNS = [
    re.compile(r'\bMATCH\s*\(', re.MULTILINE),        # MATCH (n:Label)
    re.compile(r'\bOPTIONAL MATCH\s*\(', re.MULTILINE),  # OPTIONAL MATCH (n:Label)
    re.compile(r'\bMERGE\s*\(', re.MULTILINE),        # MERGE (n:Label)
    re.compile(r'\bCREATE\s*\(', re.MULTILINE),       # CREATE (n:Label)
    re.compile(r'\bDETACH DELETE\b', re.MULTILINE),   # DETACH DELETE
    re.compile(r'\bUNWIND\s+\$', re.MULTILINE),       # UNWIND $batch
    re.compile(r'\bRETURN\s+\w', re.MULTILINE),       # RETURN n AS node
    re.compile(r'\bSET\s+\w+\.\w+\s*=', re.MULTILINE),  # SET n.prop = $val
    re.compile(r'tx\.run\(', re.MULTILINE),           # tx.run( — managed transaction
    re.compile(r'session\.execute_(?:read|write)', re.MULTILINE),  # session.execute_*
]

# Collect violations for rich error reporting
_violations: list[tuple[Path, int, str]] = []


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return (line_no, pattern) tuples for Cypher hits in a source file."""
    hits: list[tuple[int, str]] = []
    source = path.read_text(encoding="utf-8")
    for pattern in _CYPHER_PATTERNS:
        for match in pattern.finditer(source):
            line_no = source[: match.start()].count("\n") + 1
            hits.append((line_no, pattern.pattern))
    return hits


def _source_files() -> list[Path]:
    return [
        p
        for p in _SRC_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def test_no_raw_cypher_in_source() -> None:
    """No palace_mcp source file may contain raw Cypher query strings."""
    violations: list[str] = []
    for path in _source_files():
        hits = _scan_file(path)
        for line_no, pattern in hits:
            relative = path.relative_to(_SRC_ROOT.parent.parent)
            violations.append(f"  {relative}:{line_no} — matched pattern: {pattern!r}")

    if violations:
        violation_list = "\n".join(violations)
        raise AssertionError(
            f"Found raw Cypher in palace_mcp source (spec §9 violation):\n{violation_list}\n\n"
            "All Neo4j operations must go through graphiti-core namespace API."
        )


def test_no_neo4j_driver_imports_in_source() -> None:
    """No palace_mcp source file may import neo4j AsyncDriver/AsyncGraphDatabase directly."""
    forbidden_imports = [
        re.compile(r'from neo4j import.*AsyncDriver', re.MULTILINE),
        re.compile(r'from neo4j import.*AsyncGraphDatabase', re.MULTILINE),
        re.compile(r'from neo4j import.*AsyncManagedTransaction', re.MULTILINE),
    ]
    violations: list[str] = []
    for path in _source_files():
        source = path.read_text(encoding="utf-8")
        for pattern in forbidden_imports:
            if pattern.search(source):
                relative = path.relative_to(_SRC_ROOT.parent.parent)
                violations.append(f"  {relative} — {pattern.pattern!r}")

    if violations:
        violation_list = "\n".join(violations)
        raise AssertionError(
            f"Direct neo4j driver imports found in palace_mcp source:\n{violation_list}\n\n"
            "Use graphiti_client.build_graphiti() instead of raw neo4j drivers."
        )
