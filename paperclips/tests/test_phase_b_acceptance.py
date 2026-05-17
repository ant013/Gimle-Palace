"""Phase B acceptance: profile system + builder ready for Phase C scripts."""
import hashlib
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROFILES_DIR = REPO / "paperclips" / "fragments" / "profiles"


def test_all_8_profiles_present():
    for n in ["custom", "minimal", "research", "writer", "implementer", "qa", "reviewer", "cto"]:
        assert (PROFILES_DIR / f"{n}.yaml").is_file()


def test_compose_module_importable():
    import sys
    sys.path.insert(0, str(REPO / "paperclips" / "scripts"))
    from compose_agent_prompt import compose  # noqa
    assert callable(compose)


def test_validator_module_importable():
    import sys
    sys.path.insert(0, str(REPO / "paperclips" / "scripts"))
    from validate_manifest import validate_manifest  # noqa
    assert callable(validate_manifest)


def test_resolver_module_importable():
    import sys
    sys.path.insert(0, str(REPO / "paperclips" / "scripts"))
    from resolve_template_sources import resolve  # noqa
    assert callable(resolve)


def test_builder_extended_with_compose_path():
    text = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    assert "from compose_agent_prompt import compose" in text
    assert "_compose_agent_prompt" in text


def test_build_is_deterministic():
    """Same manifest + same fragments → identical SHA across two builds."""
    for project, target in [("trading", "codex"), ("gimle", "codex"), ("uaudit", "codex")]:
        subprocess.run(
            ["./paperclips/build.sh", "--project", project, "--target", target],
            cwd=REPO, check=True, capture_output=True,
        )
        if target == "codex" and project == "gimle":
            out_dir = REPO / "paperclips" / "dist" / "codex"
        elif project == "gimle":
            out_dir = REPO / "paperclips" / "dist"
        else:
            out_dir = REPO / "paperclips" / "dist" / project / target
        if not out_dir.is_dir():
            continue
        shas1 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out_dir.glob("*.md")}
        subprocess.run(
            ["./paperclips/build.sh", "--project", project, "--target", target],
            cwd=REPO, check=True, capture_output=True,
        )
        shas2 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out_dir.glob("*.md")}
        assert shas1 == shas2, f"{project}/{target}: non-deterministic build"


def test_profile_boundaries_at_runtime():
    """After compose, profile boundaries hold: each profile contains only its
    declared capabilities + role craft + universal layer (if inheritsUniversal).
    """
    cases = [
        # (project/dir, file, must_contain, must_not_contain)
        ("dist", "cto.md", ["Karpathy", "Phase 1.1", "Phase 4.2", "release-cut", "APPROVE format"], []),
        ("dist", "code-reviewer.md", ["Karpathy", "APPROVE format", "merge-readiness"], ["release-cut", "Phase 1.1"]),
        ("dist", "python-engineer.md", ["Karpathy", "Git: commit & push", "Worktree discipline"],
         ["Phase 1.1", "release-cut", "APPROVE format"]),
        ("dist", "research-agent.md", ["Karpathy", "codebase-memory first"],
         ["Phase 1.1", "Git: commit & push", "APPROVE format"]),
        ("dist", "technical-writer.md", ["Karpathy", "Handoff basics"],
         ["Phase 1.1", "Git: commit & push", "APPROVE format", "Worktree discipline"]),
        ("dist", "qa-engineer.md", ["Karpathy", "QA: smoke + evidence", "Git: commit & push"], ["release-cut"]),
    ]
    for subdir, fname, must, must_not in cases:
        p = REPO / "paperclips" / subdir / fname
        if not p.is_file():
            pytest.skip(f"{p} missing — build first")
        text = p.read_text()
        for marker in must:
            assert marker in text, f"{p.name} missing required marker {marker!r}"
        for marker in must_not:
            assert marker not in text, f"{p.name} unexpectedly contains forbidden marker {marker!r}"
