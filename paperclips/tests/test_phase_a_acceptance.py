"""Phase A acceptance: all targets met, ready for Phase B."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUBMODULE = REPO / "paperclips" / "fragments" / "shared" / "fragments"
ROLES = REPO / "paperclips" / "roles"
ROLES_CODEX = REPO / "paperclips" / "roles-codex"

CLAUDE_ROLES = [
    "cto.md", "code-reviewer.md", "python-engineer.md", "mcp-engineer.md",
    "infra-engineer.md", "blockchain-engineer.md", "qa-engineer.md",
    "security-auditor.md", "auditor.md", "research-agent.md",
    "technical-writer.md", "opus-architect-reviewer.md",
]
CODEX_ROLES = [
    "cx-cto.md", "cx-code-reviewer.md", "cx-python-engineer.md", "cx-mcp-engineer.md",
    "cx-infra-engineer.md", "cx-blockchain-engineer.md", "cx-qa-engineer.md",
    "cx-security-auditor.md", "cx-auditor.md", "cx-research-agent.md",
    "cx-technical-writer.md", "codex-architect-reviewer.md",
]

SIZE_LIMIT_PER_ROLE = 100  # lines


def test_all_24_new_roles_are_slim():
    for r in CLAUDE_ROLES + CODEX_ROLES:
        new = (ROLES if r in CLAUDE_ROLES else ROLES_CODEX) / r
        lines = new.read_text().count("\n")
        assert lines <= SIZE_LIMIT_PER_ROLE, f"{new}: {lines} lines (limit {SIZE_LIMIT_PER_ROLE})"


def test_no_new_role_includes_phase_orchestration_directly():
    for r in CLAUDE_ROLES + CODEX_ROLES:
        new = (ROLES if r in CLAUDE_ROLES else ROLES_CODEX) / r
        text = new.read_text()
        assert "Phase 1.1" not in text, f"phase choreography leaked into {new}"
        assert "Phase 4.2" not in text, f"phase choreography leaked into {new}"


def test_no_new_role_has_include_directives():
    """Slim crafts must rely on profile composition, not @include directives."""
    for r in CLAUDE_ROLES + CODEX_ROLES:
        new = (ROLES if r in CLAUDE_ROLES else ROLES_CODEX) / r
        text = new.read_text()
        assert "<!-- @include fragments/" not in text, f"{new} still has @include directive"


def test_fragment_hierarchy_complete():
    expected_dirs = ["universal", "git", "worktree", "handoff", "code-review", "qa", "pre-work", "plan"]
    for d in expected_dirs:
        assert (SUBMODULE / d).is_dir(), f"missing fragment dir: {d}"
        assert any((SUBMODULE / d).glob("*.md")), f"empty fragment dir: {d}"


def test_total_new_fragment_count():
    """Per spec §4.1 (rev3): 3+4+1+2+2+1+3+2 = 18 fragment files across 8 subdirs."""
    new_files: list[Path] = []
    for d in ["universal", "git", "worktree", "handoff", "code-review", "qa", "pre-work", "plan"]:
        new_files.extend((SUBMODULE / d).glob("*.md"))
    assert len(new_files) == 18, (
        f"expected 18 new fragment files, got {len(new_files)}: "
        f"{[f.name for f in new_files]}"
    )
