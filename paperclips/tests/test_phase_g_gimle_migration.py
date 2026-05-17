"""Phase G: gimle migration — 24 agents (12 claude + 12 codex), legacy compat preserved."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
HOST = Path(os.path.expanduser("~/.paperclip/projects/gimle"))
FIX = REPO / "paperclips" / "tests" / "fixtures" / "phase_g"
SCRIPTS = REPO / "paperclips" / "scripts"
GIMLE_MANIFEST = REPO / "paperclips" / "projects" / "gimle" / "paperclip-agent-assembly.yaml"
BASELINE_DIST = REPO / "paperclips" / "tests" / "baseline" / "phase_g" / "gimle-dist-pre"
# Gimle preserves legacy_output_paths: true per spec §10.5 (cleanup gated to Phase H).
# Claude: paperclips/dist/*.md ; Codex: paperclips/dist/codex/*.md
CURRENT_DIST_CLAUDE = REPO / "paperclips" / "dist"
CURRENT_DIST_CODEX = REPO / "paperclips" / "dist" / "codex"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


# ---------------------------------------------------------------------------
# Manifest shape — v2 schema enforcement.
# ---------------------------------------------------------------------------


def test_gimle_manifest_passes_validator():
    sys.path.insert(0, str(SCRIPTS))
    from validate_manifest import validate_manifest
    validate_manifest(GIMLE_MANIFEST)


def test_gimle_manifest_has_schemaVersion_2():
    data = yaml.safe_load(GIMLE_MANIFEST.read_text())
    assert data["schemaVersion"] == 2


def test_gimle_manifest_no_inline_uuids():
    text = GIMLE_MANIFEST.read_text()
    matches = re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        text, re.I,
    )
    assert not matches, f"inline UUIDs in manifest: {matches}"


def test_gimle_manifest_no_abs_paths():
    text = GIMLE_MANIFEST.read_text()
    # Phase G: paths.* host-local stripped (project_root, primary_repo_root,
    # production_checkout, codex_team_root, operator_memory_dir).
    # Kept (relative): primary_mcp_service_dir, overlay_root, project_rules_file.
    matches = re.findall(r"/Users/Shared|/home/|/Users/me", text)
    assert not matches, f"abs paths in manifest: {matches}"


def test_gimle_manifest_has_24_agents_split_12_12():
    data = yaml.safe_load(GIMLE_MANIFEST.read_text())
    agents = data["agents"]
    assert len(agents) == 24
    claude = [a for a in agents if a["target"] == "claude"]
    codex = [a for a in agents if a["target"] == "codex"]
    assert len(claude) == 12
    assert len(codex) == 12


def test_gimle_manifest_uses_kebab_agent_names_preserves_v1_render():
    """v1 used kebab agent_names from deploy-agents.sh + codex-agent-ids.env
    (derived). v2 manifest must also use kebab to keep render byte-identical."""
    data = yaml.safe_load(GIMLE_MANIFEST.read_text())
    for a in data["agents"]:
        name = a["agent_name"]
        # kebab = lowercase + dashes, no uppercase
        assert name == name.lower(), f"{name}: not lowercase kebab"
        assert "_" not in name, f"{name}: contains underscore"


def test_gimle_manifest_uses_profile_field():
    data = yaml.safe_load(GIMLE_MANIFEST.read_text())
    valid = {"custom", "minimal", "research", "writer", "implementer", "qa", "reviewer", "cto"}
    for a in data["agents"]:
        assert "profile" in a, f"agent {a['agent_name']} missing profile"
        assert a["profile"] in valid, f"{a['agent_name']}: invalid profile {a['profile']!r}"


def test_gimle_manifest_keeps_legacy_compat_paths():
    """Per spec §10.5, gimle's legacy compat files (deploy-agents.sh +
    codex-agent-ids.env) stay in repo until Phase H cleanup gate. Manifest's
    compatibility.* must keep pointing at them so dual-read resolver works."""
    data = yaml.safe_load(GIMLE_MANIFEST.read_text())
    compat = data["compatibility"]
    assert compat["claude_deploy_mapping"] == "paperclips/deploy-agents.sh"
    assert compat["codex_agent_ids_env"] == "paperclips/codex-agent-ids.env"


# Expected profile per agent (24-entry snapshot — locks v1 implicit defaults).
_EXPECTED_PROFILES = {
    # Claude (12)
    "cto": "cto",
    "code-reviewer": "reviewer",
    "python-engineer": "implementer",
    "qa-engineer": "qa",
    "technical-writer": "writer",
    "infra-engineer": "implementer",
    "mcp-engineer": "implementer",
    "research-agent": "research",
    "blockchain-engineer": "implementer",
    "security-auditor": "reviewer",
    "auditor": "reviewer",
    "opus-architect-reviewer": "reviewer",
    # Codex (12)
    "cx-cto": "cto",
    "cx-code-reviewer": "reviewer",
    "cx-python-engineer": "implementer",
    "cx-qa-engineer": "qa",
    "cx-technical-writer": "writer",
    "cx-infra-engineer": "implementer",
    "cx-mcp-engineer": "implementer",
    "cx-research-agent": "research",
    "cx-blockchain-engineer": "implementer",
    "cx-security-auditor": "reviewer",
    "cx-auditor": "reviewer",
    "codex-architect-reviewer": "reviewer",
}


def test_gimle_per_agent_profile_snapshot():
    data = yaml.safe_load(GIMLE_MANIFEST.read_text())
    actual = {a["agent_name"]: a["profile"] for a in data["agents"]}
    assert actual == _EXPECTED_PROFILES, (
        f"profile mapping drift:\n"
        f"  unexpected: {set(actual.items()) - set(_EXPECTED_PROFILES.items())}\n"
        f"  missing:    {set(_EXPECTED_PROFILES.items()) - set(actual.items())}"
    )


# ---------------------------------------------------------------------------
# CI fallback files.
# ---------------------------------------------------------------------------


def test_bindings_local_example_matches_manifest_agent_set():
    fb = yaml.safe_load(
        (REPO / "paperclips" / "projects" / "gimle" / "bindings.local-example.yaml").read_text()
    )
    mf = yaml.safe_load(GIMLE_MANIFEST.read_text())
    fb_names = set(fb["agents"].keys())
    mf_names = {a["agent_name"] for a in mf["agents"]}
    missing = mf_names - fb_names
    extra = fb_names - mf_names
    assert not missing, f"bindings.local-example.yaml missing: {missing}"
    assert not extra, f"bindings.local-example.yaml extra: {extra}"


def test_gimle_overlay_has_no_hardcoded_abs_paths():
    """Per Phase E/F precedent: overlays must use {{paths.X}} templates,
    not hardcoded /Users/Shared/Ios/Gimle-Palace/... paths."""
    overlays = REPO / "paperclips" / "projects" / "gimle" / "overlays"
    if not overlays.is_dir():
        pytest.skip("gimle overlays dir absent — no per-project overlays defined")
    bad = []
    for md in overlays.rglob("*.md"):
        text = md.read_text()
        if re.search(r"/Users/Shared/Ios/Gimle-Palace", text):
            bad.append(str(md.relative_to(REPO)))
    assert not bad, f"gimle overlays have hardcoded abs paths: {bad}"


# ---------------------------------------------------------------------------
# Render-delta — post-Phase-G output vs pre-Phase-G baseline.
# ---------------------------------------------------------------------------


def _diff_lines(a: str, b: str) -> list[tuple[str, str]]:
    al, bl = a.splitlines(), b.splitlines()
    if len(al) != len(bl):
        return [("__count_mismatch__", f"{len(al)} vs {len(bl)} lines")]
    return [(x, y) for x, y in zip(al, bl) if x != y]


def _list_agents_for(target: str) -> list[str]:
    d = BASELINE_DIST / target
    return sorted(p.name for p in d.glob("*.md")) if d.is_dir() else []


def test_baseline_dist_dir_present():
    assert BASELINE_DIST.is_dir(), (
        f"Phase G baseline dir missing at {BASELINE_DIST.relative_to(REPO)}. "
        f"Restore from git or re-run Task 1 snapshot."
    )
    assert (BASELINE_DIST / "claude").is_dir() and (BASELINE_DIST / "codex").is_dir()
    assert len(list((BASELINE_DIST / "claude").glob("*.md"))) == 12
    assert len(list((BASELINE_DIST / "codex").glob("*.md"))) == 12


@pytest.mark.parametrize("agent_md", _list_agents_for("claude") or ["__skip__"])
def test_phase_g_render_delta_claude(agent_md):
    if agent_md == "__skip__":
        pytest.fail("claude baseline missing")
    baseline = BASELINE_DIST / "claude" / agent_md
    current = CURRENT_DIST_CLAUDE / agent_md
    if not current.is_file():
        pytest.fail(f"current build missing for claude/{agent_md}")
    deltas = _diff_lines(baseline.read_text(), current.read_text())
    if deltas and deltas[0][0] == "__count_mismatch__":
        pytest.fail(f"claude/{agent_md} line count differs: {deltas[0][1]}")
    for old, new in deltas:
        if "/Users/Shared/Ios/Gimle-Palace" in old and "/opt/uaa-example/gimle" in new:
            continue
        pytest.fail(
            f"unexpected delta in claude/{agent_md}:\n  baseline: {old!r}\n  current:  {new!r}"
        )


@pytest.mark.parametrize("agent_md", _list_agents_for("codex") or ["__skip__"])
def test_phase_g_render_delta_codex(agent_md):
    if agent_md == "__skip__":
        pytest.fail("codex baseline missing")
    baseline = BASELINE_DIST / "codex" / agent_md
    current = CURRENT_DIST_CODEX / agent_md
    if not current.is_file():
        pytest.fail(f"current build missing for codex/{agent_md}")
    deltas = _diff_lines(baseline.read_text(), current.read_text())
    if deltas and deltas[0][0] == "__count_mismatch__":
        pytest.fail(f"codex/{agent_md} line count differs: {deltas[0][1]}")
    for old, new in deltas:
        if "/Users/Shared/Ios/Gimle-Palace" in old and "/opt/uaa-example/gimle" in new:
            continue
        pytest.fail(
            f"unexpected delta in codex/{agent_md}:\n  baseline: {old!r}\n  current:  {new!r}"
        )


# ---------------------------------------------------------------------------
# Builder bridge (Phase F C1 carry-forward).
# ---------------------------------------------------------------------------


def test_company_id_bridge_via_bindings_local_example():
    """Phase F C1 fix: company_id surfaces into resolved-assembly from
    host-local (CI fallback) when manifest is v2-stripped."""
    resolved = json.loads((REPO / "paperclips" / "dist" / "gimle.resolved-assembly.json").read_text())
    expected = "00000000-0000-0000-0000-000000000003"
    actual = resolved["parameters"]["project"]["companyId"]
    assert actual == expected, f"gimle companyId bridge: expected {expected!r}, got {actual!r}"


# ---------------------------------------------------------------------------
# Post-live-migration tests (skipped in CI).
# ---------------------------------------------------------------------------


def test_gimle_bindings_yaml_exists_post_live_migration():
    p = HOST / "bindings.yaml"
    if not p.is_file():
        pytest.skip("host-local gimle bindings not present")
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2
    assert len(data["agents"]) == 24


def test_gimle_paths_yaml_exists_post_live_migration():
    p = HOST / "paths.yaml"
    if not p.is_file():
        pytest.skip("host-local gimle paths not present")
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2
