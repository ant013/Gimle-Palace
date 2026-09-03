"""Phase C2: bootstrap-project.sh structural validation.

Per spec §9.2 — 13 steps, idempotent, journal-snapshotted, topological hire,
2-stage canary. Live execution requires real paperclip API. Tests verify
script structure + arg-parsing only.
"""
import hashlib
import json
import re
import stat
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


def test_root_agent_hire_omits_empty_reports_to_uuid():
    text = SCRIPT.read_text()
    payload_start = text.index("payload=$(jq -n")
    payload = text[payload_start:text.index("log info \"hiring", payload_start)]

    assert 'reportsTo: $reportsTo, capabilities' not in payload
    assert 'if $reportsTo == "" then {} else {reportsTo: $reportsTo} end' in payload


def test_supports_canary_flag():
    text = SCRIPT.read_text()
    assert "--canary" in text


def test_canary_selection_does_not_sigpipe_under_pipefail():
    text = SCRIPT.read_text()
    canary_block = text[text.index('if [ "$CANARY" -eq 1 ]'):text.index("# Step 11: workspaces")]
    assert not re.search(r"\|\s*head(?:\s+-n)?\s+-?1\b", canary_block)
    assert canary_block.count("][0] // \"\"") == 3


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


def test_optional_recovery_model_profile_preserves_reasoning_and_runtime_config():
    text = SCRIPT.read_text()

    assert "recovery.model" in text
    assert "preserve_primary_reasoning_effort: true" in text
    assert "--arg effort \"$agent_effort\"" in text
    assert "modelProfiles: {cheap: $recoveryProfile}" in text
    assert ".runtimeConfig.modelProfiles.cheap // null" in text
    assert "(.runtimeConfig // {})" in text
    assert ".modelProfiles = ((.modelProfiles // {}) + {cheap: $profile})" in text
    assert "agent_recovery_profile_reconcile" in text

    managed_start = text.index("managed_config_filter='")
    managed_end = text.index("current_managed=", managed_start)
    assert "runtimeConfig" not in text[managed_start:managed_end]


def test_manifest_can_require_codex_instruction_file_without_changing_legacy_default():
    text = SCRIPT.read_text()

    assert ".targets.${target}.require_instructions_file // false" in text
    assert "targets.${target}.require_instructions_file must be true or false" in text
    assert '--argjson requireInstructionsFile "$require_instructions_file"' in text
    assert "requireInstructionsFile: $requireInstructionsFile" in text
    managed_start = text.index("managed_config_filter='")
    managed_end = text.index("current_managed=", managed_start)
    assert "requireInstructionsFile" in text[managed_start:managed_end]


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


def _uaudit_helper_installer_function() -> str:
    text = SCRIPT.read_text()
    match = re.search(
        r"^install_uaudit_delivery_helper\(\) \{.*?^\}\n",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, "install_uaudit_delivery_helper function missing"
    return match.group(0)


def _run_helper_install(team_root: Path) -> subprocess.CompletedProcess[str]:
    runner = f"""
set -euo pipefail
REPO_ROOT="$1"
die() {{ printf '%s\\n' "$*" >&2; exit 1; }}
log() {{ :; }}
{_uaudit_helper_installer_function()}
install_uaudit_delivery_helper "$2"
"""
    return subprocess.run(
        ["bash", "-c", runner, "uaudit-helper-test", str(REPO), str(team_root)],
        capture_output=True,
        text=True,
    )


def test_uaudit_helper_install_is_atomic_read_only_and_self_verifying(tmp_path):
    team_root = tmp_path / "team"
    result = _run_helper_install(team_root)
    assert result.returncode == 0, result.stderr

    tools = team_root / ".uaudit-tools"
    helper = tools / "uaudit_delivery_contract.py"
    manifest_path = tools / "uaudit_delivery_contract.manifest.json"
    manifest = json.loads(manifest_path.read_text())

    assert manifest == {
        "schema_version": "uaudit-helper-install/v1",
        "file": "uaudit_delivery_contract.py",
        "sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
    }
    assert helper.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH) == 0
    assert manifest_path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH) == 0
    assert not (tools / "uaudit_delivery_contract.pending.json").exists()

    verify = subprocess.run(
        ["python3", str(helper), "verify-install", "--manifest", str(manifest_path)],
        capture_output=True,
        text=True,
    )
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["sha256"] == manifest["sha256"]

    text = SCRIPT.read_text()
    assert text.rindex('mv -f "$helper_tmp" "$destination"') < text.rindex(
        'mv -f "$manifest_tmp" "$install_manifest"'
    )


def test_uaudit_helper_install_adopts_matching_manifestless_deployment(tmp_path):
    team_root = tmp_path / "team"
    tools = team_root / ".uaudit-tools"
    tools.mkdir(parents=True)
    source = REPO / "paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py"
    helper = tools / "uaudit_delivery_contract.py"
    helper.write_bytes(source.read_bytes())
    helper.chmod(0o555)

    result = _run_helper_install(team_root)
    assert result.returncode == 0, result.stderr

    manifest_path = tools / "uaudit_delivery_contract.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest_path.stat().st_mode & (
        stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    ) == 0


