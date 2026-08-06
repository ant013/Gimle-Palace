from __future__ import annotations

import importlib.util
import copy
import re
import sys
import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "paperclips" / "scripts"
CONFIG = REPO / "paperclips/projects/uaudit/daily-version-branch-routines.yaml"
MANIFEST = REPO / "paperclips/projects/uaudit/paperclip-agent-assembly.yaml"
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)

sys.path.insert(0, str(SCRIPTS))

from reconcile_uaudit_routines import (  # noqa: E402
    apply_plan,
    build_plan,
    load_config,
    load_paths,
    normalize_current_routines,
    render_description,
    required_agent_names,
    resolve_agent_ids,
    validate_config_agents,
)


def load_manifest():
    return yaml.safe_load(MANIFEST.read_text())


def test_daily_routine_config_uses_names_not_uuids_and_resolves_agents():
    raw = CONFIG.read_text()
    assert not UUID_RE.search(raw)
    assert "required_subagents" not in raw
    config = load_config(CONFIG)
    assert config["limits"] == {
        "max_commits": 30,
        "max_files": 300,
        "max_diff_lines": 3000,
    }
    assert {r["platform"] for r in config["routines"]} == {"android", "ios"}
    assert {r["branch"] for r in config["routines"]} == {"version/0.50"}
    assert {r["routine_key"] for r in config["routines"]} == {
        "uaudit-daily-android",
        "uaudit-daily-ios",
    }
    agents = resolve_agent_ids(
        "uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml"
    )
    validate_config_agents(config, agents)
    assert {
        "AUCEO",
        "UWACTO",
        "UWICTO",
        "UWAKotlinAuditor",
        "UWISwiftAuditor",
        "UWASecurityAuditor",
        "UWISecurityAuditor",
        "UWACryptoAuditor",
        "UWICryptoAuditor",
        "UWAInfraEngineer",
        "UWIInfraEngineer",
        "UWAQAEngineer",
        "UWIQAEngineer",
    } <= required_agent_names(config)


def test_uaudit_platform_ctos_use_custom_project_dispatcher_roles():
    data = load_manifest()
    by_name = {agent["agent_name"]: agent for agent in data["agents"]}
    assert by_name["UWACTO"]["profile"] == "custom"
    assert (
        by_name["UWACTO"]["role_source"]
        == "paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md"
    )
    assert by_name["UWICTO"]["profile"] == "custom"
    assert (
        by_name["UWICTO"]["role_source"]
        == "paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md"
    )
    assert by_name["AUCEO"]["profile"] == "cto"


def test_generated_dispatcher_bundles_start_staged_daily_chain():
    forbidden = [
        "CTO profile",
        "Merge gate",
        "merge readiness",
        "APPROVE",
        "git merge",
        "Direct push",
        "mode=audit_delta",
        "required subagent roster",
    ]
    expected = {
        "UWACTO": (
            "00000000-0000-0000-0000-000000000014",
            (
                "UWAKotlinAuditor",
                "UWASecurityAuditor",
                "UWACryptoAuditor",
                "UWAInfraEngineer",
            ),
        ),
        "UWICTO": (
            "00000000-0000-0000-0000-000000000013",
            (
                "UWISwiftAuditor",
                "UWISecurityAuditor",
                "UWICryptoAuditor",
                "UWIInfraEngineer",
            ),
        ),
    }
    for name, (code_auditor_id, chain_names) in expected.items():
        path = REPO / f"paperclips/dist/uaudit/codex/{name}.md"
        assert path.is_file(), f"missing generated bundle {path}"
        text = path.read_text()
        assert text.count("\n") <= 100
        assert len(text.encode()) <= 6000
        for phrase in forbidden:
            assert phrase not in text, f"{name} contains forbidden phrase {phrase!r}"
        assert "daily-version-branch-routines.yaml" in text
        assert code_auditor_id in text
        assert "Chain:" in text
        assert "mode=daily_code_audit" in text
        assert "mode=daily_aggregate" in text
        assert "audit-final.md" in text
        assert "do not use `uaudit-*` subagents for daily real-delta audits" in text
        assert "uaudit_delivery_contract.py" in text
        assert "verify-install --manifest" in text
        assert "bind-context --run-dir" in text
        assert "aggregate --run-dir" in text
        assert "delivery-handoff.json" in text
        assert "verify-payload --run-dir" in text
        assert "code.findings.json" in text
        assert "complete+0" in text
        assert "Russian" in text
        for chain_name in chain_names:
            assert chain_name in text
        assert "max_files=300" in text


