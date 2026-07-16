"""Phase C1 Task 3: install-paperclip.sh syntactic + structural validation.

This script does host-wide setup (paperclipai, telegram fork, MCP servers,
watchdog code prep). Live execution requires real npm/git/pnpm and would
mutate operator's machine — tests verify structure only, not behavior.
"""
import hashlib
import json
import os
import re
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


def test_telegram_plugin_forces_soft_reinstall_and_worker_reload():
    """An existing plugin ID must not retain the already-running worker."""
    text = SCRIPT.read_text()
    soft_uninstall = '-X DELETE "${api_url%/}/api/plugins/${existing_id}"'
    local_install = "{packageName: $package_name, isLocalPath: true}"

    assert soft_uninstall in text
    assert local_install in text
    assert text.index(soft_uninstall) < text.index(
        'paperclip_post "/api/plugins/install" "$install_payload"'
    )
    assert '"path":"${src}"' not in text, "obsolete install request shape must not return"
    assert 'status // ""' in text and '"uninstalled"' in text
    assert 'status // ""' in text and '"ready"' in text
    assert "plugin-generations/telegram" in text
    assert text.index('git clone "$TELEGRAM_PLUGIN_REPO" "$staging_source"') < text.index(soft_uninstall)


def test_telegram_plugin_loaded_sha_proof_is_fail_closed():
    text = SCRIPT.read_text()
    assert "TELEGRAM_PLUGIN_REF must be an exact full 40-hex commit SHA" in text
    assert '[ "$loaded_head" = "$TELEGRAM_PLUGIN_REF" ]' in text
    assert '.packagePath // ""' in text
    assert "/api/plugins/${plugin_id}/health" in text
    assert 'schema_version "telegram-plugin-loaded-proof/v2"' in text
    for field in ["source_ref", "source_head", "package_path", "worker_sha256", "registry_healthy", "runtime_attestation"]:
        assert field in text
    assert 'code: "invalid_route_context"' in text
    assert 'invalid_field: "issueIdentifier"' in text
    assert text.index('rm -f "$proof_file"') < text.index(
        '-X DELETE "${api_url%/}/api/plugins/${existing_id}"'
    )


def test_telegram_plugin_prepares_rollback_before_unload():
    text = SCRIPT.read_text()
    assert 'schema_version "telegram-plugin-rollback/v1"' in text
    assert 'tar -C "$existing_package_path" -cf - .' in text
    assert 'config_sha256 "$existing_config_sha"' in text
    assert text.index('rollback generation prepared: $rollback_manifest') < text.index(
        '-X DELETE "${api_url%/}/api/plugins/${existing_id}"'
    )
    assert 'schema_version "telegram-plugin-pending-reinstall/v1"' in text
    assert text.index('mv -f "${pending_file}.tmp" "$pending_file"') < text.index(
        '-X DELETE "${api_url%/}/api/plugins/${existing_id}"'
    )
    assert "attempting prepared rollback" in text
    assert "restore_previous_generation" in text
    assert '.data.data.code == "missing_content"' in text


def test_telegram_plugin_uses_normalized_auth_store_and_admin_preflight():
    text = SCRIPT.read_text()
    assert "s/^[[:space:]]+//; s/[[:space:]]+$//; s:/+$::" in text
    assert 'api_url="$normalized_api_url"' in text
    assert ".credentials[$api].token // empty" in text
    assert ".credentials.token" not in text
    assert "requires an instance-admin Paperclip credential" in text
    assert '/api/instance/scheduler-heartbeats' in text


