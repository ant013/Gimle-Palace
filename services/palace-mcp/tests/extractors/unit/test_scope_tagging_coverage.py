from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]

WRAPPED_FILES = {
    "services/palace-mcp/src/palace_mcp/extractors/coding_convention/neo4j_writer.py",
    "services/palace-mcp/src/palace_mcp/extractors/testability_di/neo4j_writer.py",
    "services/palace-mcp/src/palace_mcp/extractors/arch_layer/neo4j_writer.py",
    "services/palace-mcp/src/palace_mcp/extractors/localization_accessibility/neo4j_writer.py",
    "services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py",
}

EXEMPT_FILES = {
    "services/palace-mcp/src/palace_mcp/extractors/crypto_domain_model/extractor.py",
    "services/palace-mcp/src/palace_mcp/extractors/git_history/neo4j_writer.py",
    "services/palace-mcp/src/palace_mcp/extractors/code_ownership/neo4j_writer.py",
    "services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py",
    "services/palace-mcp/src/palace_mcp/extractors/dependency_surface/neo4j_writer.py",
}


def test_named_g0b_writers_are_wrapped_or_explicitly_exempt() -> None:
    for rel_path in sorted(WRAPPED_FILES | EXEMPT_FILES):
        text = (ROOT / rel_path).read_text(encoding="utf-8")
        if rel_path in WRAPPED_FILES:
            assert "ScopeTaggedWriter" in text, f"{rel_path} must use ScopeTaggedWriter"
            continue
        assert "scope-tagging-exempt" in text, f"{rel_path} needs an exemption marker"
        assert "group_id" in text, f"{rel_path} exemption must still set group_id"
