"""Phase F: uaudit migration — extract bindings + paths + plugins, strip manifest."""
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
HOST = Path(os.path.expanduser("~/.paperclip/projects/uaudit"))
FIX = REPO / "paperclips" / "tests" / "fixtures" / "phase_f"
SCRIPTS = REPO / "paperclips" / "scripts"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


# ---------------------------------------------------------------------------
# CI tests — no host-local needed.
# ---------------------------------------------------------------------------


def test_migrate_bindings_dry_run_against_pre_migration_backup(tmp_path, monkeypatch):
    """Replay migrate-bindings.sh against PRE-Phase-F backup; verify 17 UUIDs match expected fixture."""
    monkeypatch.setenv("HOME", str(tmp_path))
    synth = tmp_path / "synth-repo"
    (synth / "paperclips" / "projects" / "uaudit").mkdir(parents=True)
    (synth / "paperclips" / "scripts" / "lib").mkdir(parents=True)
    (synth / "paperclips" / "scripts" / "lib" / "canonical_acronyms.txt").write_text(
        (REPO / "paperclips" / "scripts" / "lib" / "canonical_acronyms.txt").read_text()
    )
    for lib in ("_common.sh", "_paperclip_api.sh"):
        (synth / "paperclips" / "scripts" / "lib" / lib).symlink_to(
            REPO / "paperclips" / "scripts" / "lib" / lib
        )
    (synth / "paperclips" / "scripts" / "migrate-bindings.sh").symlink_to(
        REPO / "paperclips" / "scripts" / "migrate-bindings.sh"
    )
    pre_manifest = REPO / "paperclips" / "tests" / "baseline" / "phase_f" / "uaudit-manifest-pre.yaml"
    if not pre_manifest.is_file():
        pytest.skip("pre-migration backup not present (Task 1 not yet run)")
    (synth / "paperclips" / "projects" / "uaudit" / "paperclip-agent-assembly.yaml").write_text(
        pre_manifest.read_text()
    )
    out = subprocess.run(
        ["bash", str(synth / "paperclips" / "scripts" / "migrate-bindings.sh"),
         "uaudit", "--dry-run"],
        capture_output=True, text=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    assert out.returncode == 0, f"dry-run failed: {out.stderr}"
    body_start = out.stdout.find("schemaVersion:")
    assert body_start != -1, f"no YAML body:\n{out.stdout}"
    data = yaml.safe_load(out.stdout[body_start:])
    expected = yaml.safe_load((FIX / "expected_uaudit_bindings.yaml").read_text())
    assert data["schemaVersion"] == expected["schemaVersion"]
    assert data["company_id"] == expected["company_id"]
    assert set(data["agents"].keys()) == set(expected["agents"].keys())
    assert len(data["agents"]) == 17
    for name, expected_uuid in expected["agents"].items():
        assert data["agents"][name] == expected_uuid


def test_expected_uaudit_bindings_has_17_canonical_agents():
    expected = yaml.safe_load((FIX / "expected_uaudit_bindings.yaml").read_text())
    assert len(expected["agents"]) == 17
    # All UWIxxx / UWAxxx / AUCEO — codex-only project
    for name, uuid in expected["agents"].items():
        assert UUID_RE.match(uuid), f"{name}: invalid UUID {uuid!r}"


# ---------------------------------------------------------------------------
# Post-Phase-F-Task-3 tests (manifest stripped to v2).
# ---------------------------------------------------------------------------

UAUDIT_MANIFEST = REPO / "paperclips" / "projects" / "uaudit" / "paperclip-agent-assembly.yaml"


def test_uaudit_manifest_passes_validator():
    import sys
    sys.path.insert(0, str(REPO / "paperclips" / "scripts"))
    from validate_manifest import validate_manifest
    validate_manifest(UAUDIT_MANIFEST)


def test_uaudit_manifest_has_schemaVersion_2():
    data = yaml.safe_load(UAUDIT_MANIFEST.read_text())
    assert data["schemaVersion"] == 2


def test_uaudit_manifest_no_inline_uuids():
    text = UAUDIT_MANIFEST.read_text()
    matches = re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        text, re.I,
    )
    assert not matches, f"inline UUIDs in manifest: {matches}"


