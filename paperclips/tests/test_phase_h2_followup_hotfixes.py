"""Phase H2 followup: 3 hot-fixes discovered during live deploy on iMac 2026-05-17.

Live trading+uaudit+gimle deploys exposed bugs that pre-deploy tests missed:

1. paperclip_get_agent_instructions GET endpoint must include `?path=AGENTS.md`
   query (API returns 422 "Query parameter 'path' is required" without it).
2. validate_agent_name regex rejected kebab agent_names; Phase G gimle uses
   kebab (cto, cx-cto). Allow `-` (yq bracket-syntax protects path safety).
3. bootstrap-project.sh hardcoded dist path `paperclips/dist/<project>/<target>/<name>.md`
   while gimle uses `legacy_output_paths: true` → `paperclips/dist/<name>.md`.
   Honor manifest's per-agent `output_path` field.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_get_agent_instructions_includes_path_query():
    """API requires ?path=AGENTS.md query on GET. Without it, returns 422."""
    p = REPO / "paperclips" / "scripts" / "lib" / "_paperclip_api.sh"
    text = p.read_text()
    # The GET endpoint line must end with `?path=AGENTS.md"` (still curl call).
    assert re.search(
        r'instructions-bundle/file\?path=AGENTS\.md"',
        text,
    ), "GET endpoint missing ?path=AGENTS.md query (API returns 422 without it)"


def test_validate_agent_name_allows_kebab():
    """Phase G gimle manifest uses kebab agent_names (cto, cx-cto). Regex must allow `-`.

    Architect H2-followup IMPORTANT-1: behavioral test via actual bash subprocess
    instead of brittle source-string regex — catches future drift in the source
    regex too.
    """
    import subprocess
    p = REPO / "paperclips" / "scripts" / "lib" / "_common.sh"

    def check(name):
        """Returns 0 if name passes validate_agent_name, non-zero if rejected."""
        out = subprocess.run(
            ["bash", "-c", f"source {p}; validate_agent_name '{name}'"],
            capture_output=True, text=True,
        )
        return out.returncode

    # MUST accept:
    for good in ("cto", "cx-cto", "code-reviewer", "opus-architect-reviewer", "CTO", "Agent1"):
        assert check(good) == 0, f"valid agent_name {good!r} was rejected"
    # MUST reject:
    for bad in ("1bad", "bad/x", "-leading-dash", "bad name", "cto;rm", 'cto"x'):
        assert check(bad) != 0, f"invalid agent_name {bad!r} was accepted (security risk)"


def test_bootstrap_uses_bracket_syntax_for_yq_paths():
    """Kebab agent_names with `-` would be interpreted as subtraction in
    yq dot-paths. Must use bracket syntax: .agents["${agent_name}"]."""
    p = REPO / "paperclips" / "scripts" / "bootstrap-project.sh"
    text = p.read_text()
    # No dot-path with agent_name interpolation should remain.
    bad = re.findall(r'\.agents\.\$\{agent_name\}', text)
    assert not bad, (
        f"bootstrap-project.sh still uses dot-path .agents.${{agent_name}} "
        f"({len(bad)} occurrences) — must use .agents[\"${{agent_name}}\"]"
    )
    # Bracket-syntax must appear.
    good = re.findall(r'\.agents\[\\?"?\$\{agent_name\}\\?"?\]', text)
    assert len(good) >= 2, (
        f"bootstrap-project.sh should use bracket-syntax .agents[\"${{agent_name}}\"] "
        f"at least twice (hire-lookup + bindings-write); found {len(good)}"
    )


def test_bootstrap_honors_manifest_output_path():
    """Phase G gimle keeps `legacy_output_paths: true` → dist writes to
    `paperclips/dist/<name>.md` (no project/target prefix). bootstrap-project.sh
    must read manifest's per-agent `output_path` to find the file.

    Architect H2-followup IMPORTANT-2: assert ≥2 callsites (deploy_one +
    workspace-copy) to catch partial revert.
    """
    p = REPO / "paperclips" / "scripts" / "bootstrap-project.sh"
    text = p.read_text()
    callsites = re.findall(r'\.output_path //', text)
    assert len(callsites) >= 2, (
        f"bootstrap-project.sh must consult manifest's `output_path` field "
        f"at BOTH deploy_one + workspace-copy steps (found {len(callsites)} of 2)"
    )


def test_phase_g_gimle_manifest_has_output_path_per_agent():
    """Sanity: the test above relies on gimle manifest having per-agent
    output_path. Verify."""
    import yaml
    p = REPO / "paperclips" / "projects" / "gimle" / "paperclip-agent-assembly.yaml"
    data = yaml.safe_load(p.read_text())
    missing = [a["agent_name"] for a in data["agents"] if "output_path" not in a]
    assert not missing, (
        f"gimle manifest agents missing `output_path`: {missing} "
        f"(bootstrap-project.sh deploy/workspace steps would fall back to canonical path)"
    )


# ---------------------------------------------------------------------------
# Security H2-followup CRIT-3: negative tests (must reject malicious input).
# ---------------------------------------------------------------------------


def test_validate_safe_repo_path_rejects_traversal_and_absolute():
    """Security H2-followup CRIT-2: validate_safe_repo_path must reject:
    - absolute paths (/etc/passwd)
    - .. traversal (../../../etc/shadow)
    - shell-special chars
    - empty
    Without this, manifest `output_path: /etc/passwd` could exfiltrate
    arbitrary files via the AGENTS.md PUT API.
    """
    import subprocess
    p = REPO / "paperclips" / "scripts" / "lib" / "_common.sh"

    def check(path):
        out = subprocess.run(
            ["bash", "-c", f"source {p}; validate_safe_repo_path '{path}'"],
            capture_output=True, text=True,
        )
        return out.returncode

    # MUST accept (legitimate repo-relative paths):
    for good in (
        "paperclips/dist/cto.md",
        "paperclips/dist/codex/cx-cto.md",
        "paperclips/dist/trading/claude/CTO.md",
        "x.md",
    ):
        assert check(good) == 0, f"safe path {good!r} was rejected"
    # MUST reject:
    for bad in (
        "/etc/passwd",
        "/Users/anton/.ssh/id_ed25519",
        "../../../etc/shadow",
        "paperclips/../../etc/passwd",
        "paperclips/dist/../../../etc",
        "",
        "$(rm -rf /)",
        "`evil`",
        'path"with"quotes',
    ):
        assert check(bad) != 0, f"malicious path {bad!r} was accepted (CRITICAL)"


def test_smoke_test_sh_uses_bracket_syntax():
    """Code-rev H2-followup IMPORTANT-1: smoke-test.sh had 4 sites using
    `.agents.${var}` dot-path. Would silently break on kebab agent_names
    (yq returns null on subtraction). All 4 must be bracket-syntax."""
    p = REPO / "paperclips" / "scripts" / "smoke-test.sh"
    text = p.read_text()
    bad = re.findall(r'\.agents\.\$\{[a-z_]+\}', text)
    assert not bad, (
        f"smoke-test.sh still uses dot-path .agents.${{var}} "
        f"({len(bad)} occurrences) — must use .agents[\"${{var}}\"] "
        f"(silently returns null on kebab agent_names like cx-cto)"
    )


def test_bootstrap_validates_reports_to_name():
    """Security H2-followup CRIT-1: reports_to_name from manifest must be
    validated before yq interpolation (same protection as agent_name).
    Without this, manifest `reportsTo: 'x.system("evil")'` could yq-inject."""
    p = REPO / "paperclips" / "scripts" / "bootstrap-project.sh"
    text = p.read_text()
    # validate_agent_name must be called on reports_to_name BEFORE yq lookup.
    m = re.search(
        r'reports_to_name=.*?validate_agent_name "\$reports_to_name".*?\.agents\[\\?"?\$\{reports_to_name\}\\?"?\]',
        text, re.DOTALL,
    )
    assert m, (
        "reports_to_name must be validate_agent_name'd before yq bracket lookup "
        "(GIM-244 CRIT-E parity for the reportsTo field)"
    )


def test_bootstrap_validates_output_path_against_traversal():
    """Security H2-followup CRIT-2: bootstrap must call
    validate_safe_repo_path on the manifest-supplied output_path before
    interpolation into filesystem operations."""
    p = REPO / "paperclips" / "scripts" / "bootstrap-project.sh"
    text = p.read_text()
    callsites = re.findall(r'validate_safe_repo_path "?\$', text)
    assert len(callsites) >= 2, (
        f"bootstrap-project.sh must guard output_path at BOTH deploy_one + "
        f"workspace-copy steps with validate_safe_repo_path (found {len(callsites)} of 2)"
    )
