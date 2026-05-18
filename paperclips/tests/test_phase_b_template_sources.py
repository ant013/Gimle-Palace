"""Phase B: template-source resolver tests per spec §6.5."""
import pytest

SOURCES = {
    "manifest": {
        "project": {"key": "synth", "issue_prefix": "SYN", "display_name": "Synth"},
        "domain": {"target_name": "Test Wallet"},
        "mcp": {"service_name": "synth-mcp", "tool_namespace": "synth"},
    },
    "bindings": {
        "company_id": "7f3a-...",
        "agents": {"SynthCTO": "a2c1-..."},
    },
    "paths": {"project_root": "/Users/me/Code/synth"},
    "plugins": {"telegram": {"plugin_id": "60023916-...", "chat_id": "-100..."}},
}


def test_resolve_simple_manifest_var():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("Project: {{project.key}}", SOURCES)
    assert out == "Project: synth"


def test_resolve_nested():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("MCP: {{mcp.service_name}}", SOURCES)
    assert out == "MCP: synth-mcp"


def test_resolve_bindings():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("Company: {{bindings.company_id}}", SOURCES)
    assert out == "Company: 7f3a-..."


def test_resolve_paths():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("Root: {{paths.project_root}}", SOURCES)
    assert out == "Root: /Users/me/Code/synth"


def test_resolve_plugins_deep():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("Plugin: {{plugins.telegram.plugin_id}}", SOURCES)
    assert out == "Plugin: 60023916-..."


def test_unresolved_var_raises():
    from paperclips.scripts.resolve_template_sources import (
        UnresolvedTemplateError,
        resolve,
    )
    with pytest.raises(UnresolvedTemplateError, match="nonexistent"):
        resolve("{{nonexistent.var}}", SOURCES)


def test_unknown_top_level_source_raises():
    from paperclips.scripts.resolve_template_sources import (
        UnresolvedTemplateError,
        resolve,
    )
    with pytest.raises(UnresolvedTemplateError, match="unknown source"):
        resolve("{{secrets.api_key}}", SOURCES)


def test_resolve_with_whitespace_inside_braces():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("{{ project.key }}", SOURCES)
    assert out == "synth"


def test_resolve_multiple_in_one_string():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("{{project.key}}: {{mcp.service_name}}", SOURCES)
    assert out == "synth: synth-mcp"
