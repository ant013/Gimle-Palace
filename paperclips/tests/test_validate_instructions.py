from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import validate_instructions  # noqa: E402
import compare_deployed_agents  # noqa: E402
import validate_codex_target_runtime  # noqa: E402


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(Path(__file__).resolve().parents[1], repo / "paperclips")
    for noisy in [
        repo / "paperclips" / "tests",
        repo / "paperclips" / "scripts" / "__pycache__",
    ]:
        if noisy.exists():
            shutil.rmtree(noisy)
    return repo


def test_current_repo_metadata_valid() -> None:
    errors = validate_instructions.validate(Path(__file__).resolve().parents[2])
    assert errors == []


def test_unknown_profile_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    role_path = repo / "paperclips" / "roles" / "python-engineer.md"
    role_path.write_text(
        role_path.read_text().replace(
            "profiles: [core, task-start, implementation, handoff]",
            "profiles: [core, missing-profile]",
            1,
        )
    )

    errors = validate_instructions.validate(repo)

    assert any("unknown profile missing-profile" in error for error in errors)


def test_generated_front_matter_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    dist_path = repo / "paperclips" / "dist" / "python-engineer.md"
    dist_path.write_text("---\nrole_id: bad\n---\n" + dist_path.read_text())
    baseline_path = repo / "paperclips" / "bundle-size-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    for bundle in baseline["bundles"]:
        if bundle["path"] == "paperclips/dist/python-engineer.md":
            text = dist_path.read_text()
            bundle["bytes"] = len(text.encode("utf-8"))
            bundle["lines"] = text.count("\n")
            bundle["tokenEstimate"] = (bundle["bytes"] + 3) // 4
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")

    errors = validate_instructions.validate(repo)

    assert any("generated bundle contains front matter" in error for error in errors)


