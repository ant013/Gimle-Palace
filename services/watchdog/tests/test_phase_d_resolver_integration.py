"""Phase D: watchdog reads team UUIDs via dual-read resolver."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def test_validate_instructions_load_team_uuids_uses_resolver():
    """load_team_uuids must reference resolve_bindings (dual-read)."""
    text = (REPO / "paperclips" / "scripts" / "validate_instructions.py").read_text()
    assert "resolve_bindings" in text or "resolve_all" in text, (
        "load_team_uuids must use resolve_bindings for dual-read"
    )


# D-fix C-3: fixtures use real UUID format (was sentinel strings exploiting the
# old 'len >= 8' allowlist fallback).
_UUID_LEGACY = "da97dbd9-6627-48d0-b421-66af0750eacf"
_UUID_NEW = "fb1c2d3e-4f5a-6b7c-8d9e-0f1a2b3c4d5e"
_UUID_LEGACY_2 = "e010d305-22f7-4f5c-9462-e6526b195b19"
_UUID_POST = "11111111-2222-3333-4444-555555555555"


def test_load_team_uuids_merges_legacy_plus_bindings(tmp_path, monkeypatch):
    """When both legacy env + bindings.yaml exist, both UUID sources are merged."""
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "paperclips").mkdir(parents=True)
    legacy = fake_repo / "paperclips" / "codex-agent-ids.env"
    legacy.write_text(f"CX_CTO_AGENT_ID={_UUID_LEGACY}\n")

    bindings_dir = tmp_path / ".paperclip" / "projects" / "gimle"
    bindings_dir.mkdir(parents=True)
    (bindings_dir / "bindings.yaml").write_text(
        "schemaVersion: 2\n"
        'company_id: "abc"\n'
        "agents:\n"
        f'  CXCTO: "{_UUID_LEGACY}"\n'
        f'  CXNewCodexAgent: "{_UUID_NEW}"\n'
    )

    from paperclips.scripts.validate_instructions import load_team_uuids

    teams = load_team_uuids(fake_repo)
    assert _UUID_LEGACY in teams["codex"], f"legacy UUID missing: codex={teams['codex']}"
    assert _UUID_NEW in teams["codex"], f"new bindings UUID missing: codex={teams['codex']}"


def test_load_team_uuids_pre_migration_legacy_only(tmp_path, monkeypatch):
    """Backward-compat: only legacy env exists, no ~/.paperclip — return legacy UUIDs."""
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "paperclips").mkdir(parents=True)
    legacy = fake_repo / "paperclips" / "codex-agent-ids.env"
    legacy.write_text(
        f"CX_CTO_AGENT_ID={_UUID_LEGACY}\nCX_PYTHON_ENGINEER_AGENT_ID={_UUID_LEGACY_2}\n"
    )
    from paperclips.scripts.validate_instructions import load_team_uuids

    teams = load_team_uuids(fake_repo)
    assert _UUID_LEGACY in teams["codex"]
    assert _UUID_LEGACY_2 in teams["codex"]


def test_load_team_uuids_post_migration_bindings_only(tmp_path, monkeypatch):
    """Post-Phase-H: legacy removed; only bindings exist — UUIDs still loaded."""
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "paperclips").mkdir(parents=True)

    bindings_dir = tmp_path / ".paperclip" / "projects" / "gimle"
    bindings_dir.mkdir(parents=True)
    (bindings_dir / "bindings.yaml").write_text(
        f'schemaVersion: 2\ncompany_id: "abc"\nagents:\n  CXCTO: "{_UUID_POST}"\n'
    )
    from paperclips.scripts.validate_instructions import load_team_uuids

    teams = load_team_uuids(fake_repo)
    assert _UUID_POST in teams["codex"]


def test_load_team_uuids_rejects_non_uuid_values(tmp_path, monkeypatch):
    """D-fix C-3: garbage in bindings.yaml must NOT enter watchdog allowlist."""
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "paperclips").mkdir(parents=True)

    bindings_dir = tmp_path / ".paperclip" / "projects" / "gimle"
    bindings_dir.mkdir(parents=True)
    (bindings_dir / "bindings.yaml").write_text(
        "schemaVersion: 2\n"
        'company_id: "abc"\n'
        "agents:\n"
        f'  ValidAgent: "{_UUID_POST}"\n'
        '  InvalidShort: "abc"\n'
        '  InvalidLong: "this-string-is-long-enough-but-not-a-uuid"\n'
    )
    from paperclips.scripts.validate_instructions import load_team_uuids

    teams = load_team_uuids(fake_repo)
    assert _UUID_POST in teams["codex"]
    assert "abc" not in teams["codex"]
    assert "this-string-is-long-enough-but-not-a-uuid" not in teams["codex"]


def test_load_team_uuids_filters_by_company_id(tmp_path, monkeypatch):
    """D-fix C-2: allowed_company_ids filter scopes per company.

    Two projects (gimle + trading) each have their own company_id and UUIDs.
    A watchdog running for gimle's company must NOT see trading UUIDs.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "paperclips").mkdir(parents=True)

    gimle_company = "company-id-gimle-aaaa-bbbb-cccc-dddddddddddd"
    trading_company = "company-id-trading-eeee-ffff-gggg-hhhhhhhhhhhh"
    uuid_gimle = "aaaaaaaa-bbbb-cccc-dddd-111111111111"
    uuid_trading = "ffffffff-eeee-dddd-cccc-222222222222"

    for project_key, company_id, uuid_value in [
        ("gimle", gimle_company, uuid_gimle),
        ("trading", trading_company, uuid_trading),
    ]:
        proj_dir = tmp_path / ".paperclip" / "projects" / project_key
        proj_dir.mkdir(parents=True)
        (proj_dir / "bindings.yaml").write_text(
            f'schemaVersion: 2\ncompany_id: "{company_id}"\nagents:\n  Agent: "{uuid_value}"\n'
        )

    from paperclips.scripts.validate_instructions import load_team_uuids

    teams = load_team_uuids(fake_repo, allowed_company_ids={gimle_company})
    assert uuid_gimle in teams["codex"]
    assert uuid_trading not in teams["codex"], (
        f"trading UUID leaked into gimle-scoped allowlist: {teams['codex']}"
    )
