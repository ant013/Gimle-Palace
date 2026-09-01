"""Glitcherry Android Paperclip assembly contract from the approved design."""

import json
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "paperclips" / "projects" / "glitcherry-android"
MANIFEST = PROJECT / "paperclip-agent-assembly.yaml"
RESOLVED = REPO / "paperclips" / "dist" / "glitcherry-android.resolved-assembly.json"


def _manifest():
    return yaml.safe_load(MANIFEST.read_text())


def _role(name: str) -> str:
    return (PROJECT / "roles-codex" / name).read_text()


def test_glitcherry_manifest_is_clean_valid_and_workspace_rooted():
    from paperclips.scripts.validate_manifest import validate_manifest

    validate_manifest(MANIFEST)
    data = _manifest()
    text = MANIFEST.read_text()

    assert data["project"] == {
        "key": "glitcherry-android",
        "display_name": "Glitcherry Android",
        "system_name": "Glitcherry-Android",
        "issue_prefix": "GLA",
        "integration_branch": "develop",
        "specs_dir": "docs/specs",
        "plans_dir": "docs/plans",
    }
    assert data["sandbox"] == {
        "mode": "constrained",
        "bypass_approvals_and_sandbox": False,
        "runtime_env": {"PAPERCLIP_API_URL": "paperclip_runtime_api_url"},
    }
    assert "workspace_git_source_path_key" not in text
    for forbidden in ["/Users/", "/home/", "company_id:", "agent_id:"]:
        assert forbidden not in text


def test_glitcherry_roster_is_exactly_the_approved_six_agents():
    agents = _manifest()["agents"]
    expected = {
        "GlitcherryCEO": ("ceo", "crown", "minimal", "governance", "high", None),
        "GlitcherryCTO": (
            "cto", "shield", "walker", "inner_orchestrator", "xhigh", "GlitcherryCEO",
        ),
        "GlitcherryAndroidEngineer": (
            "engineer", "code", "implementer", "platform_implementer", "high", "GlitcherryCTO",
        ),
        "GlitcherryMediaPipelineEngineer": (
            "engineer", "atom", "implementer", "media_implementer", "xhigh", "GlitcherryCTO",
        ),
        "GlitcherryCodeReviewer": (
            "engineer", "eye", "reviewer", "reviewer", "xhigh", "GlitcherryCTO",
        ),
        "GlitcherryQAEngineer": (
            "qa", "bug", "reviewer", "qa", "high", "GlitcherryCTO",
        ),
    }

    assert len(agents) == len(expected)
    assert {agent["agent_name"] for agent in agents} == set(expected)
    assert sum(agent["workflow_role"] == "inner_orchestrator" for agent in agents) == 1
    assert all(agent["workflow_role"] != "outer_walker" for agent in agents)
    for agent in agents:
        role, icon, profile, workflow_role, effort, reports_to = expected[agent["agent_name"]]
        assert agent["target"] == "codex"
        assert agent["model"] == "gpt-5.6-sol"
        assert agent["modelReasoningEffort"] == effort
        assert agent["paperclip_role"] == role
        assert agent["paperclip_icon"] == icon
        assert agent["profile"] == profile
        assert agent["workflow_role"] == workflow_role
        assert agent.get("reportsTo") == reports_to


def test_glitcherry_project_files_and_portable_local_examples_exist():
    required = [
        "WORKFLOW.md",
        "bindings.local-example.yaml",
        "paths.local-example.yaml",
        "fragments/local/agent-roster.md",
        "overlays/codex/_common.md",
        "roles-codex/glitcherry-ceo.md",
        "roles-codex/glitcherry-cto.md",
        "roles-codex/android-engineer.md",
        "roles-codex/media-pipeline-engineer.md",
        "roles-codex/code-reviewer.md",
        "roles-codex/qa-engineer.md",
        "references/media-skill-sources.md",
    ]
    for relative in required:
        assert (PROJECT / relative).is_file(), relative

    paths = yaml.safe_load((PROJECT / "paths.local-example.yaml").read_text())
    assert paths["team_workspace_root"] == "/opt/example/glitcherry-paperclip-runs"
    assert paths["android_repository_url"] == "https://github.com/ant013/Glitcherry-Android.git"
    assert paths["control_repository_url"] == "https://github.com/ant013/Glitcherry.git"
    assert paths["paperclip_runtime_api_url"].startswith("http://127.0.0.1:")


