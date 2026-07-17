"""ThorChain Paperclip assembly contract from the approved rollout spec."""

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "paperclips" / "projects" / "thorchain"
MANIFEST = PROJECT / "paperclip-agent-assembly.yaml"
RESOLVED = REPO / "paperclips" / "dist" / "thorchain.resolved-assembly.json"


def _manifest():
    return yaml.safe_load(MANIFEST.read_text())


def test_thorchain_manifest_is_clean_and_valid():
    from paperclips.scripts.validate_manifest import validate_manifest

    validate_manifest(MANIFEST)
    text = MANIFEST.read_text()
    for forbidden in ["/Users/", "/home/", "company_id:", "agent_id:"]:
        assert forbidden not in text


def test_thorchain_roster_is_exactly_five_codex_56_agents():
    agents = _manifest()["agents"]
    expected = {
        "ThorChainCEO": ("ceo", "crown", "cto", "outer_walker", None),
        "ThorChainCTO": ("cto", "shield", "cto", "inner_orchestrator", "ThorChainCEO"),
        "ThorChainCodeReviewer": ("engineer", "eye", "reviewer", "reviewer", "ThorChainCTO"),
        "ThorChainSwiftEngineer": ("engineer", "code", "implementer", "implementer", "ThorChainCTO"),
        "ThorChainQAEngineer": ("qa", "bug", "qa", "qa", "ThorChainCTO"),
    }

    assert len(agents) == 5
    assert len({agent["agent_name"] for agent in agents}) == 5
    for agent in agents:
        role, icon, profile, workflow_role, reports_to = expected[agent["agent_name"]]
        assert agent["target"] == "codex"
        assert agent["model"] == "gpt-5.6-sol"
        assert agent["modelReasoningEffort"] == "xhigh"
        assert agent["paperclip_role"] == role
        assert agent["paperclip_icon"] == icon
        assert agent["profile"] == profile
        assert agent["workflow_role"] == workflow_role
        assert agent.get("reportsTo") == reports_to


def test_thorchain_project_identity_and_required_host_roots():
    manifest = _manifest()
    assert manifest["project"] == {
        "key": "thorchain",
        "display_name": "ThorChainKit",
        "system_name": "ThorChainKit.Swift",
        "issue_prefix": "THR",
        "integration_branch": "main",
        "specs_dir": "docs/specs",
        "plans_dir": "docs/plans",
    }
    assert manifest["host_paths"]["required_existing"] == [
        "gimle_skills_root",
        "vultisig_repo_root",
        "unstoppable_ios_repo_root",
        "tronkit_repo_root",
        "evmkit_repo_root",
    ]


def test_thorchain_project_files_and_slim_roles_exist():
    required = [
        "WORKFLOW.md",
        "bindings.local-example.yaml",
        "paths.local-example.yaml",
        "fragments/local/agent-roster.md",
        "overlays/codex/_common.md",
        "roles-codex/thorchain-ceo.md",
        "roles-codex/thorchain-cto.md",
        "roles-codex/thorchain-code-reviewer.md",
        "roles-codex/thorchain-swift-engineer.md",
        "roles-codex/thorchain-qa-engineer.md",
    ]
    for relative in required:
        assert (PROJECT / relative).is_file(), relative


def test_workflow_preserves_approval_handoff_and_activation_boundaries():
    text = (PROJECT / "WORKFLOW.md").read_text()
    for marker in [
        "explicit user approval",
        "POST",
        "/comments",
        "PATCH",
        "one read-only verification",
        "STOP",
        "creates no roadmap issue",
        "Maestro",
        "iOS Example",
    ]:
        assert marker in text


def test_common_overlay_requires_current_analog_and_three_read_only_review_lanes():
    text = (PROJECT / "overlays" / "codex" / "_common.md").read_text()
    for marker in [
        "analog-driven-change",
        "gimle-evidence",
        "codebase-memory",
        "Serena",
        "Vultisig",
        "architecture/boundaries",
        "security/protocol-safety",
        "verification/operability",
        "gpt-5.6-sol",
        "Maestro",
        "iOS Example",
    ]:
        assert marker in text


def test_rendered_codex_assembly_has_thr_identity_and_no_unresolved_templates():
    resolved = json.loads(RESOLVED.read_text())
    assert resolved["parameters"]["project"]["issuePrefix"] == "THR"
    roles = resolved["targets"]["codex"]["roles"]
    assert {role["agentName"] for role in roles} == {
        "ThorChainCEO",
        "ThorChainCTO",
        "ThorChainCodeReviewer",
        "ThorChainSwiftEngineer",
        "ThorChainQAEngineer",
    }
    for role in roles:
        rendered = REPO / role["output"]
        assert rendered.is_file()
        assert "{{" not in rendered.read_text()
