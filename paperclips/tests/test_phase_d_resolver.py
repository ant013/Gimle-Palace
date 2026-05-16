"""Phase D: dual-read precedence + conflict detection."""
import warnings
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "paperclips" / "tests" / "fixtures" / "phase_d"


def test_legacy_only_returns_legacy_uuids():
    from paperclips.scripts.resolve_bindings import resolve_all
    out = resolve_all(
        legacy_env_path=FIX / "codex-agent-ids.env",
        bindings_yaml_path=None,
    )
    assert out["agents"]["CXCTO"] == "da97dbd9-6627-48d0-b421-66af0750eacf"
    assert out["sources_used"] == ["legacy"]
    assert out["conflicts"] == []


def test_bindings_only_returns_new_uuids():
    from paperclips.scripts.resolve_bindings import resolve_all
    out = resolve_all(
        legacy_env_path=None,
        bindings_yaml_path=FIX / "bindings_only_new.yaml",
    )
    assert out["agents"]["CXCTO"] == "da97dbd9-6627-48d0-b421-66af0750eacf"
    assert out["sources_used"] == ["bindings"]
    assert "CXNewAgent" in out["agents"]


def test_both_matching_no_conflicts():
    from paperclips.scripts.resolve_bindings import resolve_all
    out = resolve_all(
        legacy_env_path=FIX / "codex-agent-ids.env",
        bindings_yaml_path=FIX / "bindings_matching.yaml",
    )
    assert set(out["sources_used"]) == {"legacy", "bindings"}
    assert out["conflicts"] == []


