"""Phase E: trading migration — extract UUIDs/paths + clean manifest."""
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
HOST = Path(os.path.expanduser("~/.paperclip/projects/trading"))
FIX = REPO / "paperclips" / "tests" / "fixtures" / "phase_e"
SCRIPTS = REPO / "paperclips" / "scripts"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


# ---------------------------------------------------------------------------
# Tests that work without operator's live ~/.paperclip — runnable in CI.
# ---------------------------------------------------------------------------


def test_migrate_bindings_dry_run_against_pre_migration_backup(tmp_path, monkeypatch):
    """Code-side smoke: replay migrate-bindings.sh against the PRE-Phase-E
    backup manifest (committed under paperclips/tests/baseline/phase_e/) —
    verifies the script + expected fixture stay in sync.

    Operator flow: migrate-bindings runs BEFORE manifest cleanup (Task 3).
    After Task 3 the live manifest has no inline agent_id, so this test
    uses the snapshot taken in Task 1.
    """
    monkeypatch.setenv("HOME", str(tmp_path))

    # Build a synthetic repo root pointing at the pre-migration backup as
    # paperclips/projects/trading/paperclip-agent-assembly.yaml.
    synth = tmp_path / "synth-repo"
    (synth / "paperclips" / "projects" / "trading").mkdir(parents=True)
    (synth / "paperclips" / "scripts" / "lib").mkdir(parents=True)
    (synth / "paperclips" / "scripts" / "lib" / "canonical_acronyms.txt").write_text(
        (REPO / "paperclips" / "scripts" / "lib" / "canonical_acronyms.txt").read_text()
    )
    # Symlink real lib helpers into the synth repo so migrate-bindings.sh works
    for lib in ("_common.sh", "_paperclip_api.sh"):
        (synth / "paperclips" / "scripts" / "lib" / lib).symlink_to(
            REPO / "paperclips" / "scripts" / "lib" / lib
        )
    # Copy the migrate-bindings.sh script into synth (paths are SCRIPT_DIR-relative)
    (synth / "paperclips" / "scripts" / "migrate-bindings.sh").symlink_to(
        REPO / "paperclips" / "scripts" / "migrate-bindings.sh"
    )
    # Drop the pre-migration manifest as trading's manifest
    pre_manifest = REPO / "paperclips" / "tests" / "baseline" / "phase_e" / "trading-manifest-pre.yaml"
    if not pre_manifest.is_file():
        pytest.skip("pre-migration backup not present (Task 1 not yet run)")
    (synth / "paperclips" / "projects" / "trading" / "paperclip-agent-assembly.yaml").write_text(
        pre_manifest.read_text()
    )

    out = subprocess.run(
        ["bash", str(synth / "paperclips" / "scripts" / "migrate-bindings.sh"),
         "trading", "--dry-run"],
        capture_output=True, text=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    assert out.returncode == 0, f"dry-run failed: {out.stderr}"
    body_start = out.stdout.find("schemaVersion:")
    assert body_start != -1, f"no YAML body in dry-run output:\n{out.stdout}"
    data = yaml.safe_load(out.stdout[body_start:])

    expected = yaml.safe_load((FIX / "expected_trading_bindings.yaml").read_text())
    assert data["schemaVersion"] == expected["schemaVersion"]
    assert data["company_id"] == expected["company_id"]
    assert set(data["agents"].keys()) == set(expected["agents"].keys())
    for name, expected_uuid in expected["agents"].items():
        assert data["agents"][name] == expected_uuid, \
            f"{name}: expected {expected_uuid!r}, got {data['agents'][name]!r}"


def test_expected_trading_bindings_has_all_5_canonical_agents():
    expected = yaml.safe_load((FIX / "expected_trading_bindings.yaml").read_text())
    assert set(expected["agents"].keys()) == {
        "CEO", "CTO", "CodeReviewer", "PythonEngineer", "QAEngineer"
    }
    for name, uuid in expected["agents"].items():
        assert UUID_RE.match(uuid), f"{name}: invalid UUID {uuid!r}"


# ---------------------------------------------------------------------------
# Tests that run only on operator's host AFTER live migration (Task 7).
# Skipped in CI. Verify ~/.paperclip/projects/trading/ is correctly populated.
# ---------------------------------------------------------------------------


def test_trading_bindings_yaml_exists_post_live_migration():
    p = HOST / "bindings.yaml"
    if not p.is_file():
        pytest.skip(
            "host-local trading bindings not present; runs post-operator-live-migration"
        )
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2
    assert data["company_id"]
    for name in ("CEO", "CTO", "CodeReviewer", "PythonEngineer", "QAEngineer"):
        assert name in data["agents"], f"missing agent {name}"
    for name, uuid in data["agents"].items():
        assert UUID_RE.match(uuid), f"{name}: invalid UUID format: {uuid!r}"


def test_trading_paths_yaml_exists_post_live_migration():
    p = HOST / "paths.yaml"
    if not p.is_file():
        pytest.skip(
            "host-local trading paths not present; runs post-operator-live-migration"
        )
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2
    for k in ("project_root", "team_workspace_root", "operator_memory_dir"):
        assert k in data, f"missing key: {k}"


# ---------------------------------------------------------------------------
# Task 3: committed manifest must be UUID-free + path-free, schemaVersion 2.
# ---------------------------------------------------------------------------

TRADING_MANIFEST = REPO / "paperclips" / "projects" / "trading" / "paperclip-agent-assembly.yaml"


def test_trading_manifest_passes_validator():
    import sys
    sys.path.insert(0, str(REPO / "paperclips" / "scripts"))
    from validate_manifest import validate_manifest
    validate_manifest(TRADING_MANIFEST)


def test_trading_manifest_has_schemaVersion_2():
    data = yaml.safe_load(TRADING_MANIFEST.read_text())
    assert data["schemaVersion"] == 2


def test_trading_manifest_no_inline_uuids():
    text = TRADING_MANIFEST.read_text()
    matches = re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        text, re.I,
    )
    assert not matches, f"inline UUIDs in manifest: {matches}"


