"""Phase C1: versions.env exists with all required pinned versions per spec §7."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VENV = REPO / "paperclips" / "scripts" / "versions.env"


def test_versions_env_exists():
    assert VENV.is_file()


def test_no_floating_versions():
    """No 'latest', no '9.x', no '*', no branch refs in actual assignments.

    Skip comment lines (start with #) — comments may legitimately mention
    forbidden tokens (e.g., "no 'latest' floating refs").
    """
    text = VENV.read_text()
    forbidden_tokens = ['"latest"', '"9.x"', '"*"']
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        for tok in forbidden_tokens:
            assert tok not in line, f"floating version {tok!r} in line: {line!r}"


def test_required_keys_present():
    text = VENV.read_text()
    required = [
        "PAPERCLIPAI_VERSION",
        "TELEGRAM_PLUGIN_REPO",
        "TELEGRAM_PLUGIN_REF",
        "TELEGRAM_PLUGIN_BUILD_CMD",
        "PNPM_PROVIDER",
        "PNPM_VERSION",
        "WATCHDOG_PATH",
        "CODEBASE_MEMORY_MCP_VERSION",
        "SERENA_VERSION",
        "CONTEXT7_MCP_VERSION",
        "SEQUENTIAL_THINKING_MCP_VERSION",
    ]
    for key in required:
        assert key in text, f"missing key: {key}"


def test_paperclipai_version_is_pre_5429():
    """Pinned version must NOT include PR #5429 (broke plugin secret-refs).

    Per spec §7: 2026.508.0-canary.0 is the latest valid version
    (published 2026-05-08T00:21Z, before #5429 on 2026-05-09).
    """
    text = VENV.read_text()
    import re
    m = re.search(r'PAPERCLIPAI_VERSION="([^"]+)"', text)
    assert m, "PAPERCLIPAI_VERSION not in correct format"
    v = m.group(1)
    allowed = ["2026.508.0-canary.0", "2026.507.0-canary.4"]
    assert v in allowed, f"PAPERCLIPAI_VERSION {v!r} not in allowed list {allowed}"


def test_pnpm_version_pinned_exact():
    text = VENV.read_text()
    import re
    m = re.search(r'PNPM_VERSION="([^"]+)"', text)
    assert m, "PNPM_VERSION missing"
    v = m.group(1)
    # Should be exact pinned version (e.g. "9.15.0"), not "9.x"
    assert re.match(r"^\d+\.\d+\.\d+$", v), f"PNPM_VERSION must be exact semver, got {v!r}"


def test_telegram_plugin_pinned_by_sha():
    text = VENV.read_text()
    import re
    m = re.search(r'TELEGRAM_PLUGIN_REF="([^"]+)"', text)
    assert m
    ref = m.group(1)
    # Should be 7-40 hex chars (SHA), not branch name like "main" or "HEAD"
    assert re.match(r"^[0-9a-f]{7,40}$", ref), \
        f"TELEGRAM_PLUGIN_REF must be SHA, got {ref!r}"
