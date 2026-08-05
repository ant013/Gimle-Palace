"""Phase C2: smoke-test.sh structural validation."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "smoke-test.sh"
PROBES = REPO / "paperclips" / "scripts" / "lib" / "_smoke_probes.sh"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_supports_quick_flag():
    assert "--quick" in SCRIPT.read_text()


def test_supports_canary_stage_flag():
    assert "--canary-stage" in SCRIPT.read_text()


def test_has_7_stages():
    text = SCRIPT.read_text()
    for stage in ["[1/7]", "[2/7]", "[3/7]", "[4/7]", "[5/7]", "[6/7]", "[7/7]"]:
        assert stage in text, f"missing stage marker: {stage}"


def test_stage_1_validates_board_operator_credential():
    text = SCRIPT.read_text()
    stage = text[text.index("stage_1_api_reachable()") : text.index("stage_2_company_and_agents()")]

    assert 'paperclip_get "/api/cli-auth/me"' in stage
    assert 'paperclip_get "/api/agents/me"' not in stage
    assert ".user.email" in stage
    assert ".source" in stage
    assert '[ "$auth_source" = "board_key" ]' in stage


def test_uses_smoke_probes_library():
    text = SCRIPT.read_text()
    assert "_smoke_probes.sh" in text
    assert "probe_agent_for_profile" in text
    assert "probe_e2e_handoff" in text


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "smoke" in out.stdout.lower() or "stage" in out.stdout.lower()


def test_supports_exact_disposable_issue_cleanup():
    text = SCRIPT.read_text()
    assert "--cleanup-issues" in text
    assert "SMOKE_ISSUE_LOG" in text
    assert "cleanup_smoke_issues" in text


def test_handoff_source_uses_inner_orchestrator_workflow_role():
    text = SCRIPT.read_text()
    assert 'workflow_role == "inner_orchestrator"' in text


def test_runtime_probes_pass_workflow_role_separately_from_profile():
    text = SCRIPT.read_text()
    assert "workflow_role" in text
    assert 'probe_agent_for_profile "$company_id" "$uuid" "$name" "$profile" "$workflow_role"' in text


def test_runtime_mcp_markers_are_derived_from_the_project_manifest():
    text = SCRIPT.read_text()
    assert ".mcp.runtime_smoke_required // .mcp.base_required" in text
    assert "sed 's/-/_/g'" in text
    assert "SMOKE_EXPECTED_MCP_LIST" in text


def test_git_capabilities_follow_profile_not_workflow_role():
    text = PROBES.read_text()
    assert 'local git_policy="$profile"' in text
    assert "Git capability is defined by the composed profile fragments" in text
    assert "EXPECTED_GIT_outer_walker" not in text
    assert "EXPECTED_GIT_inner_orchestrator" not in text


def test_git_forbidden_operations_are_checked_only_in_can_section():
    command = (
        f'source "{PROBES}"; '
        'printf "Can:\\n- fetch\\nCannot:\\n- commit push merge\\n" | _git_can_section'
    )
    out = subprocess.run(["bash", "-c", command], capture_output=True, text=True, check=True).stdout
    assert "fetch" in out
    assert "commit" not in out
    assert "push" not in out
    assert "merge" not in out
