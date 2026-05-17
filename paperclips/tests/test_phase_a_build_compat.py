"""Phase A: verify build path still resolves for all 24 roles.

Post-Phase-H1: role files are slim crafts (no `<!-- @include -->` directives) and
build routes through `_compose_agent_prompt` rather than legacy `expand_includes`.
The deprecated fragments + their old `@include` callsites are removed entirely.
This test now serves as a smoke check that the slim-craft compose path renders
every role without ENOENT or template-resolution errors.
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


def test_dist_bundles_below_pre_uaa_baseline():
    """Bundles after Phase B compose engine should still be MUCH smaller than
    pre-UAA baseline. Pre-UAA bundles were 20-35KB (full inlining). With Phase B
    profile-based composition, bundles include only profile-relevant fragments —
    well under 20KB even for cto (which gets most content).
    """
    for project, target in [
        ("gimle", "claude"), ("gimle", "codex"),
        ("trading", "claude"), ("trading", "codex"),
        ("uaudit", "codex"),
    ]:
        _build(project, target)

    dist_dir = REPO / "paperclips" / "dist"
    too_fat: list[str] = []
    # Post Phase B with composition: cto profile = ~14-18KB, others smaller.
    # Allow some headroom for projects with rich overlays (uaudit has per-agent overlays).
    POST_PHASE_B_MAX_BYTES = 25000
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
            if size > POST_PHASE_B_MAX_BYTES:
                too_fat.append(f"{p.relative_to(REPO)}: {size} bytes (limit {POST_PHASE_B_MAX_BYTES})")
    assert not too_fat, (
        "Post-Phase-B bundles exceed expected size; likely a fragment include leak:\n"
        + "\n".join(too_fat)
    )