def test_uaudit_helper_install_rejects_writable_manifestless_deployment(tmp_path):
    team_root = tmp_path / "team"
    tools = team_root / ".uaudit-tools"
    tools.mkdir(parents=True)
    source = REPO / "paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py"
    helper = tools / "uaudit_delivery_contract.py"
    helper.write_bytes(source.read_bytes())
    helper.chmod(0o644)

    result = _run_helper_install(team_root)
    assert result.returncode != 0
    assert "must be read-only" in result.stderr
    assert not (tools / "uaudit_delivery_contract.manifest.json").exists()


def test_uaudit_helper_install_rejects_dangling_manifest_symlink(tmp_path):
    team_root = tmp_path / "team"
    tools = team_root / ".uaudit-tools"
    tools.mkdir(parents=True)
    source = REPO / "paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py"
    helper = tools / "uaudit_delivery_contract.py"
    helper.write_bytes(source.read_bytes())
    helper.chmod(0o555)
    manifest = tools / "uaudit_delivery_contract.manifest.json"
    manifest.symlink_to(tmp_path / "missing-manifest.json")

    result = _run_helper_install(team_root)
    assert result.returncode != 0
    assert "helper/manifest pair required" in result.stderr
    assert manifest.is_symlink()


def test_uaudit_helper_install_fails_closed_after_tampering(tmp_path):
    team_root = tmp_path / "team"
    first = _run_helper_install(team_root)
    assert first.returncode == 0, first.stderr

    helper = team_root / ".uaudit-tools" / "uaudit_delivery_contract.py"
    helper.chmod(0o644)
    helper.write_bytes(helper.read_bytes() + b"# tampered\n")

    second = _run_helper_install(team_root)
    assert second.returncode != 0
    assert "digest mismatch" in second.stderr


def test_uaudit_helper_install_rejects_consistently_rewritten_pair(tmp_path):
    team_root = tmp_path / "team"
    first = _run_helper_install(team_root)
    assert first.returncode == 0, first.stderr

    tools = team_root / ".uaudit-tools"
    helper = tools / "uaudit_delivery_contract.py"
    manifest = tools / "uaudit_delivery_contract.manifest.json"
    helper.chmod(0o644)
    helper.write_text("print('forged helper')\n")
    helper.chmod(0o444)
    forged_sha = hashlib.sha256(helper.read_bytes()).hexdigest()
    manifest.chmod(0o644)
    manifest.write_text(json.dumps({
        "schema_version": "uaudit-helper-install/v1",
        "file": "uaudit_delivery_contract.py",
        "sha256": forged_sha,
    }))
    manifest.chmod(0o444)

    second = _run_helper_install(team_root)
    assert second.returncode != 0
    assert "not explicitly trusted" in second.stderr


def test_uaudit_helper_install_rejects_symlink_pair(tmp_path):
    team_root = tmp_path / "team"
    first = _run_helper_install(team_root)
    assert first.returncode == 0, first.stderr

    tools = team_root / ".uaudit-tools"
    helper = tools / "uaudit_delivery_contract.py"
    manifest = tools / "uaudit_delivery_contract.manifest.json"
    external_helper = tmp_path / "external-helper.py"
    external_manifest = tmp_path / "external-manifest.json"
    external_helper.write_bytes(helper.read_bytes())
    external_manifest.write_bytes(manifest.read_bytes())
    helper.unlink()
    manifest.unlink()
    helper.symlink_to(external_helper)
    manifest.symlink_to(external_manifest)

    second = _run_helper_install(team_root)
    assert second.returncode != 0
    assert "helper/manifest pair required" in second.stderr


def test_uaudit_helper_install_recovers_split_helper_manifest_rename(tmp_path):
    team_root = tmp_path / "team"
    first = _run_helper_install(team_root)
    assert first.returncode == 0, first.stderr

    tools = team_root / ".uaudit-tools"
    helper = tools / "uaudit_delivery_contract.py"
    manifest_path = tools / "uaudit_delivery_contract.manifest.json"
    pending = tools / "uaudit_delivery_contract.pending.json"
    source = REPO / "paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py"

    helper.chmod(0o644)
    helper.write_bytes(helper.read_bytes() + b"# previous valid generation\n")
    helper.chmod(0o444)
    previous_sha = hashlib.sha256(helper.read_bytes()).hexdigest()
    manifest_path.chmod(0o644)
    manifest_path.write_text(json.dumps({
        "schema_version": "uaudit-helper-install/v1",
        "file": "uaudit_delivery_contract.py",
        "sha256": previous_sha,
    }))
    manifest_path.chmod(0o444)

    target_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    pending.write_text(json.dumps({
        "schema_version": "uaudit-helper-install-pending/v1",
        "target_sha256": target_sha,
        "previous_sha256": previous_sha,
    }))
    pending.chmod(0o444)
    helper.chmod(0o644)
    helper.write_bytes(source.read_bytes())
    helper.chmod(0o444)

    recovered = _run_helper_install(team_root)
    assert recovered.returncode == 0, recovered.stderr
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == target_sha
    assert json.loads(manifest_path.read_text())["sha256"] == target_sha
    assert not pending.exists()
