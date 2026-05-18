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


def test_capitalize_uses_portable_construct():
    """No GNU-sed \\u extension — must be bash ${var^} or awk."""
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    assert "sed 's/.*/\\u" not in text, \
        "bootstrap-project.sh still uses GNU sed \\u (broken on BSD/macOS)"
    prompt_section = text[text.find("Local project root"):text.find("Local project root") + 200]
    portable = (
        "${project_key^}" in prompt_section or
        "awk '{print toupper" in prompt_section or
        "tr '[:lower:]' '[:upper:]'" in prompt_section
    )
    assert portable, f"prompt section uses no portable capitalize:\n{prompt_section}"


def test_migrate_bindings_preserves_acronyms(tmp_path, monkeypatch):
    """CX_CTO → CXCTO not CXCto; CX_QA_ENGINEER → CXQAEngineer not CXQaEngineer."""
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(
        ["bash", str(SCRIPTS / "migrate-bindings.sh"), "gimle", "--dry-run"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, f"failed: {out.stderr}"
    assert "CXCTO:" in out.stdout, f"CXCTO missing (got CXCto?): {out.stdout}"
    assert "CXQAEngineer:" in out.stdout, f"CXQAEngineer missing: {out.stdout}"
    assert "CXMCPEngineer:" in out.stdout, f"CXMCPEngineer missing: {out.stdout}"
    assert "CXPythonEngineer:" in out.stdout
    assert "CXBlockchainEngineer:" in out.stdout
    assert "CodexArchitectReviewer:" in out.stdout
    assert "CXCto:" not in out.stdout
    assert "CXQaEngineer:" not in out.stdout
    assert "CXMcpEngineer:" not in out.stdout


def test_path_traversal_rejected_by_bootstrap_project():
    out = subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap-project.sh"), "../../etc"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "project key" in (out.stdout + out.stderr).lower()


def test_path_traversal_rejected_by_migrate_bindings():
    out = subprocess.run(
        ["bash", str(SCRIPTS / "migrate-bindings.sh"), "../../etc", "--dry-run"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "project key" in (out.stdout + out.stderr).lower()


def test_path_traversal_rejected_by_rollback():
    out = subprocess.run(
        ["bash", str(SCRIPTS / "rollback.sh"), "../../etc/passwd"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "journal" in (out.stdout + out.stderr).lower()


def test_absolute_path_rejected_by_rollback():
    out = subprocess.run(
        ["bash", str(SCRIPTS / "rollback.sh"), "/etc/passwd"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0


def test_watchdog_append_produces_valid_yaml(tmp_path, monkeypatch):
    """bootstrap-watchdog.sh must produce parseable YAML + be idempotent."""
    import yaml
    monkeypatch.setenv("HOME", str(tmp_path))
    project_key = "gimle"
    manifest_dir = REPO / "paperclips" / "projects" / project_key
    if not (manifest_dir / "paperclip-agent-assembly.yaml").is_file():
        return
    bindings_dir = tmp_path / ".paperclip" / "projects" / project_key
    bindings_dir.mkdir(parents=True)
    (bindings_dir / "bindings.yaml").write_text(
        'schemaVersion: 2\ncompany_id: "test-company-id-9999"\nagents: {}\n'
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://localhost:3100")
    out = subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap-watchdog.sh"), project_key, "--skip-launchd"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, f"watchdog setup failed: {out.stderr}"
    config_path = tmp_path / ".paperclip" / "watchdog-config.yaml"
    assert config_path.is_file()
    data = yaml.safe_load(config_path.read_text())
    assert "companies" in data, f"companies key missing: {data}"
    assert isinstance(data["companies"], list)
    # Idempotent: re-run must not duplicate
    subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap-watchdog.sh"), project_key, "--skip-launchd"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    data2 = yaml.safe_load(config_path.read_text())
    ids = [c["id"] for c in data2["companies"]]
    assert ids.count("test-company-id-9999") == 1, f"duplicate after re-run: {ids}"


# ============================================================================
# IMPORTANT batch (IMP-A..E)
# ============================================================================


def test_paperclip_api_has_curl_timeouts():
    """IMP-A: all curl invocations need --max-time + --connect-timeout."""
    import re
    text = (SCRIPTS / "lib" / "_paperclip_api.sh").read_text()
    # Match only actual curl invocations: `curl -...` at line-start (possibly indented),
    # not the word "curl" in comments or `require_command curl`.
    curls = re.findall(r"^\s*curl\s+-[^\n]*", text, re.MULTILINE)
    assert curls, "expected at least one curl invocation"
    bad = [c for c in curls if "--max-time" not in c]
    assert not bad, "curl without --max-time:\n" + "\n".join(bad)
    bad2 = [c for c in curls if "--connect-timeout" not in c]
    assert not bad2, "curl without --connect-timeout:\n" + "\n".join(bad2)


def test_plugin_step_fail_closes_on_non_404():
    """IMP-B: step 8 must not silently fall back to {} on auth errors."""
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    plugin_start = text.find("[8/13] telegram plugin")
    plugin_end = text.find("[9/13]", plugin_start)
    section = text[plugin_start:plugin_end]
    assert '|| echo "{}"' not in section, \
        "step 8 still has || echo \"{}\" fail-soft; must distinguish 404 from auth"
    assert "_safe" in section or "404" in section, \
        "step 8 must explicitly handle 404 vs other errors"


def test_journal_files_created_with_mode_600(tmp_path):
    """IMP-C: journal files (contain AGENTS.md content) must be mode 600."""
    import os
    cmd = f'source {SCRIPTS / "lib" / "_journal.sh"}; journal_open test-mode'
    result = subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True,
        env={"HOME": str(tmp_path), "PATH": os.environ["PATH"]},
    )
    assert result.returncode == 0, f"journal_open failed: {result.stderr}"
    journal_path = result.stdout.strip()
    assert Path(journal_path).is_file()
    mode = Path(journal_path).stat().st_mode & 0o777
    assert mode == 0o600, f"journal mode {oct(mode)} != 0o600"
    journal_dir = tmp_path / ".paperclip" / "journal"
    dir_mode = journal_dir.stat().st_mode & 0o777
    assert dir_mode == 0o700, f"journal dir mode {oct(dir_mode)} != 0o700"


def test_migrate_bindings_creates_bindings_yaml_mode_600(tmp_path, monkeypatch):
    """IMP-C: bindings.yaml has company_id + UUIDs — mode 600."""
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(
        ["bash", str(SCRIPTS / "migrate-bindings.sh"), "gimle"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, f"migrate-bindings failed: {out.stderr}"
    bindings = tmp_path / ".paperclip" / "projects" / "gimle" / "bindings.yaml"
    assert bindings.is_file()
    mode = bindings.stat().st_mode & 0o777
    assert mode == 0o600, f"bindings.yaml mode {oct(mode)} != 0o600"


def test_smoke_probes_no_shell_eval_builtin():
    """IMP-D: replace dynamic-shell-evaluation invocations with ${!var}."""
    text = (SCRIPTS / "lib" / "_smoke_probes.sh").read_text()
    assert 'must_have=$EXPECTED_GIT_' not in text and \
           'must_have=\\$EXPECTED_GIT_' not in text, \
        "smoke_probes still uses dynamic shell evaluation for variable lookup"
    assert '${!' in text, \
        "smoke_probes must use bash indirect expansion ${!var}"


def test_validate_agent_name_rejects_path_chars():
    """IMP-E: validator rejects names with yq-unsafe characters."""
    bad_names = ["foo.bar", "foo[0]", "foo bar", "foo;rm", "$(pwd)", "../foo"]
    common = SCRIPTS / "lib" / "_common.sh"
    for name in bad_names:
        cmd = f'source {common}; validate_agent_name "{name}"'
        out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        assert out.returncode != 0, f"validate_agent_name accepted bad: {name!r}"


def test_validate_agent_name_accepts_canonical():
    good = ["CTO", "PythonEngineer", "CXCTO", "CXMCPEngineer", "UWIQAEngineer",
            "CodexArchitectReviewer", "code_reviewer", "auditor"]
    common = SCRIPTS / "lib" / "_common.sh"
    for name in good:
        cmd = f'source {common}; validate_agent_name "{name}"'
        out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        assert out.returncode == 0, \
            f"validate_agent_name rejected good: {name!r}: {out.stderr}"
