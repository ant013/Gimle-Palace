"""Bash-spec tests for ingest_swift_kit.sh DEFAULT_EXTRACTORS."""

from __future__ import annotations

import re
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent.parent.parent
    / "paperclips"
    / "scripts"
    / "ingest_swift_kit.sh"
)


def _parse_default_extractors() -> tuple[str, ...]:
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
    # Strip shell comments and keep declared order.
    names = tuple(
        token
        for line in block.splitlines()
        for token in line.split("#")[0].split()
        if token
    )
    return names


def test_script_file_exists() -> None:
    assert _SCRIPT_PATH.exists(), f"Script not found: {_SCRIPT_PATH}"


def test_default_extractors_match_python_ordered_profile() -> None:
    """Shell helper and Python orchestrator must stay byte-for-byte aligned."""
    from palace_mcp.extractors.foundation.profiles import get_ordered_extractors

    expected = get_ordered_extractors("swift_kit")
    defaults = _parse_default_extractors()
    assert defaults == expected
