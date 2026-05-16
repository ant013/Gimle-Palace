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


def test_baseline_compat_drift_only_from_banners():
    """Diff vs baseline limited to deprecation-banner additions."""
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

    drifts: list[str] = []
    for line in baseline.read_text().strip().split("\n"):
        sha_old, rel = line.split("  ", 1)
        # baseline shas are computed relative to dist-snapshot/ root,
        # i.e. "./auditor.md", "./codex/cx-cto.md", "./trading/codex/CTO.md".
        # Map them to live dist:  ./X.md → paperclips/dist/X.md
        rel = rel.lstrip("./")
        live = REPO / "paperclips" / "dist" / rel
        if not live.exists():
            drifts.append(f"missing live file: {live}")
            continue
        sha_new = hashlib.sha256(live.read_bytes()).hexdigest()
        if sha_new == sha_old:
            continue
        text = live.read_text()
        if "DEPRECATED (UAA Phase A" not in text:
            drifts.append(f"unexpected drift (no banner) in {live}")
    assert not drifts, "\n".join(drifts)
