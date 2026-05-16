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
