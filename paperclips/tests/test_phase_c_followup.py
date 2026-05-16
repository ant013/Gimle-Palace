"""Behavioral tests for Phase C followup fixes (deep-review findings)."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "paperclips" / "scripts"


def test_bootstrap_records_snapshot_kind_for_deploy():
    """deploy_one must write kind='agent_instructions_snapshot' with old_content,
    matching what rollback.sh case handles."""
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    assert 'kind:"agent_instructions_snapshot"' in text or \
           "kind: agent_instructions_snapshot" in text, \
        "bootstrap-project.sh must write snapshot kind handled by rollback.sh"
    assert "paperclip_get_agent_instructions" in text, \
        "bootstrap must fetch existing AGENTS.md before overwriting"
    assert 'kind:"agent_instructions_deploy"' not in text, \
        "agent_instructions_deploy kind is unhandled by rollback — remove"


def test_rollback_handles_agent_hire_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T130000Z-hire-test"
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "test-hire",
        "timestamp": "20260516T130000Z",
        "entries": [
            {"kind": "agent_hire",
             "name": "TestAgent",
             "id": "00000000-0000-0000-0000-000000000123"},
        ],
        "outcome": "success",
    }))
    out = subprocess.run(
        ["bash", str(SCRIPTS / "rollback.sh"), name, "--dry-run"],
        capture_output=True, text=True,
    )
    combined = out.stdout + out.stderr
    assert out.returncode == 0, f"rollback failed: {combined}"
    assert "unknown snapshot kind" not in combined.lower(), \
        f"agent_hire treated as unknown: {combined}"
    assert "would delete agent" in combined.lower() or \
           ("DRY RUN" in combined and "TestAgent" in combined), \
        f"agent_hire rollback did not surface delete intent: {combined}"


def test_rollback_handles_plugin_config_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T130100Z-plugin-test"
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "test-plugin",
        "timestamp": "20260516T130100Z",
        "entries": [
            {"kind": "plugin_config_snapshot",
             "plugin_id": "telegram",
             "old_config": {"defaultChatId": "12345"}},
        ],
        "outcome": "success",
    }))
    out = subprocess.run(
        ["bash", str(SCRIPTS / "rollback.sh"), name, "--dry-run"],
        capture_output=True, text=True,
    )
    combined = out.stdout + out.stderr
    assert out.returncode == 0
    assert "telegram" in combined, f"plugin_config_snapshot not surfaced: {combined}"


def test_bootstrap_journals_plugin_config_snapshot():
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    plugin_section_start = text.find("[8/13] telegram plugin config")
    assert plugin_section_start != -1, "could not locate telegram step"
    plugin_section_end = text.find("[9/13]", plugin_section_start)
    section = text[plugin_section_start:plugin_section_end] if plugin_section_end != -1 else text[plugin_section_start:]
    assert "paperclip_plugin_get_config" in section
    assert "plugin_config_snapshot" in section, \
        "plugin step must journal plugin_config_snapshot before POST"
    snapshot_pos = section.find("plugin_config_snapshot")
    post_pos = section.find("paperclip_plugin_set_config")
    assert snapshot_pos < post_pos, \
        f"snapshot at {snapshot_pos} must precede POST at {post_pos}"