def test_forced_full_range_is_explicit_and_does_not_relax_daily_rules():
    for platform, dispatcher, infra in (
        ("android", "UWACTO", "UWAInfraEngineer"),
        ("ios", "UWICTO", "UWIInfraEngineer"),
    ):
        source = (
            REPO
            / f"paperclips/projects/uaudit/roles-codex/{'uwa' if platform == 'android' else 'uwi'}-platform-dispatcher.md"
        ).read_text()
        infra_source = (
            REPO / f"paperclips/projects/uaudit/overlays/codex/{infra}.md"
        ).read_text()
        assert "UAudit forced full-range audit" in source
        assert "daily_limits_bypassed: true" in source
        assert "cursor_mutation: forbidden" in source
        assert "max_files=300" in source
        assert "never call `reconcile-daily`" in infra_source


def test_generated_dispatchers_pin_canonical_daily_cursors():
    expected = {
        "UWACTO": (
            "/state/android-version-audit.json",
            "/artifacts/",
        ),
        "UWICTO": (
            "/state/ios-version-audit.json",
            "/artifacts/",
        ),
    }
    for name, (canonical, legacy) in expected.items():
        text = (REPO / f"paperclips/dist/uaudit/codex/{name}.md").read_text()
        assert canonical in text
        assert "FROM is only" in text
        assert "preserve this cursor" in text
        assert legacy in text
        assert "Never read a cursor below" in text


def test_daily_dispatchers_fetch_declared_authoritative_refs_before_intake():
    expected = {
        "android": "https://github.com/horizontalsystems/unstoppable-wallet-android",
        "ios": "https://github.com/horizontalsystems/unstoppable-wallet-ios",
    }
    for platform, repo_url in expected.items():
        role = "uwa" if platform == "android" else "uwi"
        dispatcher = "UWACTO" if platform == "android" else "UWICTO"
        source = (
            REPO
            / f"paperclips/projects/uaudit/roles-codex/{role}-platform-dispatcher.md"
        ).read_text()
        rendered = (REPO / f"paperclips/dist/uaudit/codex/{dispatcher}.md").read_text()
        for text in (source, rendered):
            assert repo_url in text
            assert "fetch --no-tags" in text
            assert "refs/remotes/uaudit-upstream/version/0.50" in text
            assert "Never resolve TO from origin/version/0.50" in text


def test_uaudit_bootstrap_validates_partial_human_approvers_before_deploy():
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    assert "validate_uaudit_partial_approvers" in text
    assert "state/partial-approvers.json" in text
    assert "approver_actor_ids" in text
    assert "partial approvers must be a sorted, non-empty allowlist" in text


def test_infra_bundles_use_staged_daily_delivery_not_subagent_fanout():
    forbidden = [
        "If the cursor file is missing, create it",
        "noop.done",
        "If `FROM == TO`",
        "No new commits for",
        "Required subagents for `mode=audit_delta`",
        "Subagent Fanout",
        "spawnMode=profile-prompt",
        "profileSha256",
        "unverifiable fallback blocks the run",
    ]
    for name, cto in (("UWAInfraEngineer", "UWACTO"), ("UWIInfraEngineer", "UWICTO")):
        path = REPO / f"paperclips/dist/uaudit/codex/{name}.md"
        text = path.read_text()
        for phrase in forbidden:
            assert phrase not in text, f"{name} still contains intake phrase {phrase!r}"
        assert "mode=initialize_cursor" in text
        assert "mode=daily_infra_audit" in text
        assert "mode=daily_delivery" in text
        assert "audit-final.md" in text
        assert "delivery_contract=uaudit-delivery/v1" in text
        assert "verify-install --manifest" in text
        assert "verify-payload --run-dir" in text
        assert "record-delivery --run-dir" in text
        assert "reconcile-daily --run-dir" in text
        assert 'routeSource:"file_route"' in text
        assert 'routeName:"UAudit"' in text
        assert "telegram-summary.txt" in text
        assert "status/telegram.done" in text
        assert "status/cursor.done" in text
        assert "status/workflow.done" in text
        assert '{"last_successfully_audited_sha":"<40hex>"}' in text
        assert "Missing lock is allowed only" in text
        assert "partial audit approved" in text
        assert "partial-approvers.json" in text
        assert "legacy-delivery-allowlist.json" in text
        assert "at most 100 entries" in text
        assert "issue_identifier,run_dir,audit_kind,report_file,report_sha256" in text
        assert "smoke/telegram-report.md" in text
        assert "status/legacy-delivery.done.json" in text
        assert "Never use `status/delivery.done`" in text
        assert 'python3 "' in text
        assert "chatId" not in text
        assert "filePath" not in text


