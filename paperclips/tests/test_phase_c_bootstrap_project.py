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
