"""Integration test conftest — runs before fixture execution.

Sets PALACE_ADR_BASE_DIR to a tmpdir so the mcp_server module (imported
inside wire-test fixtures) picks up a writable, test-isolated base_dir
for the manage_adr wire tests.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile


def pytest_configure(config: object) -> None:
    if "PALACE_ADR_BASE_DIR" not in os.environ:
        d = tempfile.mkdtemp(prefix="palace_adr_wire_")
        os.environ["PALACE_ADR_BASE_DIR"] = d
        atexit.register(shutil.rmtree, d, True)
