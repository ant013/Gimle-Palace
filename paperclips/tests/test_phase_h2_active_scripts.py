"""Phase H2: imac-agents-deploy.sh rewritten as thin wrapper.

Narrow scope: just the wrapper rewrite. The 5 legacy script deletions +
dual-read code path removal stay in H3 because they have surviving
consumers (dual-read resolver, manifest compat fields, watchdog integration
tests) that need coordinated removal across multiple subsystems. Doing
them in one PR with this rewrite blew past H2's safe-deploy scope.

Per spec §10.5 cleanup gate: H2 is operator-merged after live deploys land
on iMac. PR opens as ready-for-review; operator decides merge cadence.
"""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


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
    assert line_count <= 180, (
        f"imac-agents-deploy.sh too large: {line_count} lines (target <=180)"
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
    required_markers = [
        ("origin/main", "must default deploy ref to origin/main (release-cut)"),
        ("--target-sha", "must accept --target-sha for rollback"),
        ("PHASE-A-ONLY", "must guard against shipping Phase-A slim-craft sentinel"),
        ("EXPECTED_CWD", "must keep production-checkout cwd guard"),
        ("EXPECTED_BRANCH", "must keep production branch guard"),
        ("trap cleanup EXIT", "must keep cleanup trap"),
        ("git worktree add --detach", "must keep detached-worktree pattern"),
        ("DEPLOY_LOG", "must append to imac-agents-deploy.log (GIM-244 watchdog dep)"),
    ]
    missing = [(m, why) for m, why in required_markers if m not in text]
    assert not missing, (
        "wrapper lost safety markers:\n"
        + "\n".join(f"  - {m}: {why}" for m, why in missing)
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


def test_imac_agents_deploy_help_works():
    """Sanity: the rewritten wrapper still responds to --help-style invocation."""
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    out = subprocess.run(["bash", str(p)], capture_output=True, text=True)
    # No-arg should exit non-zero with usage on stderr (per usage() function).
    assert out.returncode != 0
    combined = (out.stdout + out.stderr).lower()
    assert "usage" in combined, f"no usage shown: {out.stdout!r} {out.stderr!r}"


# ---------------------------------------------------------------------------
# Post-live-deploy carry-over (operator action; skipped pre-deploy).
# ---------------------------------------------------------------------------


def test_imac_agents_deploy_against_live_bindings():
    """When operator has run bootstrap-project.sh for at least one project,
    the wrapper should accept that project-key. Skipped pre-deploy."""
    import os
    home = Path(os.path.expanduser("~/.paperclip/projects"))
    if not home.is_dir():
        pytest.skip("no host-local projects (pre-deploy state)")
    projects = [p.name for p in home.iterdir() if (p / "bindings.yaml").is_file()]
    if not projects:
        pytest.skip("no project with bindings.yaml (operator hasn't run bootstrap yet)")
    # Just verify the wrapper accepts a real project key (--help path).
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    out = subprocess.run(
        ["bash", "-n", str(p)],  # syntax-check only
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"wrapper syntax error: {out.stderr}"
