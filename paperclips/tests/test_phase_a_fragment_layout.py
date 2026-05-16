"""Phase A: verify new fragment hierarchy exists with expected content."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUBMODULE = REPO / "paperclips" / "fragments" / "shared" / "fragments"


def test_universal_karpathy_exists():
    p = SUBMODULE / "universal" / "karpathy.md"
    assert p.is_file(), f"missing {p}"
    text = p.read_text()
    assert "Think before" in text or "Think Before" in text
    assert "Minimum" in text or "minimum" in text
    assert "Surgical" in text or "surgical" in text
    assert "Goal" in text or "goal" in text


def test_universal_wake_and_handoff_exists():
    p = SUBMODULE / "universal" / "wake-and-handoff-basics.md"
    assert p.is_file()
    text = p.read_text()
    # Wake-discipline checks (was in heartbeat-discipline.md)
    assert "PAPERCLIP_TASK_ID" in text
    assert "/api/agents/me" in text
    assert "Cross-session memory" in text or "cross-session memory" in text
    # Handoff basics (was in phase-handoff.md)
    assert "@mention" in text or "@-mention" in text
    assert "trailing space" in text
    assert "409" in text
    # Heartbeat content removed (paperclip heartbeat is OFF)
    assert "intervalSec" not in text


def test_universal_escalation_exists():
    p = SUBMODULE / "universal" / "escalation-board.md"
    assert p.is_file()
    text = p.read_text()
    assert "@Board" in text
    assert "blocker" in text.lower()


def test_git_commit_and_push_exists():
    p = SUBMODULE / "git" / "commit-and-push.md"
    assert p.is_file()
    text = p.read_text()
    assert "fresh-fetch" in text or "git fetch" in text
    assert "force-with-lease" in text
    assert "release-cut" not in text.lower()
    assert "mergeStateStatus" not in text


def test_git_merge_readiness_exists():
    p = SUBMODULE / "git" / "merge-readiness.md"
    assert p.is_file()
    text = p.read_text()
    assert "merge-readiness" in text.lower() or "merge readiness" in text.lower()
    assert "release-cut" not in text.lower()


def test_git_merge_state_decoder_exists():
    p = SUBMODULE / "git" / "merge-state-decoder.md"
    assert p.is_file()
    text = p.read_text()
    for code in ["CLEAN", "DIRTY", "BEHIND", "BLOCKED"]:
        assert code in text, f"missing mergeStateStatus code {code}"


def test_git_release_cut_exists():
    p = SUBMODULE / "git" / "release-cut.md"
    assert p.is_file()
    text = p.read_text()
    assert "release-cut" in text.lower()
    assert "release-cut.yml" in text or "develop → main" in text


def test_worktree_active_exists():
    p = SUBMODULE / "worktree" / "active.md"
    assert p.is_file()
    text = p.read_text()
    assert "worktree" in text.lower()


def test_handoff_basics_exists():
    p = SUBMODULE / "handoff" / "basics.md"
    assert p.is_file()
    text = p.read_text()
    assert "PATCH" in text
    assert "@" in text
    assert "Phase 1.1" not in text


def test_handoff_phase_orchestration_exists():
    p = SUBMODULE / "handoff" / "phase-orchestration.md"
    assert p.is_file()
    text = p.read_text()
    for phase in ["1.1", "1.2", "2", "3.1", "3.2", "4.1", "4.2"]:
        assert phase in text, f"missing phase {phase}"
    assert "CodeReviewer" in text


def test_code_review_approve_exists():
    p = SUBMODULE / "code-review" / "approve.md"
    assert p.is_file()
    text = p.read_text()
    assert "APPROVE" in text
    assert "gh pr checks" in text


def test_code_review_adversarial_exists():
    p = SUBMODULE / "code-review" / "adversarial.md"
    assert p.is_file()
    text = p.read_text()
    assert "adversarial" in text.lower() or "attack" in text.lower()


def test_qa_smoke_and_evidence_exists():
    p = SUBMODULE / "qa" / "smoke-and-evidence.md"
    assert p.is_file()
    text = p.read_text()
    assert "QA Evidence" in text or "qa evidence" in text.lower()
    assert "smoke" in text.lower()


def test_prework_codebase_memory_first_exists():
    p = SUBMODULE / "pre-work" / "codebase-memory-first.md"
    assert p.is_file()
    text = p.read_text()
    assert "search_graph" in text or "codebase-memory" in text


def test_prework_sequential_thinking_exists():
    p = SUBMODULE / "pre-work" / "sequential-thinking.md"
    assert p.is_file()
    text = p.read_text()
    assert "sequential-thinking" in text or "sequential_thinking" in text


def test_prework_existing_field_semantics_exists():
    p = SUBMODULE / "pre-work" / "existing-field-semantics.md"
    assert p.is_file()
    text = p.read_text()
    assert "rename" in text.lower() or "field" in text.lower()


def test_plan_producer_exists():
    p = SUBMODULE / "plan" / "producer.md"
    assert p.is_file()


def test_plan_review_exists():
    p = SUBMODULE / "plan" / "review.md"
    assert p.is_file()


EXPECTED_HIERARCHY = {
    "universal": {"karpathy.md", "wake-and-handoff-basics.md", "escalation-board.md"},
    "git": {"commit-and-push.md", "merge-readiness.md", "merge-state-decoder.md", "release-cut.md"},
    "worktree": {"active.md"},
    "handoff": {"basics.md", "phase-orchestration.md"},
    "code-review": {"approve.md", "adversarial.md"},
    "qa": {"smoke-and-evidence.md"},
    "pre-work": {"codebase-memory-first.md", "sequential-thinking.md", "existing-field-semantics.md"},
    "plan": {"producer.md", "review.md"},
}


def test_hierarchy_complete():
    for subdir, expected_files in EXPECTED_HIERARCHY.items():
        actual = {p.name for p in (SUBMODULE / subdir).glob("*.md")}
        missing = expected_files - actual
        assert not missing, f"{subdir}/ missing: {missing}"


def test_no_orphan_files_in_subdirs():
    for subdir, expected_files in EXPECTED_HIERARCHY.items():
        actual = {p.name for p in (SUBMODULE / subdir).glob("*.md")}
        unexpected = actual - expected_files
        assert not unexpected, f"{subdir}/ has unexpected: {unexpected}"


def test_deprecated_files_have_banner():
    deprecated = [
        "karpathy-discipline.md", "heartbeat-discipline.md", "escalation-blocked.md",
        "git-workflow.md", "worktree-discipline.md", "phase-handoff.md",
        "compliance-enforcement.md", "test-design-discipline.md", "pre-work-discovery.md",
        "plan-first-producer.md", "plan-first-review.md",
    ]
    for fname in deprecated:
        p = SUBMODULE / fname
        text = p.read_text()
        assert "DEPRECATED" in text, f"{fname} missing deprecation banner"
        assert "UAA Phase A" in text, f"{fname} banner doesn't reference UAA Phase A"


def test_unchanged_files_preserved():
    """cto-no-code-ban.md and language.md stay as-is in Phase A."""
    for fname in ["cto-no-code-ban.md", "language.md"]:
        p = SUBMODULE / fname
        assert p.is_file()
        text = p.read_text()
        assert "DEPRECATED" not in text, f"{fname} should NOT be deprecated"


# rev2 QA fix: subdir enumeration guard.
EXPECTED_FRAGMENT_SUBDIRS = {
    "universal", "git", "worktree", "handoff", "code-review", "qa", "pre-work", "plan",
}
# Known pre-existing subdir not in UAA Phase A spec (kept for legacy back-compat).
KNOWN_OTHER_SUBDIRS = {"role-prime"}


def test_no_unexpected_subdirs():
    """Catch any new subdir in fragments/ that isn't accounted for in Phase A or as legacy."""
    actual = {p.name for p in SUBMODULE.iterdir() if p.is_dir()}
    unexpected = actual - EXPECTED_FRAGMENT_SUBDIRS - KNOWN_OTHER_SUBDIRS
    assert not unexpected, f"unexpected subdirs in fragments/: {unexpected}"


