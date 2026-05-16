"""Phase B contract: builder derives output_path when manifest agent omits it."""
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_agent_without_output_path_produces_default_path():
    """For agent {agent_name: X, role_source: roles/...md, target: codex} without
    output_path, builder writes paperclips/dist/<project>/<target>/X.md."""
    project_root = REPO / "paperclips" / "projects" / "synth-test-b1"
    out_dir = REPO / "paperclips" / "dist" / "synth-test-b1"
    if project_root.exists():
        shutil.rmtree(project_root)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    project_root.mkdir(parents=True)
    (project_root / "compat").mkdir()
    (project_root / "compat" / "claude-stub.sh").write_text("#!/usr/bin/env bash\n# stub\n")
    (project_root / "compat" / "codex-ids.env").write_text("# stub\n")
    (project_root / "compat" / "workspace.env").write_text("# stub\n")

    (project_root / "paperclip-agent-assembly.yaml").write_text("""\
schemaVersion: 2
project:
  key: synth-test-b1
  display_name: Synth B1
  system_name: SynthB1
  issue_prefix: SYN
  company_id: synth-b1-stub
  integration_branch: main
  specs_dir: docs/specs
  plans_dir: docs/plans
domain:
  wallet_target_short: synth
  wallet_target_name: Synth Wallet
  wallet_target_slug: synth
evidence:
  merge_without_smoke_issue: SYN-stub
  graphiti_mock_issue: SYN-stub
  release_reset_issue: SYN-stub
  asyncmock_driver_issue: SYN-stub
  worktree_discipline_issue_pair: SYN-stub
  qa_worktree_discipline_issue: SYN-stub
  mcp_wire_contract_issue: SYN-stub
  qa_deploy_checklist_issue: SYN-stub
  review_scope_drift_issue: SYN-stub
  qa_to_cto_stall_issue: SYN-stub
  handoff_flake_issue: SYN-stub
  pre_slim_baseline_issue: SYN-stub
  cr_to_pe_stall_issue: SYN-stub
  handoff_misclassified_issue: SYN-stub
  post_merge_stall_issue: SYN-stub
paths:
  project_root: .
  primary_repo_root: .
  primary_mcp_service_dir: services/synth
  production_checkout: /tmp/synth-stub
  codex_team_root: /tmp/synth-stub/runs
  operator_memory_dir: /tmp/synth-stub/memory
  overlay_root: paperclips/projects/synth-test-b1/overlays
  project_rules_file: AGENTS.md
mcp:
  service_name: synth-mcp
  package_name: synth_mcp
  tool_namespace: synth
  base_required:
    - codebase-memory
    - context7
    - serena
    - github
    - sequential-thinking
  codebase_memory_projects:
    primary: synth-cm
  additions:
    project: []
    by_role: {}
skills:
  additions:
    project: []
    by_role: {}
subagents:
  additions:
    project: []
    by_role: {}
targets:
  codex:
    instruction_entry_file: AGENTS.md
    adapter_type: codex_local
    deploy_mode: dry-run
    instructions_bundle_mode: managed
compatibility:
  legacy_output_paths: false
  claude_deploy_mapping: paperclips/projects/synth-test-b1/compat/claude-stub.sh
  codex_agent_ids_env: paperclips/projects/synth-test-b1/compat/codex-ids.env
  workspace_update_script: paperclips/projects/synth-test-b1/compat/workspace.env
agents:
  - agent_name: TestAgent
    role_source: paperclips/roles-codex/cx-python-engineer.md
    profile: implementer
    target: codex
""")
    try:
        result = subprocess.run(
            ["./paperclips/build.sh", "--project", "synth-test-b1", "--target", "codex"],
            cwd=REPO, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"build failed:\n{result.stdout}\n{result.stderr}"
        out = REPO / "paperclips" / "dist" / "synth-test-b1" / "codex" / "TestAgent.md"
        assert out.is_file(), f"expected output at {out}"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)


def test_agent_with_explicit_output_path_still_works():
    """Back-compat: agents with explicit output_path (trading/uaudit pre-migration) keep working."""
    result = subprocess.run(
        ["./paperclips/build.sh", "--project", "trading", "--target", "codex"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"trading build broke:\n{result.stderr}"
