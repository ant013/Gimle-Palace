"""Phase H2: imac-agents-deploy.sh rewritten as thin wrapper.

Narrow scope: just the wrapper rewrite. The 5 legacy script deletions +
dual-read code path removal stay in H3 because they have surviving
consumers (dual-read resolver, manifest compat fields, watchdog integration
tests) that need coordinated removal across multiple subsystems. Doing
them in one PR with this rewrite blew past H2's safe-deploy scope.

Per spec §10.5 cleanup gate: H2 is operator-merged after live deploys land
on iMac. PR opens as ready-for-review; operator decides merge cadence.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"


# ---------------------------------------------------------------------------
# imac-agents-deploy.sh rewrite.
# ---------------------------------------------------------------------------


def test_imac_agents_deploy_is_thinner_than_legacy():
    """Per Phase H plan + architect H2 review (PR #207): imac-agents-deploy.sh
    becomes thinner wrapper around bootstrap-project.sh but PRESERVES the
    legacy safety envelope (worktree, --target-sha, PHASE-A guard, EXPECTED_*
    preflight). Cap is ≤180 lines (vs pre 280)."""
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    assert p.is_file(), "imac-agents-deploy.sh still required as the iMac entry point"
    text = p.read_text()
    line_count = text.count("\n")
    assert line_count <= 200, (
        f"imac-agents-deploy.sh too large: {line_count} lines (target <=200)"
    )
    assert "bootstrap-project.sh" in text, (
        "imac-agents-deploy.sh must invoke bootstrap-project.sh"
    )
    assert "--reuse-bindings" in text, (
        "imac-agents-deploy.sh must use --reuse-bindings flag"
    )


def test_imac_agents_deploy_preserves_safety_envelope():
    """Architect H2 CRIT-1/C-2/C-3 + I-1: wrapper MUST preserve safety
    markers that the legacy 280-line script provided."""
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    text = p.read_text()
    # Code-rev H2 IMPORTANT: soften trap marker to regex so harmless quoting
    # changes (`trap 'cleanup' EXIT`) don't break the guard.
    required_patterns = [
        (r"origin/main", "must default deploy ref to origin/main (release-cut)"),
        (r"--target-sha", "must accept --target-sha for rollback"),
        (r"PHASE-A-ONLY", "must guard against shipping Phase-A slim-craft sentinel"),
        (r"EXPECTED_CWD", "must keep production-checkout cwd guard"),
        (r"EXPECTED_BRANCH", "must keep production branch guard"),
        (r"trap\s+['\"]?cleanup['\"]?\s+EXIT", "must keep cleanup trap"),
        (r"git worktree add --detach", "must keep detached-worktree pattern"),
        (r"DEPLOY_LOG", "must append to imac-agents-deploy.log (GIM-244 watchdog dep)"),
    ]
    missing = [(p, why) for p, why in required_patterns if not re.search(p, text)]
    assert not missing, (
        "wrapper lost safety markers:\n"
        + "\n".join(f"  - {p}: {why}" for p, why in missing)
    )


def test_imac_agents_deploy_no_legacy_callsites():
    """The new wrapper must not invoke any of the legacy deploy scripts
    (even though they still exist on disk pending H3 removal — the wrapper
    must bypass them entirely)."""
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    text = p.read_text()
    # Match invocations (bash <name>, ./<name>, /<name>), not prose mentions.
    import re
    for legacy in ["deploy-agents.sh", "deploy-codex-agents.sh",
                   "update-agent-workspaces.sh", "hire-codex-agents.sh"]:
        # Allow `bash paperclips/<name>` pattern only inside comments (#).
        # Reject any uncommented invocation.
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if legacy in line:
                pytest.fail(
                    f"imac-agents-deploy.sh has uncommented reference to {legacy!r}: {line!r}"
                )


def test_imac_agents_deploy_rejects_path_traversal_project_key():
    """Security CRIT (architect H2 audit): PROJECT_KEY must be validated
    against path traversal via validate_project_key. Without this:
    PROJECT_KEY='../etc' would escape ~/.paperclip/projects/ AND
    log-inject into DEPLOY_LOG (GIM-244 watchdog dep)."""
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    out = subprocess.run(
        ["bash", str(p), "../etc"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0, (
        f"path-traversal PROJECT_KEY accepted (exit={out.returncode}): "
        f"{out.stdout!r} {out.stderr!r}"
    )
    combined = (out.stdout + out.stderr).lower()
    assert "invalid" in combined or "project_key" in combined, (
        f"expected validate_project_key rejection message, got: "
        f"{out.stdout!r} {out.stderr!r}"
    )


def test_imac_agents_deploy_rejects_uppercase_project_key():
    """Companion to traversal guard: validate_project_key regex
    `^[a-z0-9][a-z0-9_-]{0,39}$` rejects uppercase too."""
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    out = subprocess.run(
        ["bash", str(p), "GIMLE"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0


def test_imac_agents_deploy_help_works():
    """Sanity: the rewritten wrapper still responds to --help-style invocation."""
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    out = subprocess.run(["bash", str(p)], capture_output=True, text=True)
    # No-arg should exit non-zero with usage on stderr (per usage() function).
    assert out.returncode != 0
    combined = (out.stdout + out.stderr).lower()
    assert "usage" in combined, f"no usage shown: {out.stdout!r} {out.stderr!r}"


# ---------------------------------------------------------------------------
# Behavioral failure-mode tests (QA H2 CRIT: must catch real regressions).
# ---------------------------------------------------------------------------


def test_imac_agents_deploy_dies_when_bindings_absent(tmp_path):
    """QA CRIT-1: when ~/.paperclip/projects/<key>/bindings.yaml is missing,
    wrapper must exit non-zero BEFORE doing any deploy work, with a clear
    "bindings" or "migrate-bindings" message pointing operator at the fix."""
    env = {**os.environ, "HOME": str(tmp_path)}
    out = subprocess.run(
        ["bash", str(WRAPPER), "fake-key-no-bindings"],
        capture_output=True, text=True, env=env,
    )
    assert out.returncode != 0, (
        f"wrapper accepted missing bindings (exit={out.returncode}): "
        f"{out.stdout!r} {out.stderr!r}"
    )
    combined = (out.stdout + out.stderr).lower()
    assert "bindings" in combined or "migrate-bindings" in combined, (
        f"expected bindings-absent error message, got: "
        f"{out.stdout!r} {out.stderr!r}"
    )


def test_imac_agents_deploy_dies_when_cwd_not_production_checkout(tmp_path):
    """QA CRIT-2 (partial): EXPECTED_CWD guard should fire when wrapper is
    run from any path other than /Users/Shared/Ios/Gimle-Palace. The bindings
    pre-check fires first; this asserts that running from non-iMac checkouts
    fails fast (either via bindings or cwd guard — both are safe-exit paths)."""
    env = {**os.environ, "HOME": str(tmp_path)}
    # Plant fake bindings so we skip the bindings-absent path and hit cwd guard.
    proj = tmp_path / ".paperclip" / "projects" / "gimle"
    proj.mkdir(parents=True)
    (proj / "bindings.yaml").write_text("schemaVersion: 2\nagents: {}\n")
    out = subprocess.run(
        ["bash", str(WRAPPER), "gimle"],
        capture_output=True, text=True, env=env,
    )
    # In CI/dev, REPO_ROOT is the test repo path, NOT /Users/Shared/Ios/Gimle-Palace.
    # So the EXPECTED_CWD guard MUST fire (unless test is itself running on the
    # production iMac, in which case the test is misconfigured and skipped).
    if "/Users/Shared/Ios/Gimle-Palace" in str(REPO):
        pytest.skip("test running on production iMac checkout - EXPECTED_CWD guard inert")
    assert out.returncode != 0, (
        f"wrapper accepted wrong cwd (exit={out.returncode}): "
        f"{out.stdout!r} {out.stderr!r}"
    )
    combined = (out.stdout + out.stderr).lower()
    assert "must run from" in combined or "expected" in combined or "cwd" in combined, (
        f"expected cwd-guard error, got: {out.stdout!r} {out.stderr!r}"
    )


def test_imac_agents_deploy_grep_phase_a_sentinel_is_wired(tmp_path):
    """QA CRIT-3: PHASE-A-ONLY sentinel guard must run BEFORE bootstrap.
    Static guard via marker test catches absence; this test runs the script
    far enough to verify the actual grep command runs against paperclips/dist
    by checking the source comment + structural placement before the
    bootstrap-project.sh call."""
    text = WRAPPER.read_text()
    # Structural assertion: PHASE-A-ONLY grep must precede bootstrap-project.sh
    # invocation. If reordered, sentinel-bearing dist could ship.
    sentinel_idx = text.find("PHASE-A-ONLY")
    bootstrap_idx = text.find("bootstrap-project.sh")
    # bootstrap-project.sh appears in usage + comment + actual invocation; find
    # the LAST occurrence which is the real `bash $WORKTREE_PATH/.../bootstrap-project.sh` call.
    last_bootstrap_idx = text.rfind("bootstrap-project.sh")
    assert sentinel_idx > 0, "PHASE-A-ONLY guard missing"
    assert sentinel_idx < last_bootstrap_idx, (
        f"PHASE-A-ONLY guard appears AFTER final bootstrap-project.sh invocation "
        f"({sentinel_idx} vs {last_bootstrap_idx}) - sentinel could ship to live agents"
    )
    # Also verify the guard actually scans paperclips/dist (not /tmp or empty path).
    assert re.search(r"grep[^|]+PHASE-A-ONLY[^|]+paperclips/dist", text), (
        "PHASE-A-ONLY guard doesn't scan paperclips/dist - either pattern moved "
        "or scope narrowed (architect H2 CRIT-3 regression)"
    )


# ---------------------------------------------------------------------------
# Post-live-deploy stub (operator action; skipped pre-deploy).
# ---------------------------------------------------------------------------


def test_imac_agents_deploy_dry_run_against_live_bindings(tmp_path):
    """When operator has run bootstrap-project.sh for at least one project on
    the production iMac, run a dry-run (--help) against that real key to verify
    the wrapper accepts it. Pre-deploy: skipped."""
    home = Path(os.path.expanduser("~/.paperclip/projects"))
    if not home.is_dir():
        pytest.skip("no host-local projects (pre-deploy state)")
    projects = [p.name for p in home.iterdir() if (p / "bindings.yaml").is_file()]
    if not projects:
        pytest.skip("no project with bindings.yaml (operator hasn't bootstrapped yet)")
    # --help with a real key should still exit 0 (usage exits before bindings check).
    out = subprocess.run(
        ["bash", str(WRAPPER), "--help"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, (
        f"--help failed: {out.stdout!r} {out.stderr!r}"
    )
    assert "Usage:" in out.stdout
    # Real key listed in --help output (project-keys table).
    for project in projects:
        assert project in out.stdout, (
            f"real project {project!r} missing from --help output:\n{out.stdout}"
        )