def test_uaudit_manifest_no_abs_paths():
    text = UAUDIT_MANIFEST.read_text()
    matches = re.findall(r"/Users/Shared|/home/|/Users/me", text)
    assert not matches, f"abs paths in manifest: {matches}"


def test_uaudit_manifest_has_17_agents():
    data = yaml.safe_load(UAUDIT_MANIFEST.read_text())
    assert len(data["agents"]) == 17


def test_uaudit_manifest_all_agents_codex_target():
    """uaudit is codex-only — no claude agents."""
    data = yaml.safe_load(UAUDIT_MANIFEST.read_text())
    for a in data["agents"]:
        assert a["target"] == "codex", f"{a['agent_name']}: target={a['target']!r} (expected codex)"


def test_uaudit_manifest_uses_profile_field():
    data = yaml.safe_load(UAUDIT_MANIFEST.read_text())
    valid = {"custom", "minimal", "research", "writer", "implementer", "qa", "reviewer", "cto"}
    for a in data["agents"]:
        assert "profile" in a, f"agent {a['agent_name']} missing profile"
        assert a["profile"] in valid, f"{a['agent_name']}: invalid profile {a['profile']!r}"


def test_uaudit_manifest_no_telegram_plugin_id_field():
    """report_delivery.telegram_plugin_id moved to host-local plugins.yaml.

    Allows substring in comments; rejects YAML key form.
    """
    data = yaml.safe_load(UAUDIT_MANIFEST.read_text())

    def _walk(node):
        if isinstance(node, dict):
            assert "telegram_plugin_id" not in node, \
                f"telegram_plugin_id YAML key still present in manifest: {node}"
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)


# ---------------------------------------------------------------------------
# Render-delta tests (post-Phase-F output vs pre-migration baseline).
# ---------------------------------------------------------------------------

BASELINE_DIST = REPO / "paperclips" / "tests" / "baseline" / "phase_f" / "uaudit-dist-pre"
CURRENT_DIST = REPO / "paperclips" / "dist" / "uaudit"


def _diff_lines(a: str, b: str) -> list[tuple[str, str]]:
    al, bl = a.splitlines(), b.splitlines()
    if len(al) != len(bl):
        return [("__count_mismatch__", f"{len(al)} vs {len(bl)} lines")]
    return [(x, y) for x, y in zip(al, bl) if x != y]


def _list_agents() -> list[str]:
    return sorted(p.name for p in (BASELINE_DIST / "codex").glob("*.md")) if BASELINE_DIST.is_dir() else []


@pytest.mark.parametrize("agent_md", _list_agents() or ["__skip__"])
def test_phase_f_render_delta_expected_substitutions_only(agent_md):
    """Post-Phase-F output must differ from baseline ONLY in:
    - workspace_cwd line (abs → relative template form)
    - /Users/Shared/UnstoppableAudit → /opt/uaa-example/uaudit (CI fallback paths)
    - telegram_plugin_id 60023916-... → 00000000-... (CI fallback plugins)
    """
    if agent_md == "__skip__":
        pytest.skip("baseline dist not present (Task 1 backup missing)")
    baseline = BASELINE_DIST / "codex" / agent_md
    current = CURRENT_DIST / "codex" / agent_md
    if not baseline.is_file() or not current.is_file():
        pytest.skip(f"{agent_md} baseline or current missing")
    deltas = _diff_lines(baseline.read_text(), current.read_text())
    if deltas and deltas[0][0] == "__count_mismatch__":
        pytest.fail(
            f"{agent_md} line count differs (baseline vs current): {deltas[0][1]}"
        )
    for old, new in deltas:
        if "Workspace cwd" in old or "Workspace cwd" in new:
            continue
        if "/Users/Shared/UnstoppableAudit" in old and "/opt/uaa-example/uaudit" in new:
            continue
        if "60023916-4b6c-40f5-829f-bc8b98abc4ed" in old and \
           "00000000-0000-0000-0000-000000000000" in new:
            continue
        # company_id real → CI-fallback sentinel
        if "8f55e80b-0264-4ab6-9d56-8b2652f18005" in old and \
           "00000000-0000-0000-0000-000000000001" in new:
            continue
        pytest.fail(
            f"unexpected delta in {agent_md}:\n  baseline: {old!r}\n  current:  {new!r}"
        )


