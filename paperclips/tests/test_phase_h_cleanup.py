"""Phase H1: dead-legacy cleanup — 24 legacy role files + 11 deprecated fragments.

Audit (2026-05-17): zero non-doc references → safe to delete pre-stability-gate.
Phase H2 (active scripts) + H3 (dual-read code paths) remain gated on operator
live deploys + 7-day stability metric per spec §10.1 / §10.5.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


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
