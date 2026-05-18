"""Phase D acceptance: dual-read seam ready for migrations (E/F/G)."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_resolver_module_exists():
    assert (REPO / "paperclips" / "scripts" / "resolve_bindings.py").is_file()


def test_resolver_exports_required_api():
    from paperclips.scripts.resolve_bindings import (
        BindingsConflictWarning,
        resolve_all,
        resolve_one,
    )
    assert callable(resolve_all)
    assert callable(resolve_one)
    # Sanity: warning class subclasses UserWarning so warnings.catch_warnings
    # captures it without simplefilter("error").
    assert issubclass(BindingsConflictWarning, UserWarning)


def test_builder_calls_resolver():
    text = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    assert "resolve_bindings" in text, \
        "builder must import/reference resolve_bindings"


def test_watchdog_load_team_uuids_calls_resolver():
    """load_team_uuids in validate_instructions (called by detection_semantic) uses resolver."""
    text = (REPO / "paperclips" / "scripts" / "validate_instructions.py").read_text()
    assert "resolve_bindings" in text or "resolve_all" in text


def test_legacy_files_still_present():
    """Legacy sources MUST remain in repo until cleanup gate (§10.5)."""
    assert (REPO / "paperclips" / "codex-agent-ids.env").is_file(), \
        "legacy file removed prematurely; cleanup happens in Phase H"


def test_no_direct_legacy_reads_in_builder():
    """Builder MUST go through resolver — no read_text/open on codex-agent-ids.env."""
    builder = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    bad = re.findall(r"(open|read_text|Path)\([^)]*codex-agent-ids\.env", builder)
    assert not bad, f"builder bypasses resolver: {bad}"


def test_migrate_bindings_has_check_conflicts():
    text = (REPO / "paperclips" / "scripts" / "migrate-bindings.sh").read_text()
    assert "--check-conflicts" in text and "CHECK_CONFLICTS" in text


def test_phase_d_test_files_exist():
    """Every Phase D fix has its own test file (TDD discipline)."""
    tests = REPO / "paperclips" / "tests"
    required = [
        "test_phase_d_resolver.py",
        "test_phase_d_integration.py",
        "test_phase_d_migrate_conflict.py",
        "test_phase_d_acceptance.py",
    ]
    missing = [f for f in required if not (tests / f).is_file()]
    assert not missing, f"missing Phase D test files: {missing}"
