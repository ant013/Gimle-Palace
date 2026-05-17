"""Phase C acceptance suite — verify the full kit is wired together.

Run after Phase C closes; the gate before Phase D starts.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "paperclips" / "scripts"

# All 8 operator scripts per spec §9 + versions.env config.
REQUIRED_SCRIPTS = [
    "install-paperclip.sh",
    "bootstrap-project.sh",
    "smoke-test.sh",
    "bootstrap-watchdog.sh",
    "update-versions.sh",
    "validate-manifest.sh",
    "rollback.sh",
    "migrate-bindings.sh",
    "versions.env",
]

REQUIRED_LIB = [
    "_common.sh",
    "_paperclip_api.sh",
    "_journal.sh",
    "_prompts.sh",
    "_smoke_probes.sh",
]

REQUIRED_TEMPLATES = [
    "watchdog-config.yaml.template",
    "watchdog-company-block.yaml.template",
]


def test_all_required_scripts_exist():
    missing = [s for s in REQUIRED_SCRIPTS if not (SCRIPTS / s).is_file()]
    assert not missing, f"missing scripts: {missing}"


def test_all_shell_scripts_executable():
    not_exec = []
    for s in REQUIRED_SCRIPTS:
        if not s.endswith(".sh"):
            continue
        mode = (SCRIPTS / s).stat().st_mode
        if (mode & 0o111) == 0:
            not_exec.append(s)
    assert not not_exec, f"not executable: {not_exec}"


def test_all_lib_helpers_exist():
    lib = SCRIPTS / "lib"
    missing = [f for f in REQUIRED_LIB if not (lib / f).is_file()]
    assert not missing, f"missing lib helpers: {missing}"


def test_all_templates_exist():
    tpl = REPO / "paperclips" / "templates"
    missing = [f for f in REQUIRED_TEMPLATES if not (tpl / f).is_file()]
    assert not missing, f"missing templates: {missing}"


def test_each_script_has_usage_in_help():
    """Every .sh script must respond to --help with 'Usage' or 'usage'."""
    failures = []
    for s in REQUIRED_SCRIPTS:
        if not s.endswith(".sh"):
            continue
        out = subprocess.run(
            ["bash", str(SCRIPTS / s), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        combined = out.stdout + out.stderr
        if "Usage" not in combined and "usage" not in combined.lower():
            failures.append((s, out.returncode, combined[:200]))
    assert not failures, f"--help broken: {failures}"


def test_install_paperclip_loads_versions_env():
    text = (SCRIPTS / "install-paperclip.sh").read_text()
    assert "versions.env" in text, "install-paperclip.sh must load versions.env"


def test_update_versions_loads_versions_env():
    text = (SCRIPTS / "update-versions.sh").read_text()
    assert "versions.env" in text, "update-versions.sh must reference versions.env"


def test_bootstrap_project_calls_validate_manifest():
    """spec §9.2: bootstrap-project.sh validates manifest first."""
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    assert ("validate-manifest.sh" in text) or ("validate_manifest" in text)


def test_bootstrap_project_calls_bootstrap_watchdog():
    """spec §9.2 step 13: bootstrap-project chains to bootstrap-watchdog."""
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    assert "bootstrap-watchdog.sh" in text


def test_rollback_handles_all_journaled_snapshot_kinds():
    """rollback.sh must handle every snapshot kind journaled by mutating scripts."""
    rollback = (SCRIPTS / "rollback.sh").read_text()
    # Kinds journaled by bootstrap-project.sh + update-versions.sh
    for kind in [
        "agent_instructions_snapshot",
        "plugin_config_snapshot",
        "version_bump_snapshot",
    ]:
        assert kind in rollback, f"rollback.sh doesn't handle '{kind}'"


def test_no_floating_versions_in_versions_env():
    """versions.env must pin every dependency — no 'latest', no 'main'."""
    text = (SCRIPTS / "versions.env").read_text()
    forbidden = ['="latest"', '="main"', '="master"', '="HEAD"']
    found = [t for t in forbidden if t in text]
    assert not found, f"versions.env has floating pin(s): {found}"


def test_smoke_test_uses_probe_library():
    text = (SCRIPTS / "smoke-test.sh").read_text()
    assert "_smoke_probes.sh" in text
    assert "probe_agent_for_profile" in text
