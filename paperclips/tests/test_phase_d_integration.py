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


def test_compatibility_agent_ids_merges_canonical_keys_from_bindings(tmp_path, monkeypatch):
    """D-fix C-1: compatibility_agent_ids must include canonical-form keys
    from bindings.yaml, not only kebab-form keys from legacy env.

    This is what makes Phase E trading/uaudit (which use canonical agent_name
    like CXCTO) produce non-empty agentId in resolved-assembly JSON.
    """
    import sys
    sys.path.insert(0, str(REPO / "paperclips" / "scripts"))
    monkeypatch.setenv("HOME", str(tmp_path))

    # Seed a bindings.yaml with a canonical name + valid UUID
    proj = tmp_path / ".paperclip" / "projects" / "gimle"
    proj.mkdir(parents=True)
    (proj / "bindings.yaml").write_text(
        'schemaVersion: 2\n'
        'company_id: "test-company-id"\n'
        'agents:\n'
        '  CXCTO: "da97dbd9-6627-48d0-b421-66af0750eacf"\n'
    )

    from build_project_compat import compatibility_agent_ids
    ids = compatibility_agent_ids(REPO, {"project.key": "gimle"}, "codex")
    # Legacy env path produces kebab keys (cx-cto); resolver merge adds canonical (CXCTO).
    assert "cx-cto" in ids or "CXCTO" in ids, \
        f"expected either kebab or canonical CTO key in ids: {list(ids)[:10]}"
    assert ids.get("CXCTO") == "da97dbd9-6627-48d0-b421-66af0750eacf" or \
           ids.get("cx-cto") == "da97dbd9-6627-48d0-b421-66af0750eacf", \
        f"CTO UUID missing from compatibility ids: {ids}"
