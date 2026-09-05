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


def _flat(text: str) -> str:
    return " ".join(text.split())


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
        "bypass_approvals_and_sandbox": True,
        "runtime_env": {"PAPERCLIP_API_URL": "paperclip_runtime_api_url"},
    }
    assert data["recovery"] == {
        "model": "gpt-5.6-terra",
        "preserve_primary_reasoning_effort": True,
    }
    assert data["smoke"] == {"e2e_timeout_seconds": 360}
    assert data["targets"]["codex"]["require_instructions_file"] is True
    required_directories = set(data["host_paths"]["required_existing"])
    assert "slice_controller_path" not in required_directories
    assert {
        "project_root",
        "primary_repo_root",
        "control_repo_root",
        "task_worktree_root",
        "task_state_root",
    } <= required_directories
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
        assert not agent["model"].startswith("gpt-5.3")
        assert agent["modelReasoningEffort"] == effort
        assert agent["modelReasoningEffort"] != "low"
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
        "scripts/reconcile-paperclip-project.sh",
        "scripts/slice-worktree.py",
    ]
    for relative in required:
        assert (PROJECT / relative).is_file(), relative

    paths = yaml.safe_load((PROJECT / "paths.local-example.yaml").read_text())
    assert paths["team_workspace_root"] == "/opt/example/glitcherry-paperclip-runs"
    assert paths["task_worktree_root"] == "/opt/example/glitcherry-slice-worktrees"
    assert paths["task_state_root"] == "/opt/example/glitcherry-slice-state"
    assert paths["slice_controller_path"].endswith("/scripts/slice-worktree.py")
    assert "slice_lease_seconds" not in paths
    assert paths["android_repository_url"] == "https://github.com/ant013/Glitcherry-Android.git"
    assert paths["control_repository_url"] == "https://github.com/ant013/Glitcherry.git"
    assert paths["paperclip_runtime_api_url"].startswith("http://127.0.0.1:")

    bindings = yaml.safe_load((PROJECT / "bindings.local-example.yaml").read_text())
    assert bindings["project_workspace_id"] == "00000000-0000-0000-0000-000000000420"


