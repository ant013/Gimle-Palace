"""Drift-check for scip-java-generated SCIP artifacts.

Skipped unless PALACE_REAL_JVM_SCIP env var points to a real scip-java
artifact. Run locally after regenerating jvm-mini-project with:

    make regen-jvm-fixture
    PALACE_REAL_JVM_SCIP=tests/extractors/fixtures/jvm-mini-project/index.scip \\
        uv run pytest tests/extractors/unit/test_symbol_index_java_drift.py -v -m requires_scip_java

Verify that the parser handles real scip-java output without error and
that JVM-specific symbol formats (companion objects, sealed subclasses,
generics, inner classes) are correctly normalised.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from palace_mcp.extractors.foundation.models import Language, SymbolKind
from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file

_REAL_SCIP_ENV = "PALACE_REAL_JVM_SCIP"
_real_scip_path: Path | None = None
if _env := os.environ.get(_REAL_SCIP_ENV):
    _candidate = Path(_env)
    if _candidate.exists():
        _real_scip_path = _candidate

requires_scip_java = pytest.mark.skipif(
    _real_scip_path is None,
    reason=(
        f"Set {_REAL_SCIP_ENV}=<path> to point to a real scip-java artifact. "
        "Run 'make regen-jvm-fixture' first."
    ),
)


@requires_scip_java
class TestScipJavaDrift:
    """Drift checks against a real scip-java-generated index.

    These assertions anchor the parser contract to actual scip-java output.
    If scip-java changes its symbol scheme or format, these tests catch it.
    """

    def _occs(self) -> list[object]:
        assert _real_scip_path is not None
        index = parse_scip_file(_real_scip_path)
        return list(iter_scip_occurrences(index, commit_sha="drift-check"))

    def test_parses_real_artifact_without_error(self) -> None:
        assert _real_scip_path is not None
        index = parse_scip_file(_real_scip_path)
        assert index is not None

    def test_java_and_kotlin_languages_detected(self) -> None:
        from palace_mcp.extractors.foundation.models import Language

        occs = self._occs()
        langs = {o.language for o in occs}  # type: ignore[attr-defined]
        assert Language.JAVA in langs, f"Expected JAVA in {langs}"
        assert Language.KOTLIN in langs, f"Expected KOTLIN in {langs}"

    def test_def_occurrences_present(self) -> None:
        occs = self._occs()
        defs = [o for o in occs if o.kind == SymbolKind.DEF]  # type: ignore[attr-defined]
        assert len(defs) > 0, "No DEF occurrences in real scip-java artifact"

    def test_no_scheme_token_in_qualified_names(self) -> None:
        occs = self._occs()
        for occ in occs:
            qn = occ.symbol_qualified_name  # type: ignore[attr-defined]
            assert not qn.startswith("semanticdb"), (
                f"Scheme 'semanticdb' leaked into qualified_name: {qn!r}. "
                "Parser's _extract_qualified_name() is not stripping first 4 tokens."
            )

    def test_no_version_token_in_qualified_names(self) -> None:
        occs = self._occs()
        for occ in occs:
            qn = occ.symbol_qualified_name  # type: ignore[attr-defined]
            parts = qn.split(" ")
            for part in parts:
                # Version tokens look like "1.9.23" or "17"
                if part and part[0].isdigit() and "." in part:
                    pytest.fail(
                        f"Possible version token '{part}' in qualified_name: {qn!r}. "
                        "Parser's _extract_qualified_name() is not stripping version token."
                    )

    def test_companion_object_symbols_not_filtered(self) -> None:
        occs = self._occs()
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}  # type: ignore[attr-defined]
        companion_defs = [n for n in names if "Companion" in n]
        assert companion_defs, (
            f"Expected at least one Kotlin companion object def. Got defs: {list(names)[:20]!r}"
        )

    def test_sealed_subclasses_not_filtered(self) -> None:
        occs = self._occs()
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}  # type: ignore[attr-defined]
        sealed = [n for n in names if any(s in n for s in ("Success", "Failure", "Loading"))]
        assert sealed, (
            f"Expected sealed subclass defs (Success/Failure/Loading). "
            f"Got defs: {list(names)[:20]!r}"
        )