def _step_5_function() -> str:
    match = re.search(
        r"^step_5_telegram_plugin\(\) \{.*?^\}\n",
        SCRIPT.read_text(),
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, "step_5_telegram_plugin function missing"
    return match.group(0)


def _git(*args: str, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_telegram_plugin_reinstall_runtime_contract(tmp_path):
    """Exercise backup → unload → install → loaded-proof with a fake API."""
    home = tmp_path / "home"
    src = home / ".paperclip" / "plugins-src" / "paperclip-plugin-telegram"
    remote = tmp_path / "remote.git"
    fake_bin = tmp_path / "bin"
    src.mkdir(parents=True)
    fake_bin.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "UAudit Test",
            "GIT_AUTHOR_EMAIL": "uaudit@example.invalid",
            "GIT_COMMITTER_NAME": "UAudit Test",
            "GIT_COMMITTER_EMAIL": "uaudit@example.invalid",
        }
    )
    _git("init", cwd=src, env=env)
    (src / "package.json").write_text('{"name":"paperclip-plugin-telegram"}\n')
    (src / "worker-src.js").write_text("export const generation = 'old';\n")
    _git("add", "package.json", "worker-src.js", cwd=src, env=env)
    _git("commit", "-m", "old worker", cwd=src, env=env)
    old_sha = _git("rev-parse", "HEAD", cwd=src, env=env)

    (src / "worker-src.js").write_text("export const generation = 'new';\n")
    _git("add", "worker-src.js", cwd=src, env=env)
    _git("commit", "-m", "new worker", cwd=src, env=env)
    new_sha = _git("rev-parse", "HEAD", cwd=src, env=env)
    _git("init", "--bare", str(remote), cwd=tmp_path, env=env)
    _git("remote", "add", "origin", str(remote), cwd=src, env=env)
    _git("push", "origin", "HEAD", cwd=src, env=env)
    _git("checkout", "--detach", old_sha, cwd=src, env=env)
    (src / "dist").mkdir()
    (src / "dist/worker.js").write_text((src / "worker-src.js").read_text())

    pnpm = fake_bin / "pnpm"
    pnpm.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ \"${1:-}\" = build ]; then\n"
        "  mkdir -p dist\n"
        "  cp worker-src.js dist/worker.js\n"
        "fi\n"
    )
    pnpm.chmod(0o755)

    curl_log = tmp_path / "curl.log"
    active_path = tmp_path / "active-path"
    active_path.write_text(str(src))
    curl = fake_bin / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "method=GET\n"
        "url=\n"
        "body=\n"
        "prev=\n"
        "for arg in \"$@\"; do\n"
        "  if [ \"$prev\" = -X ]; then method=$arg; fi\n"
        "  if [ \"$prev\" = --data-binary ]; then body=$arg; fi\n"
        "  case \"$arg\" in http://*|https://*) url=$arg ;; esac\n"
        "  prev=$arg\n"
        "done\n"
        "printf '%s %s\\n' \"$method\" \"$url\" >> \"$CURL_LOG\"\n"
        "case \"$method $url\" in\n"
        "  'GET http://paperclip.test/api/instance/scheduler-heartbeats')\n"
        "    if [ \"${NON_ADMIN:-0}\" = 1 ]; then exit 22; fi\n"
        "    printf '[]' ;;\n"
        "  'GET http://paperclip.test/api/plugins')\n"
        "    current=$(cat \"$ACTIVE_PATH_FILE\")\n"
        "    printf '[{\"id\":\"plugin-id\",\"pluginKey\":\"paperclip-plugin-telegram\",\"status\":\"ready\",\"manifestJson\":{\"id\":\"paperclip-plugin-telegram\"},\"packagePath\":\"%s\"}]' \"$current\" ;;\n"
        "  'GET http://paperclip.test/api/plugins/plugin-id/config')\n"
        "    printf '{\"id\":\"config-id\",\"configJson\":{\"telegramBotTokenRef\":\"secret-ref\"}}' ;;\n"
        "  'DELETE http://paperclip.test/api/plugins/plugin-id')\n"
        "    printf '{\"id\":\"plugin-id\",\"status\":\"uninstalled\"}' ;;\n"
        "  'POST http://paperclip.test/api/plugins/install')\n"
        "    package=$(printf '%s' \"$body\" | jq -r '.packageName')\n"
        "    printf '%s' \"$package\" > \"$ACTIVE_PATH_FILE\"\n"
        "    printf '{\"id\":\"plugin-id\",\"pluginKey\":\"paperclip-plugin-telegram\",\"status\":\"ready\",\"packagePath\":\"%s\"}' \"$package\" ;;\n"
        "  'GET http://paperclip.test/api/plugins/plugin-id')\n"
        "    current=$(cat \"$ACTIVE_PATH_FILE\")\n"
        "    printf '{\"id\":\"plugin-id\",\"pluginKey\":\"paperclip-plugin-telegram\",\"status\":\"ready\",\"packagePath\":\"%s\"}' \"$current\" ;;\n"
        "  'GET http://paperclip.test/api/plugins/plugin-id/health')\n"
        "    printf '{\"pluginId\":\"plugin-id\",\"status\":\"ready\",\"healthy\":true}' ;;\n"
        "  'POST http://paperclip.test/api/plugins/plugin-id/actions/send_to_telegram')\n"
        "    if printf '%s' \"$body\" | grep -q INVALID; then\n"
        "      if [ \"${FAIL_TARGET_ATTESTATION:-0}\" = 1 ]; then\n"
        "        printf '{\"data\":{\"content\":\"\",\"data\":{\"ok\":false,\"code\":\"missing_content\"}}}'\n"
        "      else\n"
        "        printf '{\"data\":{\"content\":\"\",\"data\":{\"ok\":false,\"code\":\"invalid_route_context\",\"invalidField\":\"issueIdentifier\"}}}'\n"
        "      fi\n"
        "    else\n"
        "      printf '{\"data\":{\"content\":\"\",\"data\":{\"ok\":false,\"code\":\"missing_content\"}}}'\n"
        "    fi ;;\n"
        "  *) printf 'unexpected fake curl call: %s %s\\n' \"$method\" \"$url\" >&2; exit 1 ;;\n"
        "esac\n"
    )
    curl.chmod(0o755)

    auth = home / ".paperclip" / "auth.json"
    auth.write_text('{"version":1,"credentials":{"http://paperclip.test":{"token":"test-token"}}}\n')
    proof_dir = home / ".paperclip/plugin-proofs"
    proof_dir.mkdir()
    (proof_dir / "telegram-loaded.json").write_text('{"stale":true}\n')
    runner = f"""
set -euo pipefail
SCRIPT_DIR="$1/paperclips/scripts"
source "$SCRIPT_DIR/lib/_common.sh"
_skip() {{ return 1; }}
{_step_5_function()}
step_5_telegram_plugin
"""
    run_env = env | {
        "HOME": str(home),
        "PATH": f"{fake_bin}:{env['PATH']}",
        "CURL_LOG": str(curl_log),
        "ACTIVE_PATH_FILE": str(active_path),
        "FAKE_SRC": str(src),
        "PAPERCLIP_API_URL": "  http://paperclip.test///  ",
        "TELEGRAM_PLUGIN_REPO": str(remote),
        "TELEGRAM_PLUGIN_REF": new_sha,
    }
    non_admin = subprocess.run(
        ["bash", "-c", runner, "telegram-install-test", str(REPO)],
        env=run_env | {"NON_ADMIN": "1"},
        capture_output=True,
        text=True,
    )
    assert non_admin.returncode != 0
    assert "instance-admin" in non_admin.stderr
    assert active_path.read_text() == str(src)
    assert (proof_dir / "telegram-loaded.json").is_file()
    assert not (home / ".paperclip/plugin-rollbacks").exists()

    failed_env = run_env | {"FAIL_TARGET_ATTESTATION": "1"}
    failed = subprocess.run(
        ["bash", "-c", runner, "telegram-install-test", str(REPO)],
        env=failed_env,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
    assert "runtime attestation" in failed.stderr
    pending_after_rollback = proof_dir / "telegram-pending-reinstall.json"
    assert pending_after_rollback.is_file()
    assert not (proof_dir / "telegram-loaded.json").exists()
    rollback_active = Path(active_path.read_text())
    assert "plugin-rollbacks" in str(rollback_active)
    assert "generation = 'old'" in (rollback_active / "dist/worker.js").read_text()

    blocked_retry = subprocess.run(
        ["bash", "-c", runner, "telegram-install-test", str(REPO)],
        env=run_env,
        capture_output=True,
        text=True,
    )
    assert blocked_retry.returncode != 0
    assert "unfinished telegram plugin transaction" in blocked_retry.stderr
    assert pending_after_rollback.is_file()
    pending_after_rollback.unlink()

    result = subprocess.run(
        ["bash", "-c", runner, "telegram-install-test", str(REPO)],
        env=run_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    proof = json.loads((home / ".paperclip/plugin-proofs/telegram-loaded.json").read_text())
    assert proof["source_ref"] == new_sha
    assert proof["source_head"] == new_sha
    assert proof["schema_version"] == "telegram-plugin-loaded-proof/v2"
    target = Path(proof["package_path"])
    assert target != src
    assert proof["source_head"] == new_sha
    assert proof["runtime_attestation"] == {
        "action": "send_to_telegram",
        "code": "invalid_route_context",
        "invalid_field": "issueIdentifier",
    }
    assert proof["worker_sha256"] == hashlib.sha256(
        (target / "dist/worker.js").read_bytes()
    ).hexdigest()
    assert proof["registry_healthy"] is True
    assert not pending_after_rollback.exists()
    assert _git("rev-parse", "HEAD", cwd=src, env=env) == old_sha
    assert "generation = 'old'" in (src / "worker-src.js").read_text()
    assert "generation = 'new'" in (target / "dist/worker.js").read_text()
    assert active_path.read_text() == str(target)

    rollback = json.loads(Path(proof["rollback_manifest"]).read_text())
    assert rollback["source_ref"] == old_sha
    rollback_worker = Path(rollback["package_path"]) / "dist/worker.js"
    assert "generation = 'old'" in rollback_worker.read_text()
    assert rollback["worker_sha256"] == hashlib.sha256(rollback_worker.read_bytes()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", rollback["package_tree_sha256"])
    assert Path(proof["rollback_manifest"]).stat().st_mode & 0o222 == 0

    calls = curl_log.read_text()
    assert "DELETE http://paperclip.test/api/plugins/plugin-id" in calls
    assert "POST http://paperclip.test/api/plugins/install" in calls
