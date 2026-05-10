import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import unstoppable_audit_prereq as prereq


def test_config_contains_expected_ids_and_routes():
    config_path = Path(__file__).resolve().parents[1] / "teams" / "unstoppable-audit.yaml"
    config = prereq.parse_simple_yaml(config_path)

    assert prereq.get_path(config, "team") == "UnstoppableAudit"
    assert prereq.get_path(config, "paperclip.company_id") == "8f55e80b-0264-4ab6-9d56-8b2652f18005"
    assert prereq.get_path(config, "paperclip.onboarding_project_id") == "64871690-2f2d-4fbd-a30d-975e6bbccec9"
    assert prereq.get_path(config, "paperclip.existing_early_ceo_agent_id") == "dcdd8871-5b44-4563-bb00-f8cca292a69e"
    assert str(prereq.get_path(config, "telegram.redacted_reports_chat_id")) == "-1003937871684"
    assert str(prereq.get_path(config, "telegram.ops_chat_id")) == "-1003534905521"
    assert str(prereq.get_path(config, "codex.home_root")).endswith("/companies")
    assert "/Users/anton/.local/bin" in str(prereq.get_path(config, "codex.path"))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-1003937871684", True),
        ("-1003534905521", True),
        ("3937871684", False),
        ("https://t.me/c/3937871684/2", False),
        ("", False),
    ],
)
def test_validate_chat_id(value, expected):
    assert prereq.validate_chat_id(value) is expected


def test_owner_only_mode_accepts_private_directory(tmp_path):
    private_dir = tmp_path / "private"
    private_dir.mkdir()
    private_dir.chmod(0o700)

    try:
        assert prereq.owner_only_mode(private_dir) is True
    finally:
        private_dir.chmod(0o755)


def test_owner_only_mode_rejects_group_world_accessible_directory(tmp_path):
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    public_dir.chmod(0o755)

    assert prereq.owner_only_mode(public_dir) is False


def test_missing_required_key_is_reported(tmp_path):
    config_path = tmp_path / "broken.yaml"
    config_path.write_text(
        "\n".join(
            [
                "team: UnstoppableAudit",
                "paperclip:",
                "  company_id: 8f55e80b-0264-4ab6-9d56-8b2652f18005",
            ]
        ),
        encoding="utf-8",
    )

    manifest = prereq.verify(config_path, tmp_path)

    required = next(check for check in manifest["checks"] if check["name"] == "config.required_keys")
    assert manifest["ok"] is False
    assert required["status"] == "blocker"
    assert "repositories.ios.url" in required["details"]["missing"]


def test_verify_does_not_emit_environment_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERCLIP_TOKEN", "secret-token")
    artifact_root = tmp_path / "artifacts"
    run_root = tmp_path / "runs"
    repos_root = tmp_path / "repos"
    for path in [artifact_root, run_root, repos_root]:
        path.mkdir()
        path.chmod(0o700)

    ios_mirror = repos_root / "ios.git"
    android_mirror = repos_root / "android.git"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
team: UnstoppableAudit
paperclip:
  company_id: 8f55e80b-0264-4ab6-9d56-8b2652f18005
  onboarding_project_id: 64871690-2f2d-4fbd-a30d-975e6bbccec9
  existing_early_ceo_agent_id: dcdd8871-5b44-4563-bb00-f8cca292a69e
repositories:
  ios:
    url: https://github.com/horizontalsystems/unstoppable-wallet-ios
    mirror_path: {ios_mirror}
  android:
    url: https://github.com/horizontalsystems/unstoppable-wallet-android
    mirror_path: {android_mirror}
telegram:
  redacted_reports_chat_id: -1003937871684
  ops_chat_id: -1003534905521
codex:
  home_root: /Users/anton/.paperclip/instances/default/companies
  path: /usr/bin:/bin
models:
  default_model: gpt-5.4
  default_reasoning_effort: high
roots:
  stable_mirror_root: {repos_root}
  run_root: {run_root}
  artifact_root: {artifact_root}
codebase_memory:
  ios_project: unstoppable-wallet-ios
  android_project: unstoppable-wallet-android
  audit_storage_phase1: skipped
neo4j:
  audit_storage_phase1: skipped
""",
        encoding="utf-8",
    )

    manifest = prereq.verify(config_path, tmp_path)

    assert "secret-token" not in str(manifest)
    assert "PAPERCLIP_TOKEN" not in str(manifest)
