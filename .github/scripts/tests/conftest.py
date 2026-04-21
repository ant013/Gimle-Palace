"""Pytest config for paperclip_signal tests.

Adds the parent directory (.github/scripts/) to sys.path so tests can
`import paperclip_signal` without the script being a real Python package.
This approach keeps the Action script distributable as a single file
without pyproject.toml overhead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(SCRIPTS_DIR))


import pytest  # noqa: E402


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to tests/fixtures/ for loading JSON webhook payloads."""
    return FIXTURES_DIR


@pytest.fixture
def load_fixture(fixtures_dir: Path):
    """Callable that loads a JSON fixture by filename stem."""

    def _load(name: str) -> dict:
        path = fixtures_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Fixture {path} missing. Create a synthetic payload or capture from a real Action run."
            )
        return json.loads(path.read_text())

    return _load