def test_baseline_allows_smaller_bundle(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_path = repo / "paperclips" / "bundle-size-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    baseline["bundles"][0]["bytes"] += 1000
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")

    errors = validate_instructions.validate(repo)

    assert errors == []


def test_baseline_allows_growth_under_policy_threshold(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_path = repo / "paperclips" / "bundle-size-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    baseline["policy"]["maxGrowthPercent"] = 10
    actual_bytes = (repo / baseline["bundles"][0]["path"]).stat().st_size
    baseline["bundles"][0]["bytes"] = int(actual_bytes / 1.05)
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")

    errors = validate_instructions.validate(repo)

    assert errors == []


def test_baseline_growth_over_policy_threshold_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_path = repo / "paperclips" / "bundle-size-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    baseline["policy"]["maxGrowthPercent"] = 10
    actual_bytes = (repo / baseline["bundles"][0]["path"]).stat().st_size
    baseline["bundles"][0]["bytes"] = int(actual_bytes / 1.20)
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")

    errors = validate_instructions.validate(repo)

    assert any("bundle grew more than 10%" in error for error in errors)


def test_baseline_growth_allowlist_passes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_path = repo / "paperclips" / "bundle-size-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    baseline["policy"]["maxGrowthPercent"] = 10
    role_id = baseline["bundles"][0]["roleId"]
    path = baseline["bundles"][0]["path"]
    baseline["bundles"][0]["bytes"] = int(baseline["bundles"][0]["bytes"] * 0.80)
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")
    allowlist_path = repo / "paperclips" / "bundle-size-allowlist.json"
    allowlist = json.loads(allowlist_path.read_text())
    allowlist["entries"].append(
        {
            "rule": "bundle-size-growth",
            "roleId": role_id,
            "path": path,
            "reason": "temporary reviewed migration exception",
            "owner": "paperclip",
            "reviewAfter": "2026-06-01",
        }
    )
    allowlist_path.write_text(json.dumps(allowlist, indent=2) + "\n")

    errors = validate_instructions.validate(repo)

    assert errors == []


def test_global_growth_allowlist_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_path = repo / "paperclips" / "bundle-size-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    baseline["policy"]["maxGrowthPercent"] = 10
    baseline["bundles"][0]["bytes"] = int(baseline["bundles"][0]["bytes"] * 0.80)
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")
    allowlist_path = repo / "paperclips" / "bundle-size-allowlist.json"
    allowlist = json.loads(allowlist_path.read_text())
    allowlist["entries"].append(
        {
            "rule": "bundle-size-growth",
            "reason": "malformed global exception",
        }
    )
    allowlist_path.write_text(json.dumps(allowlist, indent=2) + "\n")

    errors = validate_instructions.validate(repo)

    assert any("missing roleId" in error for error in errors)
    assert any("missing path" in error for error in errors)
    assert any("bundle grew more than 10%" in error for error in errors)


def test_rule_required_profile_missing_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    matrix_path = repo / "paperclips" / "instruction-coverage.matrix.yaml"
    matrix_path.write_text(
        matrix_path.read_text().replace(
            "profiles: [core, task-start, implementation, handoff]",
            "profiles: [core, task-start, handoff]",
            1,
        )
    )
    role_path = repo / "paperclips" / "roles" / "blockchain-engineer.md"
    role_path.write_text(
        role_path.read_text().replace(
            "profiles: [core, task-start, implementation, handoff]",
            "profiles: [core, task-start, handoff]",
            1,
        )
    )

    errors = validate_instructions.validate(repo)

    assert any(
        "rule implementation-verification requires profile implementation for role claude:blockchain-engineer"
        in error
        for error in errors
    )


def test_block_list_front_matter_profiles_supported(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    role_path = repo / "paperclips" / "roles" / "python-engineer.md"
    role_path.write_text(
        role_path.read_text().replace(
            "profiles: [core, task-start, implementation, handoff]",
            "profiles:\n  - core\n  - task-start\n  - implementation\n  - handoff",
            1,
        )
    )

    errors = validate_instructions.validate(repo)

    assert errors == []


def test_handoff_markers_present_in_handoff_bundles(tmp_path: Path) -> None:
    """All bundles that include the phase-handoff fragment must carry every stable marker."""
    repo = make_repo(tmp_path)
    bundle_paths = {
        "claude:cto": repo / "paperclips" / "dist" / "cto.md",
        "codex:cx-cto": repo / "paperclips" / "dist" / "codex" / "cx-cto.md",
    }

    errors = validate_instructions.validate_handoff_markers(bundle_paths, repo)

    assert errors == []


def test_handoff_marker_missing_fails(tmp_path: Path) -> None:
    """Stripping a stable marker triggers a clear error message."""
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "cto.md"
    bundle.write_text(bundle.read_text().replace("paperclip:handoff-contract:v2", "tampered"))

    errors = validate_instructions.validate_handoff_markers({"claude:cto": bundle}, repo)

    assert any("paperclip:handoff-contract:v2" in error for error in errors)


def test_handoff_markers_skip_non_handoff_bundles(tmp_path: Path) -> None:
    """Bundles without the phase-handoff section (writers, research) skip the marker check."""
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "technical-writer.md"

    errors = validate_instructions.validate_handoff_markers({"claude:technical-writer": bundle}, repo)

    assert errors == []


def test_codex_runtime_refs_allow_mapped_capabilities(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "codex" / "cx-example.md"
    write(
        bundle,
        "- **Skills:** `superpowers:test-driven-development`.\n"
        "- **Subagents:** `pr-review-toolkit:pr-test-analyzer`.\n",
    )

    errors = validate_codex_target_runtime.validate_codex_runtime_refs(
        repo / "paperclips" / "dist" / "codex",
        repo / "paperclips" / "fragments" / "shared" / "targets" / "codex" / "runtime-map.json",
    )

    assert errors == []


def test_project_manifest_missing_base_mcp_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    manifest = repo / "paperclips" / "projects" / "gimle" / "paperclip-agent-assembly.yaml"
    manifest.write_text(manifest.read_text().replace("    - github\n", ""))

    errors = validate_instructions.validate_project_capability_manifests(repo)

    assert any("project manifest missing base MCP github" in error for error in errors)


def test_compare_deployed_agent_ids_parse_codex_names(tmp_path: Path) -> None:
    env_file = tmp_path / "codex-agent-ids.env"
    env_file.write_text(
        "CX_CTO_AGENT_ID=da97dbd9-6627-48d0-b421-66af0750eacf\n"
        "CODEX_ARCHITECT_REVIEWER_AGENT_ID=fec71dea-7dba-4947-ad1f-668920a02cb6\n"
        "CX_RESEARCH_AGENT_AGENT_ID=a2f7d4d2-ee96-43c3-83d8-d3af02d6674c\n"
    )

    ids = compare_deployed_agents.load_codex_agent_ids(env_file)

    assert ids["cx-cto"] == "da97dbd9-6627-48d0-b421-66af0750eacf"
    assert ids["codex-architect-reviewer"] == "fec71dea-7dba-4947-ad1f-668920a02cb6"
    assert ids["cx-research-agent"] == "a2f7d4d2-ee96-43c3-83d8-d3af02d6674c"


def test_compare_deployed_path_shape() -> None:
    path = compare_deployed_agents.deployed_agents_path(
        Path("/paperclip"),
        "company-id",
        "agent-id",
    )

    assert path == Path("/paperclip/companies/company-id/agents/agent-id/instructions/AGENTS.md")


def test_codex_runtime_refs_fail_on_gap_capability(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "codex" / "cx-example.md"
    write(bundle, "- **Skills:** `claude-api`.\n")

    errors = validate_codex_target_runtime.validate_codex_runtime_refs(
        repo / "paperclips" / "dist" / "codex",
        repo / "paperclips" / "fragments" / "shared" / "targets" / "codex" / "runtime-map.json",
    )

    assert any("runtime capability gap" in error.message for error in errors)


def test_codex_runtime_refs_fail_on_unmapped_capability(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "codex" / "cx-example.md"
    write(bundle, "- **Skills:** `superpowers:unknown-skill`.\n")

    errors = validate_codex_target_runtime.validate_codex_runtime_refs(
        repo / "paperclips" / "dist" / "codex",
        repo / "paperclips" / "fragments" / "shared" / "targets" / "codex" / "runtime-map.json",
    )

    assert any("unmapped Codex runtime capability reference" in error.message for error in errors)


def test_codex_runtime_refs_fail_on_hard_forbidden_claude_runtime(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "codex" / "cx-example.md"
    write(bundle, "Read `CLAUDE.md` before doing the task.\n")

    errors = validate_codex_target_runtime.validate_codex_runtime_refs(
        repo / "paperclips" / "dist" / "codex",
        repo / "paperclips" / "fragments" / "shared" / "targets" / "codex" / "runtime-map.json",
    )

    assert any("hard-forbidden Claude runtime reference" in error.message for error in errors)


def test_load_team_uuids_skips_company_id(tmp_path: Path) -> None:
    """COMPANY_ID at the top of deploy-agents.sh must not leak into the Claude UUID set."""
    repo = make_repo(tmp_path)

    teams = validate_instructions.load_team_uuids(repo)

    assert "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64" not in teams["claude"]
    # Real Claude agent UUID (cto) should be present
    assert "7fb0fdbb-e17f-4487-a4da-16993a907bec" in teams["claude"]


CLAUDE_CTO_UUID = "7fb0fdbb-e17f-4487-a4da-16993a907bec"


def _cx_meta() -> "validate_instructions.RoleMeta":
    return validate_instructions.RoleMeta(
        target="codex",
        role_id="codex:cx-cto",
        family="cto",
        profiles=["core"],
    )


def test_cross_team_clean_passes(tmp_path: Path) -> None:
    """Current Codex CTO bundle has no Claude UUIDs in active sections."""
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "codex" / "cx-cto.md"
    bundle_paths = {"codex:cx-cto": bundle}
    role_meta = {"codex:cx-cto": _cx_meta()}

    errors = validate_instructions.validate_cross_team_targets(bundle_paths, role_meta, repo)

    assert errors == []


def test_cross_team_actionable_foreign_fails(tmp_path: Path) -> None:
    """A Claude UUID injected into an active section of a Codex bundle is flagged."""
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "codex" / "cx-cto.md"
    bundle.write_text(bundle.read_text() + f"\n\nPATCH assigneeAgentId={CLAUDE_CTO_UUID}\n")

    bundle_paths = {"codex:cx-cto": bundle}
    role_meta = {"codex:cx-cto": _cx_meta()}
    errors = validate_instructions.validate_cross_team_targets(bundle_paths, role_meta, repo)

    assert any("cross-team UUID" in e and CLAUDE_CTO_UUID[:8] in e for e in errors)


def test_cross_team_antipattern_context_allowed(tmp_path: Path) -> None:
    """Foreign UUID in a NOT/anti-pattern line is allowed (lookup-table case)."""
    repo = make_repo(tmp_path)
    bundle = repo / "paperclips" / "dist" / "codex" / "cx-cto.md"
    bundle.write_text(
        bundle.read_text()
        + f"\n\nNEVER assign Claude CTO ({CLAUDE_CTO_UUID}) — use CXCTO.\n"
    )

    bundle_paths = {"codex:cx-cto": bundle}
    role_meta = {"codex:cx-cto": _cx_meta()}
    errors = validate_instructions.validate_cross_team_targets(bundle_paths, role_meta, repo)

    assert errors == []


def test_runbook_profile_requires_inline_rule(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    profiles_path = repo / "paperclips" / "instruction-profiles.yaml"
    profiles_path.write_text(
        profiles_path.read_text()
        + "\n  unsafe-runbook-only:\n"
        + "    fragments:\n"
        + "      - paperclips/fragments/shared/fragments/language.md\n"
        + "    runbooks:\n"
        + "      - paperclips/fragments/shared/fragments/phase-handoff.md\n"
    )

    errors = validate_instructions.validate(repo)

    assert any("has runbooks but does not require inline rules" in error for error in errors)
