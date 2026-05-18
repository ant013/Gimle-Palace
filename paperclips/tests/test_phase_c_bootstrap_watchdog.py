"""Phase C2: bootstrap-watchdog.sh structural validation per spec §9.4."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "bootstrap-watchdog.sh"
TPL = REPO / "paperclips" / "templates"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "watchdog" in out.stdout.lower()


def test_supports_remove_flag():
    assert "--remove" in SCRIPT.read_text()


def test_supports_skip_launchd_flag():
    assert "--skip-launchd" in SCRIPT.read_text()


def test_reads_bindings_for_company_id():
    text = SCRIPT.read_text()
    assert "bindings.yaml" in text
    assert "company_id" in text


def test_loads_templates():
    text = SCRIPT.read_text()
    assert "watchdog-config.yaml.template" in text
    assert "watchdog-company-block.yaml.template" in text


def test_config_template_exists():
    p = TPL / "watchdog-config.yaml.template"
    assert p.is_file()
    text = p.read_text()
    assert "version: 1" in text
    assert "companies: []" in text


def test_company_block_template_exists():
    p = TPL / "watchdog-company-block.yaml.template"
    assert p.is_file()
    text = p.read_text()
    assert "{{ bindings.company_id }}" in text
    assert "{{ project.display_name }}" in text


def test_idempotent_company_block_check():
    """Script must check if company already in config before appending."""
    text = SCRIPT.read_text()
    assert "already in config" in text or "existing=" in text
