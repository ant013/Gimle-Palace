"""Bash-spec tests for ingest_swift_kit.sh DEFAULT_EXTRACTORS (Task 1.4).

Parses the DEFAULT_EXTRACTORS array from the shell script and asserts that
all swift_kit profile audit extractors are present (subset check, not equality).
The script also includes infrastructure extractors (symbol_index_swift, git_history)
that are not in the audit profile — equality would be wrong (N1).
"""

from __future__ import annotations

import re
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent.parent.parent
    / "paperclips"
    / "scripts"
    / "ingest_swift_kit.sh"
)


def _parse_default_extractors() -> set[str]:
    """Extract extractor names from DEFAULT_EXTRACTORS=(...) array in the script."""
    text = _SCRIPT_PATH.read_text()
    match = re.search(
        r"DEFAULT_EXTRACTORS=\(\s*(.*?)\s*\)",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        f"DEFAULT_EXTRACTORS=(…) array not found in {_SCRIPT_PATH}"
    )
    block = match.group(1)
    # Strip shell comments and split on whitespace
    names = {
        token
        for line in block.splitlines()
        for token in line.split("#")[0].split()
        if token
    }
    return names


def test_script_file_exists() -> None:
    assert _SCRIPT_PATH.exists(), f"Script not found: {_SCRIPT_PATH}"


def test_default_extractors_includes_audit_critical() -> None:
    """swift_kit profile audit_extractors must be a subset of DEFAULT_EXTRACTORS (N1).

    Equality is intentionally NOT asserted — the script also carries infrastructure
    extractors (symbol_index_swift, git_history) absent from the audit profile.
    """
    from palace_mcp.extractors.foundation.profiles import PROFILES

    swift_kit_audit = PROFILES["swift_kit"].audit_extractors
    defaults = _parse_default_extractors()

    missing = swift_kit_audit - defaults
    assert not missing, (
        f"These swift_kit audit extractors are missing from DEFAULT_EXTRACTORS: {missing}\n"
        f"Current DEFAULT_EXTRACTORS: {sorted(defaults)}"
    )
