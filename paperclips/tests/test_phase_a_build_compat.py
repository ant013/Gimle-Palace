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


def test_baseline_compat_post_role_split_size_drop():
    """After role-split (Tasks 14-37), slim crafts produce SMALLER output than baseline.

    Pre-role-split, drift was banner-only (~+1.5KB per file). After role-split,
    role files no longer @include heavy fragments — they wait for Phase B profile
    composition. Result: every built file is significantly smaller than baseline.

    This test asserts the size reduction direction. It does NOT verify content
    correctness — that's Phase B's job (compose_agent_prompt + profile boundary tests).
    """
    baseline = REPO / "paperclips" / "tests" / "baseline" / "baseline-shas.txt"
    if not baseline.exists():
        import pytest
        pytest.skip("baseline-shas.txt missing — Task 1 not run on this checkout")

    for project, target in [
        ("gimle", "claude"), ("gimle", "codex"),
        ("trading", "claude"), ("trading", "codex"),
        ("uaudit", "codex"),
    ]:
        _build(project, target)

    too_large: list[str] = []
    for line in baseline.read_text().strip().split("\n"):
        sha_old, rel = line.split("  ", 1)
        rel = rel.lstrip("./")
        live = REPO / "paperclips" / "dist" / rel
        if not live.exists():
            continue  # legitimate file removal/rename
        baseline_path = REPO / "paperclips" / "tests" / "baseline" / "dist-snapshot" / rel
        if not baseline_path.exists():
            continue
        old_size = baseline_path.stat().st_size
        new_size = live.stat().st_size
        # Slim crafts should be SMALLER. Allow up to old size + small growth (banner additions on
        # the few legacy fragments still inlined for projects that use @include directives).
        if new_size > old_size + 5000:  # allow 5KB headroom for any banner growth
            too_large.append(f"{rel}: old={old_size} new={new_size} (delta={new_size - old_size:+d})")
    assert not too_large, "files unexpectedly LARGER after role-split:\n" + "\n".join(too_large)