def test_workflow_is_the_single_seven_phase_parent_child_contract():
    text = (PROJECT / "WORKFLOW.md").read_text()
    required = [
        "single lifecycle authority",
        "approved sprint identifier",
        "ROADMAP.md head SHA",
        "parentId",
        "blockedByIssueIds",
        "issue_blockers_resolved",
        "issue_children_completed",
        "Phase 1 — Spec",
        "Phase 2 — Independent spec review",
        "Phase 3 — Plan and independent plan review",
        "Phase 4 — Implementation by exactly one engineer",
        "Phase 5 — Exact-head code and architecture review",
        "Phase 6 — QA",
        "Phase 7 — Integrate, synchronize, and clean",
        "GLA-N + Android merge SHA",
        "POST evidence",
        "PATCH assignee/status",
        "one read-only verification",
        "STOP",
        "LOCAL_BLOCKED",
        "ROADMAP_BLOCKED",
        "creates no roadmap or product issue",
    ]
    for marker in required:
        assert marker in text

    forbidden = [
        "relatedWork.outbound",
        "Phase 3.2",
        "OpusArchitectReviewer",
        "release-cut planned",
    ]
    for marker in forbidden:
        assert marker not in text


def test_common_overlay_enforces_authority_repositories_and_one_writer():
    text = (PROJECT / "overlays" / "codex" / "_common.md").read_text()
    required = [
        "WORKFLOW.md",
        "Human Engineering Lead",
        "workspace/repo",
        "workspace/control",
        "workspace/AGENTS.md",
        "exactly one primary implementer",
        "integration branch is `develop`",
        "never release, sign, tag, or publish",
        "POST evidence",
        "one read-only verification",
    ]
    for marker in required:
        assert marker in text


def test_role_crafts_preserve_exact_write_and_review_boundaries():
    ceo = _role("glitcherry-ceo.md")
    cto = _role("glitcherry-cto.md")
    android = _role("android-engineer.md")
    media = _role("media-pipeline-engineer.md")
    reviewer = _role("code-reviewer.md")
    qa = _role("qa-engineer.md")

    assert "governance authority only" in ceo
    for marker in ["only merge authority", "READY", "spec", "plan", "cleanup"]:
        assert marker in cto
    assert "picker/import" in android and "MediaStore/share" in android
    assert "exactly one primary implementer" in android
    assert "EditedMediaItem" in media and "Composition" in media
    assert "CompositionPlayer" in media and "@ExperimentalApi" in media
    assert "Android 13+" in media and "API 33" in media
    assert "Media3 `1.11.0`" in media
    assert "independent spec" in reviewer and "exact PR head" in reviewer
    assert "architecture" in reviewer and "never implement fixes" in reviewer
    assert "detached read-only" in qa and "never commit or push" in qa
    for marker in ["same implementer", "scope drift", "LOCAL_BLOCKED", "Human Engineering Lead"]:
        assert marker in qa


def test_media_reference_is_pinned_licensed_and_reference_only():
    text = (PROJECT / "references" / "media-skill-sources.md").read_text()
    required = [
        "1d74b4953d21ee31a3acf61eff68972e100c2ac3",
        "Apache-2.0",
        "60aaae52bb2af8162732751a4332f62a5fef518b",
        "MIT",
        "c5bf6731b8441019418784484cca1578413e6ad3",
        "Media3 1.11.0",
        "reference only",
        "must not install",
        "must not execute",
    ]
    for marker in required:
        assert marker in text


def test_rendered_glitcherry_roles_have_no_templates_or_forbidden_authority():
    resolved = json.loads(RESOLVED.read_text())
    assert resolved["parameters"]["project"]["issuePrefix"] == "GLA"
    roles = resolved["targets"]["codex"]["roles"]
    assert {role["agentName"] for role in roles} == {
        "GlitcherryCEO",
        "GlitcherryCTO",
        "GlitcherryAndroidEngineer",
        "GlitcherryMediaPipelineEngineer",
        "GlitcherryCodeReviewer",
        "GlitcherryQAEngineer",
    }

    rendered = {role["agentName"]: (REPO / role["output"]).read_text() for role in roles}
    for text in rendered.values():
        assert "{{" not in text
        assert "WORKFLOW.md" in text

    ceo = rendered["GlitcherryCEO"]
    cto = rendered["GlitcherryCTO"]
    qa = rendered["GlitcherryQAEngineer"]
    assert "## Plan Producer" not in ceo
    assert "## Commit and Push" not in ceo
    assert "## CTO Merge Authority" not in ceo
    assert "release-cut" not in cto.lower()
    assert "develop -> main" not in cto.lower()
    assert "## Commit and Push" not in qa
    assert "commit push" not in qa.lower()
