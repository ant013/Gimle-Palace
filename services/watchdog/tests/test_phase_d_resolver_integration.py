"""Phase D: watchdog reads team UUIDs via dual-read resolver."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def test_validate_instructions_load_team_uuids_uses_resolver():
    """load_team_uuids must reference resolve_bindings (dual-read)."""
    text = (REPO / "paperclips" / "scripts" / "validate_instructions.py").read_text()
    assert "resolve_bindings" in text or "resolve_all" in text, \
        "load_team_uuids must use resolve_bindings for dual-read"


def test_load_team_uuids_merges_legacy_plus_bindings(tmp_path, monkeypatch):
    """When both legacy env + bindings.yaml exist, both UUID sources are merged."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Build a fake repo_root with legacy + per-project bindings
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "paperclips").mkdir(parents=True)
    legacy = fake_repo / "paperclips" / "codex-agent-ids.env"
    legacy.write_text("CX_CTO_AGENT_ID=uuid-codex-legacy-from-env\n")

    bindings_dir = tmp_path / ".paperclip" / "projects" / "gimle"
    bindings_dir.mkdir(parents=True)
    (bindings_dir / "bindings.yaml").write_text(
        'schemaVersion: 2\n'
        'company_id: "abc"\n'
        'agents:\n'
        '  CXCTO: "uuid-codex-legacy-from-env"\n'
        '  CXNewCodexAgent: "uuid-codex-new-from-bindings"\n'
    )

    from paperclips.scripts.validate_instructions import load_team_uuids
    teams = load_team_uuids(fake_repo)
    assert "uuid-codex-legacy-from-env" in teams["codex"], \
        f"legacy UUID missing: codex={teams['codex']}"
    assert "uuid-codex-new-from-bindings" in teams["codex"], \
        f"new bindings UUID missing: codex={teams['codex']}"


def test_load_team_uuids_pre_migration_legacy_only(tmp_path, monkeypatch):
    """Backward-compat: only legacy env exists, no ~/.paperclip — return legacy UUIDs."""
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "paperclips").mkdir(parents=True)
    legacy = fake_repo / "paperclips" / "codex-agent-ids.env"
    legacy.write_text(
        "CX_CTO_AGENT_ID=uuid-codex-only-legacy\n"
        "CX_PYTHON_ENGINEER_AGENT_ID=another-codex-legacy\n"
    )
    from paperclips.scripts.validate_instructions import load_team_uuids
    teams = load_team_uuids(fake_repo)
    assert "uuid-codex-only-legacy" in teams["codex"]
    assert "another-codex-legacy" in teams["codex"]


def test_load_team_uuids_post_migration_bindings_only(tmp_path, monkeypatch):
    """Post-Phase-H: legacy removed; only bindings exist — UUIDs still loaded."""
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "paperclips").mkdir(parents=True)
    # No legacy env file at all

    bindings_dir = tmp_path / ".paperclip" / "projects" / "gimle"
    bindings_dir.mkdir(parents=True)
    (bindings_dir / "bindings.yaml").write_text(
        'schemaVersion: 2\n'
        'company_id: "abc"\n'
        'agents:\n'
        '  CXCTO: "post-migration-codex-uuid"\n'
    )
    from paperclips.scripts.validate_instructions import load_team_uuids
    teams = load_team_uuids(fake_repo)
    assert "post-migration-codex-uuid" in teams["codex"]