# ---------------------------------------------------------------------------
# Post-live-migration tests (skip in CI).
# ---------------------------------------------------------------------------


def test_uaudit_bindings_yaml_exists_post_live_migration():
    p = HOST / "bindings.yaml"
    if not p.is_file():
        pytest.skip("host-local uaudit bindings not present")
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2
    assert len(data["agents"]) == 17


def test_uaudit_paths_yaml_exists_post_live_migration():
    p = HOST / "paths.yaml"
    if not p.is_file():
        pytest.skip("host-local uaudit paths not present")
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2


def test_uaudit_plugins_yaml_exists_post_live_migration():
    p = HOST / "plugins.yaml"
    if not p.is_file():
        pytest.skip("host-local uaudit plugins not present")
    data = yaml.safe_load(p.read_text())
    assert "telegram" in data
    assert UUID_RE.match(data["telegram"]["plugin_id"])


# ---------------------------------------------------------------------------
# F-fix IMP batch — tests for findings from 4-voltAgent deep-review.
# ---------------------------------------------------------------------------


def test_bindings_local_example_matches_manifest_agent_set():
    """F-fix code-rev I4: bindings.local-example.yaml agents{} must mirror
    manifest's agents[] keys, otherwise CI builds fail confusingly when
    operator adds an agent without updating the fallback.
    """
    fb = yaml.safe_load(
        (REPO / "paperclips" / "projects" / "uaudit" / "bindings.local-example.yaml").read_text()
    )
    mf = yaml.safe_load(UAUDIT_MANIFEST.read_text())
    fb_names = set(fb["agents"].keys())
    mf_names = {a["agent_name"] for a in mf["agents"]}
    missing_in_fallback = mf_names - fb_names
    extra_in_fallback = fb_names - mf_names
    assert not missing_in_fallback, (
        f"bindings.local-example.yaml missing agents from manifest: {missing_in_fallback}"
    )
    assert not extra_in_fallback, (
        f"bindings.local-example.yaml has agents not in manifest: {extra_in_fallback}"
    )


def test_uaudit_overlay_has_no_hardcoded_abs_paths():
    """F-fix security I-1 + architect I-3: overlays must use {{paths.X}}
    templates, not hardcoded /Users/Shared/UnstoppableAudit/... shell snippets.
    """
    overlays = REPO / "paperclips" / "projects" / "uaudit" / "overlays"
    bad = []
    for md in overlays.rglob("*.md"):
        text = md.read_text()
        if re.search(r"/Users/Shared/UnstoppableAudit", text):
            bad.append(str(md.relative_to(REPO)))
    assert not bad, f"uaudit overlays have hardcoded abs paths: {bad}"


# Expected profile per agent — snapshot of Phase F design decisions.
_EXPECTED_PROFILES = {
    "AUCEO": "cto",
    "UWICTO": "cto",
    "UWACTO": "cto",
    "UWISwiftAuditor": "reviewer",
    "UWAKotlinAuditor": "reviewer",
    "UWICryptoAuditor": "implementer",  # preserved from v1 (cx-blockchain-engineer default)
    "UWACryptoAuditor": "implementer",  # preserved from v1
    "UWISecurityAuditor": "reviewer",
    "UWASecurityAuditor": "reviewer",
    "UWIQAEngineer": "qa",
    "UWAQAEngineer": "qa",
    "UWIInfraEngineer": "implementer",
    "UWAInfraEngineer": "implementer",
    "UWIResearchAgent": "research",
    "UWAResearchAgent": "research",
    "UWITechnicalWriter": "writer",
    "UWATechnicalWriter": "writer",
}


