"""Phase C2 SM-4: _smoke_probes.sh library smoke (structural — runtime tests
require live paperclip API, deferred to operator-live smoke per spec §12.C)."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "paperclips" / "scripts" / "lib" / "_smoke_probes.sh"


def test_smoke_probes_lib_exists():
    assert LIB.is_file()


def test_defines_probe_functions():
    text = LIB.read_text()
    for fn in ["probe_agent_for_profile", "probe_e2e_handoff", "post_question_wait_reply"]:
        assert f"{fn}()" in text or f"{fn} ()" in text, f"missing function: {fn}"


def test_defines_probe_questions():
    text = LIB.read_text()
    for q in [
        "PROBE_Q_MCP_LIST",
        "PROBE_Q_GIT_CAPABILITY",
        "PROBE_Q_HANDOFF_PROCEDURE",
        "PROBE_Q_PHASE_ORCHESTRATION",
    ]:
        assert q in text, f"missing probe question constant: {q}"


def test_per_profile_expected_markers_defined():
    """Per spec §12.C: each profile family gets specific markers."""
    text = LIB.read_text()
    for profile in ["implementer", "reviewer", "cto", "writer", "research", "qa"]:
        assert f"EXPECTED_GIT_{profile}" in text, f"missing markers for profile: {profile}"


def test_sources_without_error():
    """Library should source cleanly (after sourcing dependencies)."""
    common = REPO / "paperclips" / "scripts" / "lib" / "_common.sh"
    api = REPO / "paperclips" / "scripts" / "lib" / "_paperclip_api.sh"
    out = subprocess.run(
        ["bash", "-c",
         f"export PAPERCLIP_API_URL=stub PAPERCLIP_API_KEY=stub; "
         f"source {common} && source {api} && source {LIB} && echo ok"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