def test_workflow_is_the_single_worktree_parent_child_contract():
    text = (PROJECT / "WORKFLOW.md").read_text()
    required = [
        "single lifecycle authority",
        "approved sprint identifier",
        "ROADMAP.md head SHA",
        "parentId",
        "blockedByIssueIds",
        "issue_blockers_resolved",
        "issue_children_completed",
        "Phase 1 — Adopt Paperclip worktree and materialize spec",
        "Phase 2 — Independent spec review",
        "Phase 3 — Plan and independent plan review",
        "Phase 4 — Implementation by exactly one engineer",
        "Phase 5 — Exact-head code and architecture review",
        "Phase 6 — Integrate, synchronize, and clean",
        "Sprint smoke gate — QA only here",
        "task_worktree_root",
        "task_state_root",
        "GLITCHERRY_INTERRUPT_HANDOFF_V2",
        "GLITCHERRY_HANDOFF_TARGET_V2",
        "maximum three",
        "fourth autonomous",
        "SPRINT_SMOKE_REQUIRED",
        "GLA-N + Android merge SHA",
        "POST evidence",
        "PATCH assignee/status",
        "without `interrupt`",
        "interrupt: true",
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


def test_plan_authority_mirror_and_confirmation_classifier_are_explicit():
    workflow = _flat((PROJECT / "WORKFLOW.md").read_text())
    cto = _flat(_role("glitcherry-cto.md"))
    reviewer = _flat(_role("code-reviewer.md"))

    for marker in [
        "tracked `docs/plans/...` file",
        "implementation authority",
        "Paperclip `plan` document",
        "byte-identical mirror",
        "`baseRevisionId`",
        "tracked-plan SHA-256",
        "mirrored-body SHA-256",
        "revision ID and revision number",
        "product behavior",
        "roadmap or slice scope/order",
        "production dependency, toolchain, or API floor",
        "quality threshold or pass/fail meaning",
        "cited accepted ADR or explicitly named architecture boundary",
        "standing autonomous correction policy",
    ]:
        assert marker in workflow

    for marker in [
        "Before every `plan_review` handoff",
        "byte-identical mirror",
        "`baseRevisionId`",
        "read back",
        "both SHA-256 hashes",
        "revision ID and revision number",
        "project-wide standing delegation",
    ]:
        assert marker in cto

    for marker in [
        "verify the plan mirror before technical review",
        "absent, stale, or divergent",
        "byte-identical",
        "Do not request issue-specific or duplicate human confirmation",
        "project-wide standing delegation",
    ]:
        assert marker in reviewer


def test_standing_autonomous_corrections_are_scenario_complete_and_role_safe():
    workflow = _flat((PROJECT / "WORKFLOW.md").read_text())
    common = _flat((PROJECT / "overlays" / "codex" / "_common.md").read_text())
    cto = _flat(_role("glitcherry-cto.md"))
    android = _flat(_role("android-engineer.md"))
    media = _flat(_role("media-pipeline-engineer.md"))
    reviewer = _flat(_role("code-reviewer.md"))
    ceo = _flat(_role("glitcherry-ceo.md"))
    qa = _flat(_role("qa-engineer.md"))

    for marker in [
        "GLITCHERRY_STANDING_AUTONOMY_V1",
        "Correcting actual buggy behavior",
        "technical_triage",
        "Each new clean correction HEAD",
    ]:
        assert marker in workflow
        assert marker in common

    for marker in [
        "uses controller `reject`",
        "no synthetic plan edit",
        "does not consume a product verification attempt",
        "a cited accepted ADR or explicitly named architecture boundary",
        "Unavailability of Serena, codebase-memory, Context7",
    ]:
        assert marker in workflow

    for marker in [
        "reject -> implementation_fix -> code_review",
        "without a synthetic plan revision",
        "does not consume the product attempt",
        "a cited accepted ADR or explicitly named architecture boundary",
        "Advisory MCP failure",
    ]:
        assert marker in common

    for role in (cto, android, media, reviewer):
        assert "standing" in role.lower()
        assert "technical_triage" in role
        assert "pinned contract" in role

    assert "do not consume a review cycle" in cto
    assert "Each controller `reject` consumes one" in cto
    assert "same worktree/branch/PR" in android
    assert "same worktree/branch/PR" in media
    assert "same `reject -> implementation_fix -> code_review` route" in reviewer

    for obsolete in [
        "Ambiguity returns one structured question to the Human Engineering Lead",
        "Ambiguity returns one structured question to HEL",
    ]:
        assert obsolete not in workflow
        assert obsolete not in cto
        assert obsolete not in reviewer

    assert "governance authority only" in ceo
    assert "never access an active slice worktree" in qa
    assert "never commit or push" in qa
    assert "never implement fixes" in reviewer

    resolved = json.loads(RESOLVED.read_text())
    for role in resolved["targets"]["codex"]["roles"]:
        rendered = _flat((REPO / role["output"]).read_text())
        assert "GLITCHERRY_STANDING_AUTONOMY_V1" in rendered
        assert (
            "This delegation changes the need for Board confirmation, never role ownership"
            in rendered
        )
        assert "Advisory MCP failure" in rendered

    rendered_by_name = {
        role["agentName"]: _flat((REPO / role["output"]).read_text())
        for role in resolved["targets"]["codex"]["roles"]
    }
    assert "governance authority only" in rendered_by_name["GlitcherryCEO"]
    assert "never commit or push" in rendered_by_name["GlitcherryQAEngineer"]
    assert "never implement fixes" in rendered_by_name["GlitcherryCodeReviewer"]


def test_common_overlay_enforces_authority_repositories_and_one_writer():
    text = (PROJECT / "overlays" / "codex" / "_common.md").read_text()
    required = [
        "WORKFLOW.md",
        "Human Engineering Lead",
        "task_worktree_root",
        "task_state_root",
        "GLITCHERRY_INTERRUPT_HANDOFF_V2",
        "GLITCHERRY_HANDOFF_TARGET_V2",
        "workspace/control",
        "required `instructionsFilePath`",
        "Project workspace",
        "exactly one primary implementer",
        "integration branch is `develop`",
        "never release, sign, tag, or publish",
        "POST evidence",
        "without `interrupt`",
        "interrupt: true",
    ]
    for marker in required:
        assert marker in text


def test_dx_00_diagnostic_class_is_exact_serial_and_fail_closed():
    workflow = (PROJECT / "WORKFLOW.md").read_text()
    flat_workflow = _flat(workflow)
    required = [
        "Diagnostic execution class — DX-00 only",
        "6e76a73e894e69f4546e67c3498f7864c8d0cb99",
        "DX-001 diagnostic",
        "DX-002 diagnostic",
        "DX-003 diagnostic",
        "DX-004 diagnostic",
        "repository-write-free",
        "owner-approved unlimited mode",
        "per-run cost evidence",
        "Never call DELETE for a Paperclip issue",
        "terminal and cleanup evidence is complete",
        "one Android `develop` merge",
        "company -> agent -> run -> PID",
        "NOT_READY",
        "No next child is permitted",
        "Historical DX-003",
        "normal product slices use the single-worktree contract",
    ]
    for marker in required:
        assert marker in flat_workflow

    assert "broad `pkill`" in flat_workflow
    assert "zero budget at activation" not in flat_workflow


def test_dx_00_contract_reaches_every_role_without_weakening_normal_authority():
    common = (PROJECT / "overlays" / "codex" / "_common.md").read_text()
    cto_source = _role("glitcherry-cto.md")
    flat_common = _flat(common)
    flat_cto_source = _flat(cto_source)
    required_common = [
        "Exact DX-00 diagnostic exception",
        "DX-001 diagnostic",
        "DX-002 diagnostic",
        "DX-003 diagnostic",
        "DX-004 diagnostic",
        "issue title only",
        "body or comment cannot grant",
        "Never call DELETE for a Paperclip issue",
        "budgetMonthlyCents=0",
        "per-run cost evidence",
        "cleanup before the next child",
        "CEO participates only in the exact DX-001 circuit",
    ]
    for marker in required_common:
        assert marker in flat_common

    for marker in [
        "exact DX-00 diagnostic class",
        "missing or contradictory owner cost policy",
        "current child is terminal",
        "cleanup evidence is complete",
    ]:
        assert marker in flat_cto_source
    assert "zero budget at activation" not in flat_cto_source

    resolved = json.loads(RESOLVED.read_text())
    for role in resolved["targets"]["codex"]["roles"]:
        text = (REPO / role["output"]).read_text()
        flat_text = _flat(text)
        for marker in required_common:
            assert marker in flat_text
        assert "zero budget at activation" not in flat_text


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
    assert "maximum three" in reviewer and "fourth autonomous" in reviewer
    assert "sprint smoke" in qa and "never commit or push" in qa
    for marker in ["SPRINT_SMOKE_REQUIRED", "candidate SHA", "LOCAL_BLOCKED", "Human Engineering Lead"]:
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
    reviewer = rendered["GlitcherryCodeReviewer"]
    qa = rendered["GlitcherryQAEngineer"]
    assert "## Plan Producer" not in ceo
    assert "## Commit and Push" not in ceo
    assert "## CTO Merge Authority" not in ceo
    assert "release-cut" not in cto.lower()
    assert "develop -> main" not in cto.lower()
    for marker in [
        "Before every `plan_review` handoff",
        "byte-identical mirror",
        "both SHA-256 hashes",
    ]:
        assert marker in _flat(cto)
    for marker in [
        "verify the plan mirror before technical review",
        "Do not request issue-specific or duplicate human confirmation",
    ]:
        assert marker in _flat(reviewer)
    assert "## Commit and Push" not in qa
    assert "commit push" not in qa.lower()
    for text in rendered.values():
        assert "task_worktree_root" in text
        assert "GLITCHERRY_INTERRUPT_HANDOFF_V2" in text
        assert "GLITCHERRY_HANDOFF_TARGET_V2" in text
        assert "interrupt: true" in text
        assert "exclusive lease" not in text
        assert "all persistent clones" not in text