# rev2 QA fix: content-correctness tests for fragments that previously only had keyword-existence.
def test_plan_producer_has_real_content():
    """plan/producer.md must contain plan-first discipline rule, not just exist."""
    p = SUBMODULE / "plan" / "producer.md"
    text = p.read_text()
    assert len(text) > 200, f"plan/producer.md too short: {len(text)} chars"
    assert "plan" in text.lower()


def test_plan_review_has_real_content():
    p = SUBMODULE / "plan" / "review.md"
    text = p.read_text()
    assert len(text) > 100, f"plan/review.md too short: {len(text)} chars"


def test_worktree_active_has_substantive_rules():
    """Verify worktree/active.md has rules beyond just the heading."""
    p = SUBMODULE / "worktree" / "active.md"
    text = p.read_text()
    # At least 2 of 3 substantive rules must be present
    rule_markers = [
        "team-isolated" in text.lower() or "team isolated" in text.lower() or "isolated worktree" in text.lower(),
        "cross-branch" in text.lower() or "switching branch" in text.lower(),
        "production checkout" in text.lower() or "production_checkout" in text,
    ]
    assert sum(rule_markers) >= 2, f"worktree/active.md missing substantive rules; only {sum(rule_markers)}/3 markers found"


def test_git_merge_readiness_has_checklist():
    """Verify git/merge-readiness.md has actual checklist items, not just heading."""
    p = SUBMODULE / "git" / "merge-readiness.md"
    text = p.read_text()
    # Should have CI/approval/conflict checks as numbered or bulleted list
    checks = [
        "CI green" in text or "gh pr checks" in text,
        "approved" in text.lower() or "APPROVED" in text,
        "conflict" in text.lower(),
    ]
    assert sum(checks) >= 2, f"git/merge-readiness.md missing checklist; only {sum(checks)}/3 found"


# rev2 QA fix: section-structure test for all 24 slim crafts.
def test_all_slim_crafts_have_canonical_sections():
    """Each slim craft must have Role, Area, MCP, Anti-patterns sections (spec §10.1.1)."""
    REPO = Path(__file__).resolve().parents[2]
    REQUIRED_SECTIONS = ["## Role", "## Area of responsibility", "## MCP / Tool scope", "## Anti-patterns"]
    failures = []
    for sub in ["roles", "roles-codex"]:
        for p in (REPO / "paperclips" / sub).glob("*.md"):
            text = p.read_text()
            for sec in REQUIRED_SECTIONS:
                if sec not in text:
                    failures.append(f"{p.relative_to(REPO)}: missing section {sec!r}")
    assert not failures, "\n".join(failures)


def test_all_slim_crafts_have_phase_a_sentinel():
    """Per rev2 Group 2: every slim craft has PHASE-A-ONLY sentinel for deploy guard."""
    REPO = Path(__file__).resolve().parents[2]
    failures = []
    for sub in ["roles", "roles-codex"]:
        for p in (REPO / "paperclips" / sub).glob("*.md"):
            text = p.read_text()
            if "PHASE-A-ONLY" not in text:
                failures.append(f"{p.relative_to(REPO)}: missing PHASE-A-ONLY sentinel")
    assert not failures, "\n".join(failures)
