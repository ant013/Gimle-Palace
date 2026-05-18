"""Phase H1 (CLAUDE.md decompose): root CLAUDE.md is a thin index, content
extracted into focused docs.

Per Phase G plan Task 5: root CLAUDE.md becomes ≤30-line pointer; sections
moved to docs/contributing/, docs/palace-mcp/, services/palace-mcp/README.md.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_root_claude_md_is_slim_pointer():
    """Pre-decompose CLAUDE.md was 719 lines. Post-decompose should be ≤40."""
    p = REPO / "CLAUDE.md"
    assert p.is_file(), "CLAUDE.md must remain at repo root"
    lines = p.read_text().splitlines()
    assert len(lines) <= 40, (
        f"CLAUDE.md not slim: {len(lines)} lines (post-decompose target ≤40)"
    )


def test_extracted_docs_exist():
    """Each destination file from Phase G plan Task 5 must exist."""
    expected = [
        "docs/contributing/branch-flow.md",
        "docs/contributing/docs-layout.md",
        "docs/contributing/paperclip-team-workflow.md",
        "docs/palace-mcp/extractors.md",
    ]
    missing = [f for f in expected if not (REPO / f).is_file()]
    assert not missing, f"decompose destination files missing: {missing}"


def test_palace_mcp_readme_carries_deploy_section():
    p = REPO / "services" / "palace-mcp" / "README.md"
    text = p.read_text()
    assert "Production deploy on iMac" in text, (
        "palace-mcp README missing extracted 'Production deploy on iMac' section"
    )
    assert "Docker Compose Profiles" in text
    assert "Mounting project repos" in text


def test_root_claude_md_points_to_all_extracted_docs():
    """The thin pointer must reference each extracted file so readers can
    navigate from the root.
    """
    text = (REPO / "CLAUDE.md").read_text()
    must_reference = [
        "docs/contributing/branch-flow.md",
        "docs/contributing/docs-layout.md",
        "docs/contributing/paperclip-team-workflow.md",
        "docs/palace-mcp/extractors.md",
        "services/palace-mcp/README.md",
    ]
    missing = [r for r in must_reference if r not in text]
    assert not missing, f"CLAUDE.md missing pointers to: {missing}"


def test_root_claude_md_no_legacy_fragment_refs():
    """Decomposed CLAUDE.md must not cite any of the 11 H1-deleted fragments."""
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
    text = (REPO / "CLAUDE.md").read_text()
    leaks = [d for d in deprecated if re.search(rf"\b{re.escape(d)}\b", text)]
    assert not leaks, f"CLAUDE.md still references deleted fragments: {leaks}"
