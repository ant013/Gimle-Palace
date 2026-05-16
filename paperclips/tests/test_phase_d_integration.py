"""Phase D: integration — builder reads via resolver."""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_builder_imports_resolver():
    text = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    assert "resolve_bindings" in text, \
        "build_project_compat.py must reference resolve_bindings module"


def test_builder_does_not_read_legacy_env_directly():
    """build_project_compat.py should NOT directly open codex-agent-ids.env."""
    text = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    direct_reads = re.findall(r"(open|read_text|Path)\([^)]*codex-agent-ids\.env", text)
    assert not direct_reads, f"builder still reads legacy env directly: {direct_reads}"


def test_builder_runs_clean_on_trading():
    """Smoke: builder still works after wiring through resolver."""
    out = subprocess.run(
        ["bash", "paperclips/build.sh", "--project", "trading", "--target", "codex"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, f"build failed: stdout={out.stdout[-500:]} stderr={out.stderr[-500:]}"
