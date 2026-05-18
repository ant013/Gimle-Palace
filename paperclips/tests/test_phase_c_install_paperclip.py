"""Phase C1 Task 3: install-paperclip.sh syntactic + structural validation.

This script does host-wide setup (paperclipai, telegram fork, MCP servers,
watchdog code prep). Live execution requires real npm/git/pnpm and would
mutate operator's machine — tests verify structure only, not behavior.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "install-paperclip.sh"


def test_exists_and_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_shows_usage():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "install" in out.stdout.lower()


def test_loads_versions_env():
    text = SCRIPT.read_text()
    assert "versions.env" in text


def test_uses_corepack_for_pnpm():
    text = SCRIPT.read_text()
    assert "corepack enable" in text
    # Allow both `corepack prepare pnpm@X` and `corepack prepare "pnpm@${X}"` quoting styles.
    assert "corepack prepare" in text
    assert "pnpm@" in text


def test_disables_heartbeat():
    text = SCRIPT.read_text()
    assert "heartbeat" in text and ("false" in text or "disabled" in text)


def test_uses_ignore_scripts_for_pnpm():
    """Security: prevent telegram plugin npm install-scripts from executing."""
    text = SCRIPT.read_text()
    assert "--ignore-scripts" in text


def test_does_not_install_watchdog_service():
    """Per spec §9.1 step 8: prepares watchdog code only; service install
    via bootstrap-watchdog.sh AFTER first project bootstrap.
    """
    text = SCRIPT.read_text()
    assert "uv sync" in text
    # Should NOT run 'gimle_watchdog install' directly (deferred to bootstrap-watchdog.sh).
    has_install = "gimle_watchdog install" in text
    if has_install:
        assert "deferred" in text or "bootstrap-watchdog" in text, \
            "install line must be commented/documented as deferred to bootstrap-watchdog.sh"


def test_sources_common_lib():
    text = SCRIPT.read_text()
    assert "_common.sh" in text


def test_pre_flight_checks_required_commands():
    """Spec §9.1 step 0: pre-flight verifies node 20+, gh, python3, uv, git, etc."""
    text = SCRIPT.read_text()
    for cmd in ["node", "gh", "python3", "git", "jq"]:
        assert cmd in text, f"pre-flight missing {cmd}"


def test_telegram_plugin_pinned_by_sha():
    """Should clone + checkout fork SHA, not install upstream npm."""
    text = SCRIPT.read_text()
    assert "git clone" in text
    assert "TELEGRAM_PLUGIN_REPO" in text
    assert "TELEGRAM_PLUGIN_REF" in text
    # Should NOT do plain `npm install paperclip-plugin-telegram` (would get upstream).
    assert "npm install -g paperclip-plugin-telegram" not in text


def test_idempotent_paperclipai_install():
    """Script should skip paperclipai install if already at pinned version."""
    text = SCRIPT.read_text()
    # Either: explicit version check, OR npm install handles idempotency.
    assert "PAPERCLIPAI_VERSION" in text
