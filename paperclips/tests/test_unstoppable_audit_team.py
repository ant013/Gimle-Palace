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
