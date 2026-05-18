"""Phase B: compose_agent_prompt produces correctly-ordered AGENTS.md."""
import io
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUBMODULE_FRAGMENTS = REPO / "paperclips" / "fragments" / "shared" / "fragments"
PROFILES_DIR = REPO / "paperclips" / "fragments" / "profiles"


def test_minimal_profile_emits_universal_only():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="minimal",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Test Role\nbody",
        custom_includes=[],
        overlay_blocks=[],
    )
    assert "Karpathy discipline" in out
    assert "Wake & handoff basics" in out
    assert "@Board" in out
    assert "# Test Role" in out
    assert out.index("Karpathy discipline") < out.index("# Test Role")


def test_implementer_includes_git_and_worktree():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="implementer",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Python Engineer\nbody",
        custom_includes=[],
        overlay_blocks=[],
    )
    assert "Git: commit & push" in out
    assert "Worktree discipline" in out
    assert "Karpathy discipline" in out
    u_idx = out.index("Karpathy discipline")
    g_idx = out.index("Git: commit & push")
    r_idx = out.index("# Python Engineer")
    assert u_idx < g_idx < r_idx


def test_qa_extends_implementer():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="qa",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# QA",
        custom_includes=[],
        overlay_blocks=[],
    )
    assert "Git: commit & push" in out  # from implementer
    assert "QA: smoke + evidence" in out  # from qa.yaml
    # Universal appears EXACTLY ONCE despite both profiles claiming inheritsUniversal: true
    assert out.count("Karpathy discipline") == 1


def test_custom_profile_skips_universal():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="custom",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Custom",
        custom_includes=[],
        overlay_blocks=[],
    )
    assert "Karpathy discipline" not in out
    assert "@Board" not in out
    assert "# Custom" in out


def test_custom_includes_appended_after_profile():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="reviewer",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Opus",
        custom_includes=["code-review/adversarial.md"],
        overlay_blocks=[],
    )
    assert "Code review: adversarial review" in out
    assert "Code review: APPROVE format" in out


def test_overlay_blocks_appended_last():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="minimal",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Role",
        custom_includes=[],
        overlay_blocks=["## Project anti-pattern\nNever push directly."],
    )
    overlay_idx = out.index("Project anti-pattern")
    role_idx = out.index("# Role")
    assert role_idx < overlay_idx, "overlay must come AFTER role"


def test_cto_includes_release_cut_and_phase_orchestration():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="cto",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# CTO",
        custom_includes=[],
        overlay_blocks=[],
    )
    # CTO extends reviewer → must have approve.md
    assert "Code review: APPROVE format" in out
    # CTO own additions
    assert "Git: release-cut procedure" in out
    assert "Phase orchestration" in out


def test_implementer_does_NOT_have_phase_orchestration_or_release_cut():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="implementer",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Engineer",
        custom_includes=[],
        overlay_blocks=[],
    )
    assert "Phase orchestration" not in out
    assert "Git: release-cut" not in out
    assert "Code review: APPROVE" not in out


def test_writer_minimal_capabilities():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="writer",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Writer",
        custom_includes=[],
        overlay_blocks=[],
    )
    # Writer has universal + handoff/basics only
    assert "Karpathy discipline" in out
    assert "Handoff basics" in out
    # NOT git/worktree/code-review
    assert "Git: commit" not in out
    assert "Worktree discipline" not in out
    assert "APPROVE format" not in out
