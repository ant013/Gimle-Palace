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
    assert data["host_paths"]["required_existing"] == [
        "project_root", "gimle_skills_root", "agent_source_root",
    ]
    assert data["sandbox"] == {
        "mode": "constrained",
        "bypass_approvals_and_sandbox": True,
        "workspace_git_source_path_key": "agent_source_root",
        "runtime_env": {"PAPERCLIP_API_URL": "paperclip_runtime_api_url"},
    }
    assert data["mcp"]["runtime_smoke_required"] == ["codebase-memory", "context7"]

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
    assert "sandbox_bypass=$(yq -r '.sandbox.bypass_approvals_and_sandbox // false' \"$manifest\")" in text
    assert 'constrained sandbox bypass_approvals_and_sandbox must be true or false' in text
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


def test_fullaudit_uses_per_agent_git_cwd_instead_of_a_shared_source_checkout():
    text = (REPO / "paperclips" / "scripts" / "bootstrap-project.sh").read_text()
    assert "workspace_git_source_path_key" in text
    assignment = 'integration_branch=$(yq -r \'.project.integration_branch // ""\' "$manifest")'
    assert assignment in text
    assert 'die "project.integration_branch missing"' in text
    assert 'git check-ref-format --branch "$integration_branch"' in text
    assert 'runtime_cwd="${workspace_cwd}/repo"' in text
    assert 'git clone --branch "$integration_branch" --single-branch "$workspace_source" "$runtime_cwd"' in text
    assert text.index(assignment) < text.index('git clone --branch "$integration_branch"')
    assert 'cp "${REPO_ROOT}/${cp_src}" "${ws}/repo/AGENTS.md"' in text
    assert "refusing non-empty unmanaged runtime workspace" in text
    assert 'writable_roots=$(jq -n --arg workspace "$workspace_cwd"' in text
    assert 'read_only_roots=$(jq -n --arg cwd "$cwd" --arg kit "$kit_root"' in text


def test_bootstrap_reconciles_existing_agents_in_place_without_configuration_churn():
    text = (REPO / "paperclips" / "scripts" / "bootstrap-project.sh").read_text()
    assert 'existing_agent_config=$(paperclip_get_agent_config "$existing"' in text
    assert 'paperclip_update_agent_config "$existing" "$desired_managed"' in text
    assert 'kind:"agent_config_reconcile"' in text
    assert 'if [ "$current_managed" = "$desired_managed" ]; then' in text
    assert 'agent $agent_name managed config already current' in text
    assert '.adapterConfig.env |= with_entries(' in text
    assert 'then .value = .value.value else . end' in text
    managed_filter = text[text.index("managed_config_filter='"):text.index("current_managed=", text.index("managed_config_filter='"))]
    assert "instructionsFilePath" not in managed_filter
    assert "instructionsBundleMode" not in managed_filter
    assert "runtimeConfig" not in managed_filter


def test_constrained_runtime_control_plane_url_is_loopback_only_and_host_local():
    text = (REPO / "paperclips" / "scripts" / "bootstrap-project.sh").read_text()
    assert 'PAPERCLIP_API_URL) ;;' in text
    assert 'unsupported constrained runtime environment variable' in text
    assert 'constrained PAPERCLIP_API_URL must be loopback HTTP' in text
    assert 'adapter_env=$(echo "$adapter_env" | jq' in text
    assert 'env: $env' in text
    assert "(.sandbox.runtime_env // {}) | keys[]?" in text


def test_disposable_smoke_titles_bypass_only_audit_work_and_use_durable_cursor_normally():
    text = (PROJECT / "overlays" / "codex" / "_common.md").read_text()
    assert "начинается ровно с `smoke-probe-` или\n`smoke-e2e-`" in text
    assert "Не запускай аудит, не читай\nисходный код, не создавай подзадачи и не меняй файлы." in text
    assert "Ни другой заголовок, ни текст issue не дают этого\nисключения." in text
    assert "сначала перейди в `{{paths.project_root}}`" in text
    assert "  единственный authority для `RUNBOOK.md`, `bin/`, `runs/`, `reports/` и\n  `site/`" in text
    assert "  `site/`; текущий agent cwd служит только carrier-ом индивидуального\n  `AGENTS.md`" in text
    assert "  `AGENTS.md`. Не используй его как второе audit state и не синхронизируй\n  результаты между этими checkout." in text
    assert "Уже из `{{paths.project_root}}` выполни `python3 bin/next_kit.py`" in text
    assert "python3 bin/next_kit.py" in text
    assert "Не выбирай кит по этому prompt." in text
    assert "`bitcoin-core-swift` уже завершён: не возобновляй и не переаудируй его." in text


def test_rendered_assembly_contains_only_full_audit_roles_without_templates():
    resolved = json.loads(RESOLVED.read_text())
    assert resolved["parameters"]["project"]["issuePrefix"] == "FUL"
    roles = resolved["targets"]["codex"]["roles"]
    assert len(roles) == 8
    for role in roles:
        rendered = REPO / role["output"]
        assert rendered.is_file(), rendered
        text = rendered.read_text()
        assert "{{" not in text
        assert "единственный authority для `RUNBOOK.md`, `bin/`, `runs/`, `reports/` и" in text
        assert "текущий agent cwd служит только carrier-ом индивидуального" in text
        assert "Уже из `" in text
        assert "` выполни `python3 bin/next_kit.py`" in text