def test_both_conflicting_raises_warning():
    from paperclips.scripts.resolve_bindings import (
        resolve_all,
        BindingsConflictWarning,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = resolve_all(
            legacy_env_path=FIX / "codex-agent-ids.env",
            bindings_yaml_path=FIX / "bindings_conflicting.yaml",
        )
    assert out["agents"]["CXCTO"] == "DIFFERENT-uuid-from-legacy"
    assert len(out["conflicts"]) == 1
    assert out["conflicts"][0]["agent"] == "CXCTO"
    assert out["conflicts"][0]["legacy"] == "da97dbd9-6627-48d0-b421-66af0750eacf"
    assert out["conflicts"][0]["bindings"] == "DIFFERENT-uuid-from-legacy"
    conflict_warnings = [w for w in caught if issubclass(w.category, BindingsConflictWarning)]
    assert len(conflict_warnings) == 1


def test_normalize_legacy_name_to_canonical():
    """env-var → canonical name MUST match watchdog/role_taxonomy.py exactly."""
    from paperclips.scripts.resolve_bindings import _normalize_legacy_name
    assert _normalize_legacy_name("CX_CTO_AGENT_ID") == "CXCTO"
    assert _normalize_legacy_name("CX_QA_ENGINEER_AGENT_ID") == "CXQAEngineer"
    assert _normalize_legacy_name("CX_MCP_ENGINEER_AGENT_ID") == "CXMCPEngineer"
    assert _normalize_legacy_name("CX_PYTHON_ENGINEER_AGENT_ID") == "CXPythonEngineer"
    assert _normalize_legacy_name("CX_CODE_REVIEWER_AGENT_ID") == "CXCodeReviewer"
    assert _normalize_legacy_name("CODEX_ARCHITECT_REVIEWER_AGENT_ID") == "CodexArchitectReviewer"


def test_all_normalized_names_appear_in_role_taxonomy():
    """Smoke: every name produced by normalization is recognized by watchdog taxonomy."""
    import sys
    sys.path.insert(0, str(REPO / "services" / "watchdog" / "src"))
    from gimle_watchdog.role_taxonomy import _ROLE_CLASS_RAW
    from paperclips.scripts.resolve_bindings import _read_legacy_env

    legacy_path = REPO / "paperclips" / "codex-agent-ids.env"
    if not legacy_path.is_file():
        pytest.skip("legacy env file already removed (post Phase H)")
    extracted = _read_legacy_env(legacy_path)
    unknown = [n for n in extracted if n not in _ROLE_CLASS_RAW]
    assert not unknown, (
        f"normalization produces names unknown to watchdog taxonomy: {unknown}\n"
        f"Either fix _normalize_legacy_name() or add entries to "
        f"services/watchdog/src/gimle_watchdog/role_taxonomy.py"
    )


def test_resolve_one_agent_returns_uuid():
    from paperclips.scripts.resolve_bindings import resolve_one
    uuid = resolve_one(
        agent_name="CXCTO",
        legacy_env_path=FIX / "codex-agent-ids.env",
        bindings_yaml_path=FIX / "bindings_matching.yaml",
    )
    assert uuid == "da97dbd9-6627-48d0-b421-66af0750eacf"


def test_resolve_one_missing_returns_none():
    from paperclips.scripts.resolve_bindings import resolve_one
    uuid = resolve_one(
        agent_name="NonexistentAgent",
        legacy_env_path=FIX / "codex-agent-ids.env",
        bindings_yaml_path=FIX / "bindings_matching.yaml",
    )
    assert uuid is None


def test_no_sources_raises():
    from paperclips.scripts.resolve_bindings import resolve_all
    with pytest.raises(FileNotFoundError):
        resolve_all(legacy_env_path=None, bindings_yaml_path=None)


def test_python_and_bash_share_acronym_source():
    """D-fix C-4: resolve_bindings.py + migrate-bindings.sh must agree.

    Both load from paperclips/scripts/lib/canonical_acronyms.txt.
    """
    from paperclips.scripts.resolve_bindings import _PRESERVED_ACRONYMS

    acronym_file = REPO / "paperclips" / "scripts" / "lib" / "canonical_acronyms.txt"
    assert acronym_file.is_file(), "shared acronym file missing"

    file_acronyms = {
        line.strip()
        for line in acronym_file.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert _PRESERVED_ACRONYMS == file_acronyms, (
        "Python _PRESERVED_ACRONYMS drifted from shared lib/canonical_acronyms.txt:\n"
        f"  Python only: {_PRESERVED_ACRONYMS - file_acronyms}\n"
        f"  file only:   {file_acronyms - _PRESERVED_ACRONYMS}"
    )

    # Bash side: read the script and verify it sources the same file.
    bash_script = (REPO / "paperclips" / "scripts" / "migrate-bindings.sh").read_text()
    assert "canonical_acronyms.txt" in bash_script, \
        "migrate-bindings.sh must read shared canonical_acronyms.txt"


def test_cli_rejects_path_traversal_project_key():
    """D-fix IMP-D1: Python CLI must reject ../../etc-style project keys."""
    import subprocess
    out = subprocess.run(
        ["python3", "-m", "paperclips.scripts.resolve_bindings", "../../etc"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "invalid project_key" in (out.stdout + out.stderr).lower()


def test_cli_rejects_uppercase_project_key():
    """D-fix IMP-D1: only lowercase + digit + dash/underscore allowed."""
    import subprocess
    out = subprocess.run(
        ["python3", "-m", "paperclips.scripts.resolve_bindings", "GIMLE"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "invalid project_key" in (out.stdout + out.stderr).lower()


def test_cli_accepts_canonical_project_key():
    """D-fix IMP-D1: lowercase-alphanumeric passes validation."""
    import subprocess
    # gimle is a real project — should at least pass validation (may exit non-zero
    # on missing ~/.paperclip/projects/gimle, but NOT due to validation).
    out = subprocess.run(
        ["python3", "-m", "paperclips.scripts.resolve_bindings", "gimle"],
        cwd=REPO, capture_output=True, text=True,
    )
    combined = out.stdout + out.stderr
    assert "invalid project_key" not in combined.lower(), \
        f"valid key rejected: {combined}"
