import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import unstoppable_audit_team as team


def load_team_config():
    config_path = Path(__file__).resolve().parents[1] / "teams" / "unstoppable-audit.yaml"
    return team.load_config(config_path)


def test_roster_contains_full_gate_b1_team():
    config = load_team_config()
    agents = team.build_agent_plan(config, Path(__file__).resolve().parents[2], Path("paperclips/dist/codex/unstoppable-audit"))

    assert len(agents) == 17
    assert {agent["name"] for agent in agents} == {
        "AUCEO",
        "UWICTO",
        "UWISwiftAuditor",
        "UWISecurityAuditor",
        "UWICryptoAuditor",
        "UWIInfraEngineer",
        "UWIResearchAgent",
        "UWIQAEngineer",
        "UWITechnicalWriter",
        "UWACTO",
        "UWAKotlinAuditor",
        "UWASecurityAuditor",
        "UWACryptoAuditor",
        "UWAInfraEngineer",
        "UWAResearchAgent",
        "UWAQAEngineer",
        "UWATechnicalWriter",
    }


def test_agent_runtime_is_audit_only():
    config = load_team_config()
    agents = team.build_agent_plan(config, Path(__file__).resolve().parents[2], Path("paperclips/dist/codex/unstoppable-audit"))

    for agent in agents:
        assert agent["adapterType"] == "codex_local"
        assert agent["instructionsBundleMode"] == "managed"
        assert agent["instructionsFilePath"] == "AGENTS.md"
        assert agent["sandboxBypass"] is False
        assert agent["extraArgs"] == ["--skip-git-repo-check"]
        assert agent["expectedConfig"]["adapterConfig"]["extraArgs"] == ["--skip-git-repo-check"]
        assert agent["plannedOperation"] == "create"
        assert "PAPERCLIP_API_KEY" not in agent["runtimeEnvKeys"]
        assert "GITHUB_TOKEN" not in agent["runtimeEnvKeys"]
        assert all("/repos/" not in root for root in agent["writableRoots"])


def test_manifest_marks_live_readback_unchecked():
    config_path = Path(__file__).resolve().parents[1] / "teams" / "unstoppable-audit.yaml"
    config = team.load_config(config_path)
    agents = team.build_agent_plan(config, Path(__file__).resolve().parents[2], Path("paperclips/dist/codex/unstoppable-audit"))
    manifest = team.build_manifest(config, agents, config_path)

    assert manifest["ok"] is True
    assert manifest["mode"] == "unauthenticated-dry-run"
    assert manifest["live_readback"]["checked"] is False
    assert manifest["apply_policy"]["live_apply_allowed"] is False
    assert manifest["apply_policy"]["requires_authenticated_preflight"] is True
    assert manifest["dry_run_config_hash"]


def test_rendered_bundle_contains_required_ua_markers(tmp_path):
    config = load_team_config()
    agents = team.build_agent_plan(config, tmp_path, Path("paperclips/dist/codex/unstoppable-audit"))
    team.render_bundles(agents[:1], config, tmp_path)

    text = (tmp_path / agents[0]["bundlePath"]).read_text(encoding="utf-8")

    assert "UnstoppableAudit" in text
    assert "codebase-memory" in text
    assert "Serena" in text
    assert "Paperclip one-issue handoff" in text
    assert "Audit-Only Runtime Policy" in text
    assert "Telegram receives redacted artifacts" in text
    assert "Gimle" not in text


def test_validate_agent_plan_rejects_admin_runtime_env():
    agent = {
        "name": "BadAgent",
        "adapterType": "codex_local",
        "instructionsBundleMode": "managed",
        "instructionsFilePath": "AGENTS.md",
        "sandboxBypass": False,
        "runtimeEnvKeys": ["PAPERCLIP_API_KEY"],
        "writableRoots": ["/Users/Shared/UnstoppableAudit/artifacts/BadAgent"],
    }

    with pytest.raises(ValueError, match="forbidden runtime env"):
        team.validate_agent_plan(agent)


def test_preflight_rejects_stale_dry_run_manifest():
    config_path = Path(__file__).resolve().parents[1] / "teams" / "unstoppable-audit.yaml"
    config = team.load_config(config_path)
    agents = team.build_agent_plan(config, Path(__file__).resolve().parents[2], Path("paperclips/dist/codex/unstoppable-audit"))
    current = team.build_manifest(config, agents, config_path)
    stale = dict(current)
    stale["dry_run_config_hash"] = "stale"

    errors = team.assert_fresh_dry_run(stale, current)

    assert "dry-run manifest is stale against current team config" in errors


