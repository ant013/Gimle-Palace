"""fullAudit Paperclip assembly and constrained-sandbox contract."""

import json
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "paperclips" / "projects" / "fullaudit"
MANIFEST = PROJECT / "paperclip-agent-assembly.yaml"
RESOLVED = REPO / "paperclips" / "dist" / "fullaudit.resolved-assembly.json"


def manifest():
    return yaml.safe_load(MANIFEST.read_text())


def test_fullaudit_manifest_is_valid_and_has_no_machine_specific_paths():
    from paperclips.scripts.validate_manifest import validate_manifest

    validate_manifest(MANIFEST)
    text = MANIFEST.read_text()
    for forbidden in ["/Users/", "/home/", "company_id:", "agent_id:"]:
        assert forbidden not in text


def test_fullaudit_exactly_models_the_eight_role_team_and_writes_are_minimal():
    data = manifest()
    assert data["project"]["key"] == "fullaudit"
    assert data["project"]["issue_prefix"] == "FUL"
    assert data["sandbox"] == {"mode": "constrained"}
    assert data["host_paths"]["required_existing"] == ["project_root", "gimle_skills_root"]

    expected = {
        "FullAuditCEO": ("ceo", None),
        "FullAuditCTO": ("cto", ["runs"]),
        "FullAuditSwiftAuditor": ("security", None),
        "FullAuditKotlinAuditor": ("security", None),
        "FullAuditProtocolAuditor": ("security", None),
        "FullAuditEvidenceReviewer": ("security", None),
        "FullAuditReportPublisher": ("engineer", ["runs", "reports", "site/dist"]),
        "FullAuditQAEngineer": ("qa", None),
    }
    agents = data["agents"]
    assert len(agents) == len(expected)
    assert {agent["agent_name"] for agent in agents} == set(expected)
    for agent in agents:
        role, writable_paths = expected[agent["agent_name"]]
        assert agent["target"] == "codex"
        assert agent["model"] == "gpt-5.6-sol"
        assert agent["modelReasoningEffort"] == "xhigh"
        assert agent["paperclip_role"] == role
        assert agent.get("sandbox", {}).get("writable_paths") == writable_paths


def test_fullaudit_includes_read_only_domain_and_verifier_contracts():
    auditor = PROJECT / "codex-agents" / "fullaudit-domain-auditor.toml"
    verifier = PROJECT / "codex-agents" / "fullaudit-verifier.toml"
    assert auditor.is_file()
    assert verifier.is_file()
    assert 'sandbox_mode = "read-only"' in auditor.read_text()
    assert 'sandbox_mode = "read-only"' in verifier.read_text()
    for path in ["WORKFLOW.md", "fragments/local/agent-roster.md", "overlays/codex/_common.md"]:
        assert (PROJECT / path).is_file(), path


def test_bootstrap_retains_legacy_default_but_enforces_constrained_fullaudit_roots():
    text = (REPO / "paperclips" / "scripts" / "bootstrap-project.sh").read_text()
    assert 'sandbox_mode=$(yq -r \'.sandbox.mode // "legacy"\' "$manifest")' in text
    assert "sandbox_bypass=true" in text
    assert 'if [ "$sandbox_mode" = "constrained" ]; then' in text
    assert 'kit_root="${project_root}/workspace/repos"' in text
    assert "may not target Git metadata or environment files" in text
    assert "dangerouslyBypassApprovalsAndSandbox: $bypass" in text
    assert "writableRoots: $writable" in text
    assert "sourceRootsReadOnly: $readonly" in text


def test_bootstrap_builds_from_its_repository_not_the_callers_cwd():
    text = (REPO / "paperclips" / "scripts" / "bootstrap-project.sh").read_text()
    build_section = text[text.index('log info "[9/13] building agent prompts"'):text.index('# Step 10:')]
    assert 'cd "$REPO_ROOT"' in build_section
    assert '"${REPO_ROOT}/paperclips/build.sh" --project "$project_key" --target "$target"' in build_section


def test_rendered_assembly_contains_only_full_audit_roles_without_templates():
    resolved = json.loads(RESOLVED.read_text())
    assert resolved["parameters"]["project"]["issuePrefix"] == "FUL"
    roles = resolved["targets"]["codex"]["roles"]
    assert len(roles) == 8
    for role in roles:
        rendered = REPO / role["output"]
        assert rendered.is_file()
        assert "{{" not in rendered.read_text()