def test_trading_manifest_no_abs_paths():
    text = TRADING_MANIFEST.read_text()
    matches = re.findall(r"/Users/Shared|/home/|/Users/me", text)
    assert not matches, f"abs paths in manifest: {matches}"


def test_trading_manifest_has_5_agents():
    data = yaml.safe_load(TRADING_MANIFEST.read_text())
    assert len(data["agents"]) == 5
    names = {a["agent_name"] for a in data["agents"]}
    assert names == {"CEO", "CTO", "CodeReviewer", "PythonEngineer", "QAEngineer"}


def test_trading_manifest_uses_profile_field():
    """Each agent must declare profile (per UAA §6.1)."""
    data = yaml.safe_load(TRADING_MANIFEST.read_text())
    valid_profiles = {
        "custom", "minimal", "research", "writer",
        "implementer", "qa", "reviewer", "cto",
    }
    for a in data["agents"]:
        assert "profile" in a, f"agent {a['agent_name']} missing profile"
        assert a["profile"] in valid_profiles, \
            f"agent {a['agent_name']} unknown profile: {a['profile']}"


# ---------------------------------------------------------------------------
# E-fix C5: v2 detection robustness — covers quoted / float / commented forms.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("schemaVersion: 2\n", True),                       # canonical
    ("schemaVersion: 2  # phase E\n", True),            # trailing comment
    ('schemaVersion: "2"\n', True),                     # quoted string
    ("schemaVersion: '2'\n", True),                     # single-quoted string
    ("schemaVersion: 2.0\n", True),                     # float
    ("schemaVersion: 1\n", False),                      # v1 — must NOT match
    ("schemaVersion: 3\n", False),                      # future version, not v2
    ("# schemaVersion: 2\n", False),                    # commented out
    ("nested:\n  schemaVersion: 2\n", False),           # indented (not top-level)
])
def test_v2_detection_tolerant(text, expected):
    """E-fix C5: _is_v2_manifest_text accepts canonical + quoted + float forms."""
    import sys
    sys.path.insert(0, str(REPO / "paperclips" / "scripts"))
    from validate_instructions import _is_v2_manifest_text
    assert _is_v2_manifest_text(text) == expected, \
        f"detector got wrong result for {text!r}: expected {expected}"


# ---------------------------------------------------------------------------
# Task 5: re-render delta — post-Phase-E output should differ ONLY in the
# workspace_cwd line (abs path → relative + descriptive form).
# ---------------------------------------------------------------------------

BASELINE_DIST = REPO / "paperclips" / "tests" / "baseline" / "phase_e" / "trading-dist-pre"
CURRENT_DIST = REPO / "paperclips" / "dist" / "trading"


def _diff_lines(a: str, b: str) -> list[tuple[str, str]]:
    """Pair lines that differ between two texts (assumes same line count)."""
    al, bl = a.splitlines(), b.splitlines()
    if len(al) != len(bl):
        return [("__count_mismatch__", f"{len(al)} vs {len(bl)} lines")]
    return [(x, y) for x, y in zip(al, bl) if x != y]


@pytest.mark.parametrize("subpath", [
    "claude/CTO.md",
    "codex/CEO.md",
    "codex/CodeReviewer.md",
    "codex/PythonEngineer.md",
    "codex/QAEngineer.md",
])
def test_phase_e_render_delta_only_workspace_cwd_line(subpath):
    """The only change in built artifacts post-Phase-E must be the
    'Workspace cwd:' line. Everything else (handoff fragments, role text,
    overlay substitutions for non-host-local fields) must be byte-identical
    to the pre-migration baseline.
    """
    baseline = BASELINE_DIST / subpath
    current = CURRENT_DIST / subpath
    if not baseline.is_file():
        pytest.skip(f"baseline {subpath} not present (Task 1 baseline missing)")
    deltas = _diff_lines(baseline.read_text(), current.read_text())
    # E-fix C6: explicit count-mismatch guard before the per-line loop.
    # Previously the sentinel `__count_mismatch__` reached `pytest.fail` with
    # an opaque "baseline: '__count_mismatch__'" message — undebuggable.
    if deltas and deltas[0][0] == "__count_mismatch__":
        pytest.fail(
            f"{subpath} line count differs (baseline vs current): {deltas[0][1]} — "
            f"a shared fragment likely added/removed a line. Refresh the baseline "
            f"after verifying the change is intentional."
        )
    for old, new in deltas:
        # Expected delta 1: workspace_cwd line (template form replaced inline path)
        if "Workspace cwd" in old or "Workspace cwd" in new:
            continue
        # Expected delta 2: CI-fallback paths from paths.local-example.yaml.
        # Operator's host-local paths.yaml will substitute /Users/Shared/Trading/...
        # back in; CI uses sanitized /opt/example/trading/... values.
        if "/Users/Shared/Trading" in old and "/opt/example/trading" in new:
            continue
        pytest.fail(
            f"unexpected post-Phase-E delta in {subpath}:\n"
            f"  baseline: {old!r}\n"
            f"  current:  {new!r}"
        )