def test_audit_stage_bundles_use_bound_structured_v1_sidecars():
    expected = {
        "UWISwiftAuditor": (
            "code",
            "UWISwiftAuditor",
            "code.findings.json",
            "code.done.json",
        ),
        "UWAKotlinAuditor": (
            "code",
            "UWAKotlinAuditor",
            "code.findings.json",
            "code.done.json",
        ),
        "UWISecurityAuditor": (
            "security",
            "UWISecurityAuditor",
            "security.findings.json",
            "security.done.json",
        ),
        "UWASecurityAuditor": (
            "security",
            "UWASecurityAuditor",
            "security.findings.json",
            "security.done.json",
        ),
        "UWICryptoAuditor": (
            "crypto",
            "UWICryptoAuditor",
            "crypto.findings.json",
            "crypto.done.json",
        ),
        "UWACryptoAuditor": (
            "crypto",
            "UWACryptoAuditor",
            "crypto.findings.json",
            "crypto.done.json",
        ),
        "UWIInfraEngineer": (
            "infra",
            "UWIInfraEngineer",
            "infra.findings.json",
            "infra.done.json",
        ),
        "UWAInfraEngineer": (
            "infra",
            "UWAInfraEngineer",
            "infra.findings.json",
            "infra.done.json",
        ),
        "UWIResearchAgent": (
            "research_context",
            "UWIResearchAgent",
            "research-context.findings.json",
            "research_context.done.json",
        ),
        "UWAResearchAgent": (
            "research_context",
            "UWAResearchAgent",
            "research-context.findings.json",
            "research_context.done.json",
        ),
        "UWIQAEngineer": (
            "qa_verify",
            "UWIQAEngineer",
            "qa-verify.findings.json",
            "qa_verify.done.json",
        ),
        "UWAQAEngineer": (
            "qa_verify",
            "UWAQAEngineer",
            "qa-verify.findings.json",
            "qa_verify.done.json",
        ),
    }
    for name, (stage, source, sidecar, marker) in expected.items():
        text = (REPO / f"paperclips/dist/uaudit/codex/{name}.md").read_text()
        assert "run-context.json" in text
        assert sidecar in text
        assert marker in text
        assert f'stage="{stage}"' in text
        assert f'source_agent="{source}"' in text
        assert "audit_status" in text
        assert "{text,material}" in text
        assert (
            "severity,file,line,area,title,evidence,impact,recommendation,needs_runtime_verification"
            in text
        )
        assert "limitation text" in text or "limitation `text`" in text
        assert "validate-stage --run-dir" in text
        assert "Russian" in text
        if "InfraEngineer" not in name:
            assert "send_to_telegram" not in text


def test_pr_coordinators_use_helper_owned_russian_delivery_contract():
    expected = {
        "UWISwiftAuditor": "uaudit-swift-audit-specialist",
        "UWAKotlinAuditor": "uaudit-kotlin-audit-specialist",
    }
    for name, specialist in expected.items():
        text = (REPO / f"paperclips/dist/uaudit/codex/{name}.md").read_text()
        for agent_type in (
            specialist,
            "uaudit-bug-hunter",
            "uaudit-security-auditor",
            "uaudit-blockchain-auditor",
        ):
            assert agent_type in text
        assert "bind-context --run-dir" in text
        assert "verify-install --manifest" in text
        assert "validate-stage --run-dir" in text
        assert "aggregate --run-dir" in text
        assert "delivery-summary.json" in text
        assert "delivery-handoff.json" in text
        assert 'delivery_contract:"uaudit-delivery/v1"' in text
        assert "complete+0" in text
        assert "partial" in text
        assert "Russian" in text
        assert "legacy confidence/scope/no-finding fields" in text
        assert "spawn only missing slots" in text
        assert "never overwrite a validated slot" in text