def test_uaudit_per_agent_profile_snapshot():
    """F-fix QA gap 4 + code-rev W2: enforce per-agent profile mapping (was
    only checked at "is one of 8 valid strings" level — wouldn't catch drift)."""
    data = yaml.safe_load(UAUDIT_MANIFEST.read_text())
    actual = {a["agent_name"]: a["profile"] for a in data["agents"]}
    assert actual == _EXPECTED_PROFILES, (
        f"profile mapping drift:\n"
        f"  unexpected: {set(actual.items()) - set(_EXPECTED_PROFILES.items())}\n"
        f"  missing:    {set(_EXPECTED_PROFILES.items()) - set(actual.items())}"
    )


def test_company_id_bridge_via_bindings_local_example():
    """F-fix QA C2: company_id from bindings.local-example.yaml must surface
    into resolved-assembly.json parameters.project.companyId for v2 manifests
    (was empty string pre-F-fix-C1). Isolates the bridge code path."""
    import json
    resolved = json.loads(
        (REPO / "paperclips" / "dist" / "uaudit.resolved-assembly.json").read_text()
    )
    expected = "00000000-0000-0000-0000-000000000001"  # from bindings.local-example.yaml
    actual = resolved["parameters"]["project"]["companyId"]
    assert actual == expected, (
        f"companyId bridge regression: expected {expected!r}, got {actual!r}. "
        f"Phase F resolved_assembly must read from host-local bindings when "
        f"manifest has stripped project.company_id."
    )


def test_baseline_dist_dir_present():
    """F-fix QA C3: render-delta test parametrize silently skips if baseline
    dir absent (test gets [__skip__] case → green CI). Explicit guard fails
    test collection loud if baseline gets accidentally deleted."""
    assert BASELINE_DIST.is_dir(), (
        f"Phase F baseline dir missing at {BASELINE_DIST.relative_to(REPO)}. "
        f"render-delta parametrize would silently skip → green CI without "
        f"actually testing render-delta. Restore from git or re-run Task 1."
    )
    files = list((BASELINE_DIST / "codex").glob("*.md"))
    assert len(files) == 17, f"baseline dist should have 17 agent files, got {len(files)}"


def test_host_local_bindings_takes_precedence_over_ci_fallback(tmp_path, monkeypatch):
    """F-fix QA C1: when operator's ~/.paperclip/projects/uaudit/bindings.yaml
    exists, it must override paperclips/projects/uaudit/bindings.local-example.yaml.
    Without this test, an inverted precedence would still pass CI (no host-local
    in CI → always fallback path used)."""
    import sys
    sys.path.insert(0, str(REPO / "paperclips" / "scripts"))
    monkeypatch.setenv("HOME", str(tmp_path))

    # Plant operator host-local with DISTINCT UUIDs (not in CI fallback).
    operator_company = "deadbeef-cafe-babe-feed-0123456789ab"
    operator_uuid = "11111111-2222-3333-4444-555555555555"
    proj = tmp_path / ".paperclip" / "projects" / "uaudit"
    proj.mkdir(parents=True)
    (proj / "bindings.yaml").write_text(
        f"schemaVersion: 2\n"
        f'company_id: "{operator_company}"\n'
        f"agents:\n"
        f'  AUCEO: "{operator_uuid}"\n'
    )

    # Force module reimport so resolve_bindings picks up monkeypatched HOME.
    for mod in ("build_project_compat", "resolve_bindings"):
        sys.modules.pop(mod, None)
    import importlib
    bpc = importlib.import_module("build_project_compat")
    sources = bpc._load_host_local_sources("uaudit", repo_root=REPO)

    assert sources.get("bindings", {}).get("company_id") == operator_company, (
        f"host-local bindings.yaml didn't override CI fallback: "
        f"got {sources.get('bindings', {}).get('company_id')!r}, "
        f"expected {operator_company!r}"
    )
    assert sources["bindings"]["agents"].get("AUCEO") == operator_uuid
