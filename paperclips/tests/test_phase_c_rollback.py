"""Phase C3 Task 5: rollback.sh — journal replay."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "rollback.sh"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "Usage" in out.stdout
    assert "--list" in out.stdout
    assert "--dry-run" in out.stdout


def test_no_args_exits_nonzero():
    out = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert out.returncode != 0


def test_list_empty_journal_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(
        ["bash", str(SCRIPT), "--list"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert "no journal dir" in (out.stdout + out.stderr).lower()


def test_list_shows_recent_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T120000Z-bootstrap-test"
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "bootstrap-test",
        "timestamp": "20260516T120000Z",
        "entries": [],
        "outcome": "success",
    }))
    out = subprocess.run(
        ["bash", str(SCRIPT), "--list"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert name in (out.stdout + out.stderr)


def test_replay_missing_journal_dies(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(
        ["bash", str(SCRIPT), "nonexistent-journal-id"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "not found" in (out.stdout + out.stderr).lower()


def test_replay_empty_entries_no_op(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T120100Z-empty-op"
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "empty-op",
        "timestamp": "20260516T120100Z",
        "entries": [],
        "outcome": "success",
    }))
    out = subprocess.run(
        ["bash", str(SCRIPT), name],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert "nothing to roll back" in (out.stdout + out.stderr).lower()


def test_dry_run_does_not_call_api(tmp_path, monkeypatch):
    """DRY RUN must surface what would happen without invoking paperclip_deploy_agents_md."""
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T120200Z-dry-test"
    entry = {
        "kind": "agent_instructions_snapshot",
        "agent_id": "00000000-0000-0000-0000-000000000000",
        "old_content": "OLD AGENTS.md CONTENT",
    }
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "test-dry",
        "timestamp": "20260516T120200Z",
        "entries": [entry],
        "outcome": "success",
    }))
    out = subprocess.run(
        ["bash", str(SCRIPT), name, "--dry-run"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert "DRY RUN" in (out.stdout + out.stderr)
    # Bytes count should match the OLD AGENTS.md CONTENT (21 bytes)
    assert "21 bytes" in (out.stdout + out.stderr)


def test_sources_lib_helpers():
    text = SCRIPT.read_text()
    assert "_common.sh" in text
    assert "_paperclip_api.sh" in text


def test_handles_unknown_snapshot_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T120300Z-unknown-kind"
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "test",
        "timestamp": "20260516T120300Z",
        "entries": [{"kind": "something_new_v9"}],
        "outcome": "success",
    }))
    out = subprocess.run(
        ["bash", str(SCRIPT), name, "--dry-run"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert "unknown snapshot kind" in (out.stdout + out.stderr).lower()


def test_dry_run_covers_created_company_host_files_workspaces_and_watchdog(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T120400Z-greenfield"
    entries = [
        {
            "kind": "company_create",
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "ThorChainKit",
        },
        {
            "kind": "host_file_create",
            "path": str(tmp_path / ".paperclip/projects/thorchain/paths.yaml"),
        },
        {
            "kind": "managed_workspace_create",
            "path": str(tmp_path / "runs/ThorChainCEO/workspace"),
            "managed_file": "AGENTS.md",
        },
        {
            "kind": "watchdog_snapshot",
            "project_key": "thorchain",
            "config_path": str(tmp_path / ".paperclip/watchdog-config.yaml"),
            "config_existed": False,
            "config_content": "",
            "plist_path": str(
                tmp_path / "Library/LaunchAgents/work.ant013.gimle-watchdog.plist"
            ),
            "plist_existed": False,
            "plist_content": "",
        },
    ]
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "bootstrap-thorchain",
        "timestamp": "20260516T120400Z",
        "entries": entries,
        "outcome": "success",
    }))

    out = subprocess.run(
        ["bash", str(SCRIPT), name, "--dry-run"],
        capture_output=True,
        text=True,
    )

    assert out.returncode == 0, out.stderr
    combined = out.stdout + out.stderr
    for marker in ["company", "host file", "workspace", "watchdog"]:
        assert marker in combined.lower()


def test_workspace_rollback_quarantines_unknown_nonempty_content():
    text = SCRIPT.read_text()
    assert "quarantine" in text.lower()
    assert "rm -rf" not in text
    assert "managed_workspace_create" in text


def test_company_rollback_is_idempotent_after_bootstrap_compensation():
    text = SCRIPT.read_text()
    assert "paperclip_get_company_if_exists" in text
    assert "already absent" in text.lower()
