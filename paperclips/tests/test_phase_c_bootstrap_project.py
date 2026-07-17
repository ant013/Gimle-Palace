"""Phase C2: bootstrap-project.sh structural validation.

Per spec §9.2 — 13 steps, idempotent, journal-snapshotted, topological hire,
2-stage canary. Live execution requires real paperclip API. Tests verify
script structure + arg-parsing only.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "bootstrap-project.sh"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "bootstrap" in out.stdout.lower()


def test_validates_manifest_first():
    text = SCRIPT.read_text()
    assert "validate-manifest.sh" in text or "validate_manifest" in text


def test_uses_topological_order():
    text = SCRIPT.read_text()
    assert "reportsTo" in text or "topological" in text.lower()


def test_supports_canary_flag():
    text = SCRIPT.read_text()
    assert "--canary" in text


def test_calls_bootstrap_watchdog_at_end():
    text = SCRIPT.read_text()
    assert "bootstrap-watchdog.sh" in text


def test_journal_snapshot_before_mutations():
    text = SCRIPT.read_text()
    assert "journal_open" in text


def test_supports_reuse_bindings():
    text = SCRIPT.read_text()
    assert "--reuse-bindings" in text


def test_sources_all_4_libs():
    text = SCRIPT.read_text()
    for lib in ["_common.sh", "_paperclip_api.sh", "_journal.sh", "_prompts.sh"]:
        assert lib in text, f"missing lib source: {lib}"


def test_fails_without_project_key():
    out = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert out.returncode != 0
    assert "project-key required" in out.stderr or "project-key" in out.stderr.lower()


def test_company_creation_uses_supported_prefix_seed_and_verifies_final_identity():
    text = SCRIPT.read_text()
    section = text[text.index("# Step 5:"):text.index("# Step 6:")]

    assert '[[ "$issue_prefix" =~ ^[A-Z]{3}$ ]]' in section
    assert '--arg n "$issue_prefix"' in section
    assert "'{name:$n}'" in section
    assert "issuePrefix:$p" not in section
    assert "prefix" in section.lower() and "already allocated" in section.lower()

    post_pos = section.index('paperclip_post "/api/companies"')
    journal_pos = section.index('kind:"company_create"')
    created_get_pos = section.index('paperclip_get "/api/companies/${company_id}"')
    patch_pos = section.index('paperclip_patch "/api/companies/${company_id}"')
    final_get_pos = section.index(
        'paperclip_get "/api/companies/${company_id}"', created_get_pos + 1
    )
    bindings_pos = section.index('cat > "$bindings"')

    assert post_pos < journal_pos < created_get_pos < patch_pos < final_get_pos
    assert final_get_pos < bindings_pos
    assert "rollback_created_company_or_die" in section
    assert "paperclip_delete_company" in section


def test_reused_company_is_verified_but_never_renamed():
    text = SCRIPT.read_text()
    section = text[text.index("# Step 5:"):text.index("# Step 6:")]
    reused = section[section.index("else\n  company_resp="):]

    assert "live_name" in reused
    assert "live_prefix" in reused
    assert "display name mismatch" in reused
    assert "prefix mismatch" in reused
    assert "paperclip_patch" not in reused


def test_explicit_paperclip_identity_overrides_profile_fallback():
    text = SCRIPT.read_text()
    assert "paperclip_role" in text
    assert "paperclip_icon" in text
    assert "profile fallback" in text.lower()


def test_canary_cto_uses_workflow_role():
    text = SCRIPT.read_text()
    assert 'workflow_role == "inner_orchestrator"' in text


def test_bootstrap_journals_all_created_resource_classes():
    text = SCRIPT.read_text()
    for kind in [
        'kind:"company_create"',
        'kind:"host_file_create"',
        'kind:"managed_workspace_create"',
        'kind:"watchdog_snapshot"',
    ]:
        assert kind in text, f"missing journal kind: {kind}"


def test_load_bearing_host_roots_are_checked_before_company_mutation():
    text = SCRIPT.read_text()
    check_pos = text.index("required_existing")
    company_pos = text.index("company create-or-reuse")
    assert check_pos < company_pos
    assert "host-local path" in text.lower()
