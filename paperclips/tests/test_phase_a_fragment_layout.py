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
