"""SF3 regression: only compute.py runs the aggregation Cypher.

Per spec rev2 acceptance #18: any other module that contains
MATCH (p:Project)-[:DEPENDS_ON] is a sign that skew computation has
been duplicated. This test fails CI on such duplication.
"""

import re
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[3] / "src" / "palace_mcp"
EXEMPT_FILE = (
    PKG_ROOT / "extractors" / "cross_repo_version_skew" / "compute.py"
)

MATCH_PATTERN = re.compile(r"MATCH.*Project.*\)-\[:DEPENDS_ON", re.DOTALL)


def test_only_compute_py_runs_aggregation_cypher():
    offenders: list[tuple[str, int]] = []
    for py in sorted(PKG_ROOT.rglob("*.py")):
        if py == EXEMPT_FILE:
            continue
        text = py.read_text()
        # Skip lines marked with explicit opt-out
        for n, line in enumerate(text.splitlines(), 1):
            if "noqa: skew-compute" in line:
                continue
            if MATCH_PATTERN.search(line):
                offenders.append((str(py.relative_to(PKG_ROOT)), n))
    assert offenders == [], (
        "Skew-aggregation Cypher (MATCH (p:Project)-[:DEPENDS_ON]) appears "
        "outside compute.py:\n" + "\n".join(f"  {p}:{n}" for p, n in offenders)
    )