def test_pr_subagents_emit_only_the_strict_v1_envelope():
    agents_dir = REPO / "paperclips/projects/uaudit/codex-agents"
    for path in sorted(agents_dir.glob("uaudit-*.toml")):
        instructions = tomllib.loads(path.read_text())["developer_instructions"]
        for field in (
            "schema_version",
            "run_binding",
            "stage",
            "source_agent",
            "audit_status",
            "findings",
            "limitations",
            "block_reason",
            "needs_runtime_verification",
        ):
            assert field in instructions, f"{path.name} omits v1 field {field}"
        assert (
            "severity,file,line,area,title,evidence,impact,recommendation,needs_runtime_verification"
            in instructions
        )
        assert "limitation text" in instructions and "in Russian" in instructions
        assert "do not add" in instructions.lower()
        assert "raw diff content" in instructions or "raw-diff" in instructions


def _paths():
    return load_paths(
        "uaudit",
        REPO / "paperclips/projects/uaudit/paths.local-example.yaml",
    )


def _legacy_live_routine(config, routine, assignee, *, suffix="1"):
    paths = _paths()
    description = "\n".join(
        (
            config["marker"],
            f"platform: {routine['platform']}",
            f"branch: {routine['branch']}",
            f"repo: {render_description(config, routine, paths).splitlines()[4][6:]}",
            f"cursor: {render_description(config, routine, paths).splitlines()[5][8:]}",
        )
    )
    return {
        "id": f"00000000-0000-0000-0000-0000000000{suffix}",
        "title": routine["title"],
        "description": description,
        "assigneeAgentId": assignee,
        "latestRevisionId": f"revision-{suffix}",
    }


def test_reconcile_plan_matches_legacy_records_and_renders_stable_keys():
    config = load_config(CONFIG)
    agents = resolve_agent_ids(
        "uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml"
    )
    android, ios = config["routines"]
    current = normalize_current_routines(
        {
            "routines": [
                _legacy_live_routine(config, android, "old-android", suffix="11"),
                _legacy_live_routine(config, ios, agents["UWICTO"], suffix="12"),
            ]
        }
    )
    plan = build_plan(config, agents, current, _paths())
    by_id = {item["routine_id"]: item for item in plan}
    assert by_id["daily-android-version-0.50"]["dispatcher"] == "UWACTO"
    assert (
        by_id["daily-android-version-0.50"]["desired_assigneeAgentId"]
        == agents["UWACTO"]
    )
    assert by_id["daily-android-version-0.50"]["live_uuid"].endswith("11")
    assert by_id["daily-android-version-0.50"]["needs_update"] is True
    assert by_id["daily-ios-version-0.50"]["needs_update"] is True
    assert (
        "routine_key: uaudit-daily-android"
        in by_id["daily-android-version-0.50"]["desired_description"]
    )
    assert (
        by_id["daily-android-version-0.50"]["patch"]["baseRevisionId"] == "revision-11"
    )


def test_reconcile_stable_key_survives_next_version_without_new_live_record():
    config = load_config(CONFIG)
    agents = resolve_agent_ids(
        "uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml"
    )
    paths = _paths()
    current = []
    for index, routine in enumerate(config["routines"], start=21):
        current.append(
            {
                "id": f"00000000-0000-0000-0000-0000000000{index}",
                "title": routine["title"],
                "description": render_description(config, routine, paths),
                "assigneeAgentId": agents[routine["dispatcher"]],
                "latestRevisionId": f"revision-{index}",
            }
        )
    next_config = copy.deepcopy(config)
    for routine in next_config["routines"]:
        routine["id"] = routine["id"].replace("0.50", "0.51")
        routine["branch"] = "version/0.51"
    plan = build_plan(next_config, agents, current, paths)
    assert {item["live_uuid"] for item in plan} == {
        "00000000-0000-0000-0000-000000000021",
        "00000000-0000-0000-0000-000000000022",
    }
    assert all(item["needs_update"] for item in plan)
    assert all("branch: version/0.51" in item["desired_description"] for item in plan)


