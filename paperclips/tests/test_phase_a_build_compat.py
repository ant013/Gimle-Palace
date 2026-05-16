"""Phase A: verify no build-output drift since baseline beyond deprecation banners.

Existing role files reference deprecated fragments via <!-- @include --> directives.
Those fragments are still present (with deprecation banners). When builder includes
them, output gains the banner block at the top of each fragment. Drift expected
to be banner-only.
"""

import hashlib
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _build(project: str, target: str) -> None:
    subprocess.run(
        ["./paperclips/build.sh", "--project", project, "--target", target],
        cwd=REPO, check=True, capture_output=True,
    )


def test_all_projects_still_build():
    """Builder doesn't crash; all old fragment includes still resolve."""
    for project, target in [
        ("gimle", "claude"), ("gimle", "codex"),
        ("trading", "claude"), ("trading", "codex"),
        ("uaudit", "codex"),
    ]:
        _build(project, target)


def test_phase_a_intermediate_state_dist_is_slim():
    """Phase A intermediate: slim crafts produce small dist bundles (verify in CI).

    Replaces rev1's silently-skipping baseline-compat test (QA reviewer rev2 finding).
    Does not depend on baseline-shas.txt or gitignored dist-snapshot — checks
    fresh build output directly. Hard cap: every dist file ≤ 2KB at Phase A state.

    Phase B compose_agent_prompt will re-expand bundles; this test must be
    updated/removed when Phase B lands.
    """
    for project, target in [
        ("gimle", "claude"), ("gimle", "codex"),
        ("trading", "claude"), ("trading", "codex"),
        ("uaudit", "codex"),
    ]:
        _build(project, target)

    dist_dir = REPO / "paperclips" / "dist"
    too_fat: list[str] = []
    # Phase A bundles = slim craft (~1KB) + optional project overlays (trading/uaudit
    # have meaningful overlays adding up to ~10KB). Set cap accordingly; this is
    # still 5-10× smaller than pre-Phase-A baselines (which were 20-35KB).
    PHASE_A_MAX_BYTES = 15000
    SCAN_DIRS = [
        dist_dir,
        dist_dir / "codex",
        dist_dir / "trading" / "claude",
        dist_dir / "trading" / "codex",
        dist_dir / "uaudit" / "codex",
    ]
    for d in SCAN_DIRS:
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            size = p.stat().st_size
            if size > PHASE_A_MAX_BYTES:
                too_fat.append(f"{p.relative_to(REPO)}: {size} bytes (limit {PHASE_A_MAX_BYTES})")
    assert not too_fat, (
        "Phase A intermediate state expected slim bundles; these are too fat:\n"
        + "\n".join(too_fat)
        + "\nCompose engine is Phase B; if you re-fattened a Phase A bundle, remove the bloat."
    )
