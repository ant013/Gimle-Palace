"""Phase H1: dead-legacy cleanup — 24 legacy role files + 11 deprecated fragments
+ 7 vendored copies (4 codex per-target + 3 trading per-project).

Audit (2026-05-17, after architect+code-rev+qa deep-review): zero
non-doc/non-test references across (a) upstream submodule, (b) per-target
vendored copies, (c) per-project vendored copies, (d) committed dist, (e)
CLAUDE.md, (f) inventory artifacts. Tests below pin all 6 surfaces so a
partial rollback can't silently re-introduce the deprecated names.

Phase H2 (active scripts: imac-agents-deploy.sh rewrite + 5 legacy scripts +
templates/* legacy expand_includes path) + H3 (dual-read code paths) remain
gated on operator live deploys + 7-day stability metric per spec §10.1 / §10.5.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

DEPRECATED_NAMES = [
    "karpathy-discipline.md",
    "heartbeat-discipline.md",
    "phase-handoff.md",
    "git-workflow.md",
    "worktree-discipline.md",
    "escalation-blocked.md",
    "compliance-enforcement.md",
    "test-design-discipline.md",
    "pre-work-discovery.md",
    "plan-first-producer.md",
    "plan-first-review.md",
]

# Lower-bound submodule pointer: bump this when Phase H2/H3 land further submodule changes.
POST_H1_SUBMODULE_SHA = "0a06922"


def test_legacy_role_dirs_removed():
    """Phase H1: roles/legacy/ + roles-codex/legacy/ are now dead — verified via
    `git grep -l roles/legacy paperclips/` returning zero non-doc consumers."""
    for d in ["paperclips/roles/legacy", "paperclips/roles-codex/legacy"]:
        p = REPO / d
        assert not p.is_dir(), f"legacy dir still present: {d}"


def test_deprecated_shared_fragments_removed():
    """Phase H1: 11 deprecated fragments in paperclip-shared-fragments submodule.
    Replaced by new Phase-A fragment layout under fragments/{universal,handoff,...}."""
    submodule = REPO / "paperclips" / "fragments" / "shared" / "fragments"
    deprecated = [
        "karpathy-discipline.md",
        "heartbeat-discipline.md",
        "phase-handoff.md",
        "git-workflow.md",
        "worktree-discipline.md",
        "escalation-blocked.md",
        "compliance-enforcement.md",
        "test-design-discipline.md",
        "pre-work-discovery.md",
        "plan-first-producer.md",
        "plan-first-review.md",
    ]
    still_present = [d for d in deprecated if (submodule / d).is_file()]
    assert not still_present, f"deprecated fragments not yet removed: {still_present}"


def test_kept_fragments_still_present():
    """Negative-coverage anchor: ensure we didn't accidentally over-delete."""
    submodule = REPO / "paperclips" / "fragments" / "shared" / "fragments"
    kept = ["cto-no-code-ban.md", "language.md"]
    for k in kept:
        assert (submodule / k).is_file(), f"kept fragment accidentally removed: {k}"


# --- Per voltAgent QA CRIT-3: no unexpected root files in submodule fragments/ ---


def test_no_unexpected_files_at_fragment_root():
    """Submodule fragments/ root must hold only the explicitly-kept set.
    A new file at root (where the 11 deleted ones lived) is a smell — either
    accidental restoration during merge OR a new deprecation that should live
    under a subdir per Phase A hierarchy. Catches both."""
    submodule = REPO / "paperclips" / "fragments" / "shared" / "fragments"
    root_md = {p.name for p in submodule.glob("*.md")}
    expected = {
        "cto-no-code-ban.md",
        "language.md",
        "phase-review-discipline.md",
        "async-signal-wait.md",
        "fragment-density.md",
    }
    unexpected = root_md - expected
    assert not unexpected, f"unexpected files at fragment root: {unexpected}"


# --- Per voltAgent QA CRIT-1: submodule SHA lower-bound (rollback detection) ---


def test_shared_fragments_submodule_at_or_after_post_h1_sha():
    """Guard against accidental submodule pointer rollback. Pins lower bound;
    H2/H3 will bump POST_H1_SUBMODULE_SHA forward as further submodule changes land."""
    submodule_dir = REPO / "paperclips" / "fragments" / "shared"
    current = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=submodule_dir,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", POST_H1_SUBMODULE_SHA, current],
        cwd=submodule_dir, capture_output=True,
    )
    assert ancestor.returncode == 0, (
        f"submodule pointer {current[:7]} is NOT a descendant of "
        f"{POST_H1_SUBMODULE_SHA}. Possible accidental rollback. "
        f"If H2/H3 intentionally bumped, update POST_H1_SUBMODULE_SHA in this file."
    )


# --- Per voltAgent code-rev IMP-1 + architect CRIT-1/2/3/4: full-repo grep guard ---


def test_no_surviving_reference_to_deleted_fragments():
    """Strongest guard: for every deprecated fragment name, no non-doc/non-test
    consumer in the repo references it. Catches:
    - per-target vendored copies (paperclips/fragments/targets/codex/shared/fragments/)
    - per-project vendored copies (paperclips/projects/<key>/fragments/shared/fragments/)
    - committed dist text (paperclips/dist/**)
    - CLAUDE.md and other operator-facing docs (excluding /docs/)
    - inventory artifacts (paperclips/*.json)

    Architect+code-rev+qa CRITICAL: H1's "dead-only" claim must be honest.
    Without this test, the 3 narrow file-absence checks above pass but the
    fragments are still referenced everywhere else."""
    for frag in DEPRECATED_NAMES:
        # Path-aware: match `fragments/<name>` form (the deleted location) but
        # not orthogonal files that share the name (e.g., `lessons/phase-handoff.md`
        # is a separate surviving file in super-repo, intentionally kept).
        pattern = f"fragments/{frag}"
        out = subprocess.run(
            ["git", "grep", "-l", pattern, "--",
             ":!docs/",
             ":!paperclips/tests/test_phase_h_cleanup.py",
             # Frozen pre-migration baselines — INTENTIONALLY contain old text
             # to pin render-delta determinism across Phase E/F/G renames.
             ":!paperclips/tests/baseline",
             # test_phase_a_fragment_layout.py EXPECTED_HIERARCHY enumerates the
             # post-Phase-A submodule layout; it lists deprecated names only as
             # part of historical context comments (no live consumer).
             ":!paperclips/tests/test_phase_a_fragment_layout.py",
             # bundle_breakdown + bundle-size-breakdown carry stale legacy names
             # until H2 — the script depends on the legacy expand_includes path
             # which slim crafts bypass; both will be reworked in H2.
             ":!paperclips/scripts/bundle_breakdown.py",
             ":!paperclips/bundle-size-breakdown.json",
             # Legacy `templates/*` in submodule is dead expand_includes path
             # (deleted in H2 along with the legacy code path).
             ":!paperclips/fragments/shared/templates",
             # paperclip_shared_fragments tracks its own deletion history in commit messages
             ":!paperclips/fragments/shared/.git",
            ],
            cwd=REPO, capture_output=True, text=True,
        )
        refs = [ln for ln in out.stdout.strip().splitlines() if ln]
        assert not refs, f"deleted fragment {frag!r} still referenced by: {refs}"
# CI re-trigger marker (tree-hash dedupe workaround)
