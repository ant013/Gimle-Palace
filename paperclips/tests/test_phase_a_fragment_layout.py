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
