"""Phase C1: bash library helpers smoke-test."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "paperclips" / "scripts" / "lib"


def _run_bash(snippet: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", snippet], cwd=REPO,
        capture_output=True, text=True, **kwargs,
    )


def test_common_log_info_to_stderr():
    out = _run_bash(f"source {LIB}/_common.sh && log info 'hello'")
    assert out.returncode == 0
    assert "hello" in out.stderr
    assert out.stdout == ""


def test_common_die_exits_nonzero():
    out = _run_bash(f"source {LIB}/_common.sh && die 'fatal'")
    assert out.returncode != 0
    assert "fatal" in out.stderr


def test_common_require_command_passes_for_existing():
    out = _run_bash(f"source {LIB}/_common.sh && require_command bash")
    assert out.returncode == 0


def test_common_require_command_fails_for_missing():
    out = _run_bash(f"source {LIB}/_common.sh && require_command nonexistent-cmd-xyz123")
    assert out.returncode != 0


def test_common_require_env_passes_for_set():
    out = _run_bash(f"export FOO=bar; source {LIB}/_common.sh && require_env FOO")
    assert out.returncode == 0


def test_common_require_env_fails_for_unset():
    out = _run_bash(f"source {LIB}/_common.sh && require_env UNSET_VAR_XYZ")
    assert out.returncode != 0


def test_paperclip_api_lib_sources_clean():
    """_paperclip_api.sh should source without error."""
    out = _run_bash(f"source {LIB}/_common.sh && source {LIB}/_paperclip_api.sh && echo ok")
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout


def test_paperclip_api_defines_required_functions():
    """Verify all expected API wrapper functions are defined."""
    fns = [
        "paperclip_get", "paperclip_post", "paperclip_put", "paperclip_patch",
        "paperclip_hire_agent", "paperclip_deploy_agents_md",
        "paperclip_get_agent_config",
        "paperclip_plugin_get_config", "paperclip_plugin_set_config",
    ]
    cmd = f"source {LIB}/_common.sh && source {LIB}/_paperclip_api.sh"
    for fn in fns:
        out = _run_bash(f"{cmd} && type {fn}")
        assert out.returncode == 0, f"function {fn} not defined: {out.stderr}"


def test_journal_open_creates_file_under_journal_dir(tmp_path, monkeypatch):
    """journal_open creates expected JSON structure under ~/.paperclip/journal/."""
    monkeypatch.setenv("HOME", str(tmp_path))
    out = _run_bash(
        f"source {LIB}/_common.sh && source {LIB}/_journal.sh && journal_open test-op",
        env={**dict(__import__("os").environ), "HOME": str(tmp_path)},
    )
    assert out.returncode == 0, out.stderr
    journal_path = out.stdout.strip()
    assert journal_path.startswith(str(tmp_path / ".paperclip" / "journal"))
    p = Path(journal_path)
    assert p.is_file()
    import json
    data = json.loads(p.read_text())
    assert data["op"] == "test-op"
    assert data["entries"] == []
    assert "timestamp" in data


def test_journal_record_appends_entry(tmp_path):
    out = _run_bash(
        f"source {LIB}/_common.sh && source {LIB}/_journal.sh && "
        f"j=$(journal_open test-op) && "
        f"journal_record \"$j\" '{{\"kind\":\"test\",\"id\":\"abc\"}}' && "
        f"cat \"$j\"",
        env={**dict(__import__("os").environ), "HOME": str(tmp_path)},
    )
    assert out.returncode == 0, out.stderr
    import json
    data = json.loads(out.stdout)
    assert len(data["entries"]) == 1
    assert data["entries"][0]["kind"] == "test"


def test_prompts_lib_sources_clean():
    out = _run_bash(f"source {LIB}/_common.sh && source {LIB}/_prompts.sh && echo ok")
    assert out.returncode == 0
    assert "ok" in out.stdout


def test_prompts_defines_required_functions():
    fns = ["prompt_with_default", "prompt_yes_no", "prompt_required"]
    cmd = f"source {LIB}/_common.sh && source {LIB}/_prompts.sh"
    for fn in fns:
        out = _run_bash(f"{cmd} && type {fn}")
        assert out.returncode == 0, f"function {fn} not defined"
