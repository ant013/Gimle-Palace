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
    """Phase G gimle manifest uses kebab agent_names (cto, cx-cto). Regex must allow `-`."""
    p = REPO / "paperclips" / "scripts" / "lib" / "_common.sh"
    text = p.read_text()
    # The regex line for validate_agent_name must include `-` in the char class.
    m = re.search(
        r'validate_agent_name\(\).*?\[A-Za-z\]\[A-Za-z0-9_\-?\]\*',
        text, re.DOTALL,
    )
    assert m, (
        "validate_agent_name regex must allow `-` for kebab agent_names "
        "(Phase G gimle uses cto, cx-cto, etc.)"
    )


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
    must read manifest's per-agent `output_path` to find the file."""
    p = REPO / "paperclips" / "scripts" / "bootstrap-project.sh"
    text = p.read_text()
    # The fallback default still references canonical path, but the primary
    # lookup must read .output_path from the manifest.
    assert re.search(
        r'\.output_path //',
        text,
    ), "bootstrap-project.sh must consult manifest's `output_path` field (fallback to canonical default)"


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