def test_decide_agent_refuses_paused_auceo():
    config = load_team_config()
    agents = team.build_agent_plan(config, Path(__file__).resolve().parents[2], Path("paperclips/dist/codex/unstoppable-audit"))
    auceo = next(agent for agent in agents if agent["name"] == "AUCEO")
    live = {
        "id": "dcdd8871-5b44-4563-bb00-f8cca292a69e",
        "name": "AUCEO",
        "status": "paused",
    }
    live_config = {
        "adapterType": "codex_local",
        "adapterConfig": {
            "cwd": auceo["workspacePath"],
            "model": auceo["model"],
            "modelReasoningEffort": auceo["reasoningEffort"],
            "instructionsFilePath": "AGENTS.md",
            "instructionsBundleMode": "managed",
            "dangerouslyBypassApprovalsAndSandbox": False,
            "env": {key: "redacted" for key in auceo["runtimeEnvKeys"]},
        },
    }

    decision = team.decide_agent(
        auceo,
        [live],
        live_config,
        "dcdd8871-5b44-4563-bb00-f8cca292a69e",
    )

    assert decision["decision"] == "refuse"
    assert decision["ok"] is False
    assert any("status is paused" in blocker for blocker in decision["blockers"])


def test_decide_agent_recreate_policy_accepts_paused_auceo_with_snapshot():
    config = load_team_config()
    agents = team.build_agent_plan(config, Path(__file__).resolve().parents[2], Path("paperclips/dist/codex/unstoppable-audit"))
    auceo = next(agent for agent in agents if agent["name"] == "AUCEO")
    live = {
        "id": "dcdd8871-5b44-4563-bb00-f8cca292a69e",
        "name": "AUCEO",
        "status": "paused",
    }
    live_config = {
        "adapterType": "codex_local",
        "adapterConfig": {
            "cwd": None,
            "model": auceo["model"],
            "instructionsFilePath": "/tmp/live/AGENTS.md",
            "instructionsBundleMode": "managed",
            "dangerouslyBypassApprovalsAndSandbox": True,
            "env": {},
        },
    }

    decision = team.decide_agent(
        auceo,
        [live],
        live_config,
        "dcdd8871-5b44-4563-bb00-f8cca292a69e",
        "recreate",
    )

    assert decision["decision"] == "recreate"
    assert decision["ok"] is True
    assert decision["blockers"] == []
    assert decision["rollbackSnapshot"]["agent"]["id"] == "dcdd8871-5b44-4563-bb00-f8cca292a69e"
    assert decision["recreatePlan"]["terminate_existing_agent_id"] == "dcdd8871-5b44-4563-bb00-f8cca292a69e"
    assert any("readback diverges" in warning for warning in decision["warnings"])


def test_decide_agent_allows_create_when_missing():
    config = load_team_config()
    agents = team.build_agent_plan(config, Path(__file__).resolve().parents[2], Path("paperclips/dist/codex/unstoppable-audit"))
    agent = next(agent for agent in agents if agent["name"] == "UWICTO")

    decision = team.decide_agent(agent, [], None, "dcdd8871-5b44-4563-bb00-f8cca292a69e")

    assert decision["decision"] == "create"
    assert decision["ok"] is True
    assert decision["live"]["found"] is False


def test_compare_readback_rejects_forbidden_live_env_key():
    config = load_team_config()
    agents = team.build_agent_plan(config, Path(__file__).resolve().parents[2], Path("paperclips/dist/codex/unstoppable-audit"))
    agent = next(agent for agent in agents if agent["name"] == "UWICTO")
    live_config = {
        "adapterType": "codex_local",
        "adapterConfig": {
            "cwd": agent["workspacePath"],
            "model": agent["model"],
            "modelReasoningEffort": agent["reasoningEffort"],
            "instructionsFilePath": "AGENTS.md",
            "instructionsBundleMode": "managed",
            "dangerouslyBypassApprovalsAndSandbox": False,
            "env": {
                "CODEBASE_MEMORY_PROJECT": "redacted",
                "SERENA_PROJECT": "redacted",
                "TELEGRAM_REDACTED_REPORTS_CHAT_ID": "redacted",
                "TELEGRAM_OPS_CHAT_ID": "redacted",
                "PAPERCLIP_API_KEY": "redacted",
            },
        },
    }

    divergences = team.compare_readback(agent, live_config)

    assert any("forbidden keys" in divergence for divergence in divergences)
