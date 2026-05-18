"""Phase C2: smoke-test.sh structural validation."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "smoke-test.sh"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_supports_quick_flag():
    assert "--quick" in SCRIPT.read_text()


def test_supports_canary_stage_flag():
    assert "--canary-stage" in SCRIPT.read_text()


def test_has_7_stages():
    text = SCRIPT.read_text()
    for stage in ["[1/7]", "[2/7]", "[3/7]", "[4/7]", "[5/7]", "[6/7]", "[7/7]"]:
        assert stage in text, f"missing stage marker: {stage}"


def test_uses_smoke_probes_library():
    text = SCRIPT.read_text()
    assert "_smoke_probes.sh" in text
    assert "probe_agent_for_profile" in text
    assert "probe_e2e_handoff" in text


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "smoke" in out.stdout.lower() or "stage" in out.stdout.lower()