def test_reconcile_rejects_ambiguous_legacy_fallback():
    config = load_config(CONFIG)
    agents = resolve_agent_ids(
        "uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml"
    )
    android = config["routines"][0]
    duplicate_a = _legacy_live_routine(config, android, "old-a", suffix="31")
    duplicate_b = _legacy_live_routine(config, android, "old-b", suffix="32")
    try:
        build_plan(
            {**config, "routines": [android]},
            agents,
            [duplicate_a, duplicate_b],
            _paths(),
        )
    except ValueError as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("ambiguous legacy fallback must fail")


def test_reconcile_rejects_conflicting_stable_identity():
    config = load_config(CONFIG)
    agents = resolve_agent_ids(
        "uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml"
    )
    android = config["routines"][0]
    live = _legacy_live_routine(config, android, "old-a", suffix="33")
    live["description"] = live["description"].replace(
        "platform: android",
        "routine_key: uaudit-daily-android\nplatform: ios",
    )
    try:
        build_plan({**config, "routines": [android]}, agents, [live], _paths())
    except ValueError as exc:
        assert "conflicting platform" in str(exc)
    else:
        raise AssertionError("conflicting stable identity must fail")


def test_config_rejects_duplicate_stable_keys(tmp_path):
    data = yaml.safe_load(CONFIG.read_text())
    data["routines"][1]["routine_key"] = data["routines"][0]["routine_key"]
    config_path = tmp_path / "duplicate-routine-key.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False))
    try:
        load_config(config_path)
    except ValueError as exc:
        assert "routine routine_key values must be unique" in str(exc)
    else:
        raise AssertionError("duplicate routine keys must fail")


def test_explicit_missing_paths_source_does_not_fall_back(tmp_path):
    missing = tmp_path / "missing-paths.yaml"
    try:
        load_paths("uaudit", missing)
    except ValueError as exc:
        assert "missing explicit" in str(exc)
    else:
        raise AssertionError("an explicit missing paths source must fail")


def test_reconcile_partial_apply_reports_409_and_rerun_converges():
    config = load_config(CONFIG)
    agents = resolve_agent_ids(
        "uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml"
    )
    paths = _paths()
    android, ios = config["routines"]
    states = {
        item["id"]: item
        for item in (
            _legacy_live_routine(config, android, "old-android", suffix="41"),
            _legacy_live_routine(config, ios, "old-ios", suffix="42"),
        )
    }
    fail_ios = {"value": True}

    def request(method, url, token, body):
        live_uuid = url.rsplit("/", 1)[-1]
        if method == "GET":
            return copy.deepcopy(states[live_uuid])
        assert method == "PATCH"
        if live_uuid.endswith("42") and fail_ios["value"]:
            raise RuntimeError("PATCH failed HTTP 409")
        assert body["baseRevisionId"] == states[live_uuid]["latestRevisionId"]
        states[live_uuid].update(
            {key: value for key, value in body.items() if key != "baseRevisionId"}
        )
        states[live_uuid]["latestRevisionId"] += "-next"
        return copy.deepcopy(states[live_uuid])

    first_plan = build_plan(config, agents, list(states.values()), paths)
    first_result, first_ok = apply_plan(
        "http://paperclip.test",
        "redacted",
        config,
        agents,
        paths,
        first_plan,
        request=request,
    )
    assert first_ok is False
    assert [item["routine_id"] for item in first_result["updated"]] == [
        "daily-android-version-0.50"
    ]
    assert [item["routine_id"] for item in first_result["failed"]] == [
        "daily-ios-version-0.50"
    ]

    fail_ios["value"] = False
    second_plan = build_plan(config, agents, list(states.values()), paths)
    second_result, second_ok = apply_plan(
        "http://paperclip.test",
        "redacted",
        config,
        agents,
        paths,
        second_plan,
        request=request,
    )
    assert second_ok is True
    assert [item["routine_id"] for item in second_result["updated"]] == [
        "daily-ios-version-0.50"
    ]
    assert [item["routine_id"] for item in second_result["unchanged"]] == [
        "daily-android-version-0.50"
    ]
    final_plan = build_plan(config, agents, list(states.values()), paths)
    assert all(not item["needs_update"] for item in final_plan)


def test_validate_uaudit_docs_script_passes():
    spec = importlib.util.spec_from_file_location(
        "validate_uaudit_docs", SCRIPTS / "validate_uaudit_docs.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.main() == 0
