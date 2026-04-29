"""Integration tests using real .scip fixture files.

Covers ts-mini-project, py-mini-project, jvm-mini-project, oz-v5-mini-project.

These tests parse the pre-built SCIP binaries and verify actual symbol extraction
behaviour — both language detection and qualified_name format.

Markers:
  requires_scip_typescript — skipped if ts-mini-project/index.scip is missing
  requires_scip_python     — skipped if py-mini-project/index.scip is missing
  requires_scip_java       — skipped if jvm-mini-project/index.scip is missing (synthetic always present)
  requires_scip_solidity   — skipped if oz-v5-mini-project/index.scip is missing
"""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.extractors.foundation.models import Language, SymbolKind
from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file

FIXTURES = Path(__file__).parent.parent / "fixtures"
TS_SCIP = FIXTURES / "ts-mini-project" / "index.scip"
PY_SCIP = FIXTURES / "py-mini-project" / "index.scip"
JVM_SCIP = FIXTURES / "jvm-mini-project" / "index.scip"
SOL_SCIP = FIXTURES / "oz-v5-mini-project" / "index.scip"

requires_scip_typescript = pytest.mark.skipif(
    not TS_SCIP.exists(), reason="ts-mini-project/index.scip not present"
)
requires_scip_python = pytest.mark.skipif(
    not PY_SCIP.exists(), reason="py-mini-project/index.scip not present"
)
requires_scip_java = pytest.mark.skipif(
    not JVM_SCIP.exists(), reason="jvm-mini-project/index.scip not present"
)
requires_scip_solidity = pytest.mark.skipif(
    not SOL_SCIP.exists(), reason="oz-v5-mini-project/index.scip not present"
)


@requires_scip_typescript
class TestTsMiniProjectFixture:
    def test_parses_without_error(self) -> None:
        index = parse_scip_file(TS_SCIP)
        assert index is not None

    def test_yields_typescript_occurrences(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        ts_occs = [o for o in occs if o.language == Language.TYPESCRIPT]
        assert len(ts_occs) > 0, "Expected at least one TypeScript occurrence"

    def test_has_def_occurrences(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        defs = [o for o in occs if o.kind == SymbolKind.DEF]
        assert len(defs) > 0, "Expected at least one DEF occurrence"

    def test_greeter_class_def_present(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        greeter_defs = [n for n in names if "Greeter" in n]
        assert greeter_defs, f"Expected Greeter def in {names!r}"

    def test_qualified_names_have_no_version(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        for occ in occs:
            parts = occ.symbol_qualified_name.split(" ")
            for part in parts:
                assert not (part.count(".") >= 2 and part[0].isdigit()), (
                    f"Possible version token in qualified_name: {occ.symbol_qualified_name!r}"
                )

    def test_has_use_occurrences(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        uses = [o for o in occs if o.kind == SymbolKind.USE]
        assert len(uses) > 0, "Expected at least one USE occurrence in index.ts"

    def test_cache_generic_class_present(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        cache_defs = [n for n in names if "Cache" in n]
        assert cache_defs, f"Expected Cache def in {names!r}"

    def test_logger_default_export_present(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        logger_defs = [n for n in names if "Logger" in n]
        assert logger_defs, f"Expected Logger def in {names!r}"

    def test_button_tsx_jsx_component(self) -> None:
        index = parse_scip_file(TS_SCIP)
        doc_paths = {doc.relative_path for doc in index.documents}
        button_docs = [p for p in doc_paths if "Button.tsx" in p]
        assert button_docs, f"Expected Button.tsx document, got: {doc_paths!r}"
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        ts_occs = [
            o
            for o in occs
            if o.language == Language.TYPESCRIPT and "Button" in o.symbol_qualified_name
        ]
        assert ts_occs, "Expected at least one TYPESCRIPT occurrence for Button"

    def test_legacy_js_javascript_language(self) -> None:
        index = parse_scip_file(TS_SCIP)
        doc_paths = {doc.relative_path for doc in index.documents}
        js_docs = [p for p in doc_paths if "legacy.js" in p]
        assert js_docs, f"Expected legacy.js document, got: {doc_paths!r}"
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        js_occs = [o for o in occs if o.language == Language.JAVASCRIPT]
        assert js_occs, "Expected at least one JAVASCRIPT occurrence from legacy.js"


@requires_scip_python
class TestPyMiniProjectFixture:
    def test_parses_without_error(self) -> None:
        index = parse_scip_file(PY_SCIP)
        assert index is not None

    def test_yields_python_occurrences(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        py_occs = [o for o in occs if o.language == Language.PYTHON]
        assert len(py_occs) > 0, "Expected at least one Python occurrence"

    def test_has_def_occurrences(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        defs = [o for o in occs if o.kind == SymbolKind.DEF]
        assert len(defs) > 0, "Expected at least one DEF occurrence"

    def test_greeter_class_def_present(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        greeter_defs = [n for n in names if "Greeter" in n]
        assert greeter_defs, f"Expected Greeter def in {names!r}"

    def test_qualified_names_have_no_version(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        for occ in occs:
            parts = occ.symbol_qualified_name.split(" ")
            for part in parts:
                assert not (part.count(".") >= 2 and part[0].isdigit()), (
                    f"Possible version token in qualified_name: {occ.symbol_qualified_name!r}"
                )

    def test_cache_generic_class_present(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        cache_defs = [n for n in names if "Cache" in n]
        assert cache_defs, f"Expected Cache def in {names!r}"

    def test_config_dataclass_present(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        config_defs = [n for n in names if "Config" in n]
        assert config_defs, f"Expected Config def in {names!r}"

    def test_logger_decorated_method(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        logger_defs = [n for n in names if "Logger" in n]
        assert logger_defs, f"Expected Logger def in {names!r}"


@requires_scip_java
class TestJvmMiniProjectFixture:
    def test_parses_without_error(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        assert index is not None

    def test_yields_java_occurrences(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        java_occs = [o for o in occs if o.language == Language.JAVA]
        assert len(java_occs) > 0, "Expected at least one Java occurrence"

    def test_yields_kotlin_occurrences(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        kt_occs = [o for o in occs if o.language == Language.KOTLIN]
        assert len(kt_occs) > 0, "Expected at least one Kotlin occurrence"

    def test_has_def_occurrences(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        defs = [o for o in occs if o.kind == SymbolKind.DEF]
        assert len(defs) > 0, "Expected at least one DEF occurrence"

    def test_user_class_def_present(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        user_defs = [n for n in names if "User" in n]
        assert user_defs, f"Expected User def; got defs: {names!r}"

    def test_inner_builder_nested_class_def_present(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        builder_defs = [n for n in names if "Builder" in n]
        assert builder_defs, f"Expected Inner.Builder def; got defs: {names!r}"

    def test_kotlin_companion_def_present(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        companion_defs = [n for n in names if "Companion" in n]
        assert companion_defs, f"Expected Logger.Companion def; got defs: {names!r}"

    def test_sealed_subclasses_present(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("Success" in n for n in names), (
            f"Expected Result.Success def; {names!r}"
        )
        assert any("Failure" in n for n in names), (
            f"Expected Result.Failure def; {names!r}"
        )
        assert any("Loading" in n for n in names), (
            f"Expected Result.Loading def; {names!r}"
        )

    def test_has_use_occurrences(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        uses = [o for o in occs if o.kind == SymbolKind.USE]
        assert len(uses) > 0, "Expected at least one USE occurrence"

    def test_cache_generic_def_present(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        cache_defs = [n for n in names if "Cache" in n]
        assert cache_defs, f"Expected Cache# generic def; got defs: {names!r}"
        assert any("Cache#put" in n for n in names), (
            f"Expected Cache#put() def; got: {names!r}"
        )

    def test_kotlin_greet_default_present(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        greet_default = [n for n in names if "greet$default" in n]
        assert greet_default, (
            f"Expected Greeter#greet$default() def for default-param method; "
            f"got: {names!r}"
        )

    def test_kotlin_extension_fun_present(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        ext_funs = [n for n in names if "toGreeting" in n]
        assert ext_funs, f"Expected extension fun toGreeting() def; got: {names!r}"

    def test_anonymous_inner_class_filtered(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        local_occs = [o for o in occs if "local" in o.symbol_qualified_name.lower()]
        assert not local_occs, (
            f"Anonymous inner class 'local N' symbols must be filtered; "
            f"found: {[o.symbol_qualified_name for o in local_occs]!r}"
        )

    def test_qualified_names_have_no_scheme_or_manager(self) -> None:
        index = parse_scip_file(JVM_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        for occ in occs:
            qn = occ.symbol_qualified_name
            assert not qn.startswith("semanticdb"), (
                f"Qualified name must not start with 'semanticdb': {qn!r}"
            )
            assert not qn.startswith("maven"), (
                f"Qualified name must not start with 'maven': {qn!r}"
            )


# ---------------------------------------------------------------------------
# Oracle constants (GIM-124 Phase 1.0 — filled 2026-04-29, commit 53fc272)
# ---------------------------------------------------------------------------
# 6 .sol files, 8 contracts/interfaces, 76 DEF + 12 ForwardDef(DECL) = 88 total
_SOL_N_OCCURRENCES_TOTAL = 88
_SOL_N_DEF = 76
_SOL_N_DECL = 12  # ForwardDef inherited-but-not-overridden functions


@requires_scip_solidity
class TestSolMiniProjectFixture:
    def test_parses_without_error(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        assert index is not None

    def test_yields_solidity_occurrences(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        sol_occs = [o for o in occs if o.language == Language.SOLIDITY]
        assert len(sol_occs) >= _SOL_N_OCCURRENCES_TOTAL, (
            f"Expected ≥{_SOL_N_OCCURRENCES_TOTAL} SOLIDITY occurrences, got {len(sol_occs)}"
        )

    def test_occurrence_total_matches_oracle(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        assert len(occs) == _SOL_N_OCCURRENCES_TOTAL, (
            f"Oracle: {_SOL_N_OCCURRENCES_TOTAL} occurrences, got {len(occs)}"
        )

    def test_six_documents(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        assert len(index.documents) == 6

    def test_def_count_matches_oracle(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        defs = [o for o in occs if o.kind == SymbolKind.DEF]
        assert len(defs) == _SOL_N_DEF, f"Oracle: {_SOL_N_DEF} DEF, got {len(defs)}"

    def test_inherited_forward_def_count_matches_oracle(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        decls = [o for o in occs if o.kind == SymbolKind.DECL]
        assert len(decls) == _SOL_N_DECL, (
            f"Oracle: {_SOL_N_DECL} DECL (ForwardDef), got {len(decls)}"
        )

    def test_erc20_contract_def_present(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("`ERC20`#." in n for n in names), (
            f"Expected ERC20 contract def; got: {names!r}"
        )

    def test_ownable_contract_def_present(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("`Ownable`#." in n for n in names), (
            f"Expected Ownable contract def; got: {names!r}"
        )

    def test_transfer_abi_selector_oracle(self) -> None:
        # Oracle: transfer(address,uint256) → 0xa9059cbb
        index = parse_scip_file(SOL_SCIP)
        found = False
        for doc in index.documents:
            for si in doc.symbols:
                if "`ERC20`#transfer(address,uint256)." in si.symbol:
                    found = any(
                        d == "abi_selector:0xa9059cbb" for d in si.documentation
                    )
                    assert found, (
                        f"Expected abi_selector:0xa9059cbb for ERC20.transfer; "
                        f"got: {list(si.documentation)}"
                    )
                    break
        assert found, "ERC20.transfer(address,uint256) symbol not found in index"

    def test_owner_abi_selector_oracle(self) -> None:
        # Oracle: owner() → 0x8da5cb5b
        index = parse_scip_file(SOL_SCIP)
        found = False
        for doc in index.documents:
            for si in doc.symbols:
                if "`Ownable`#owner()." in si.symbol:
                    found = any(
                        d == "abi_selector:0x8da5cb5b" for d in si.documentation
                    )
                    assert found, (
                        f"Expected abi_selector:0x8da5cb5b for Ownable.owner; "
                        f"got: {list(si.documentation)}"
                    )
                    break
        assert found, "Ownable.owner() symbol not found in index"

    def test_transfer_ownership_abi_selector_oracle(self) -> None:
        # Oracle: transferOwnership(address) → 0xf2fde38b
        index = parse_scip_file(SOL_SCIP)
        found = False
        for doc in index.documents:
            for si in doc.symbols:
                if "`Ownable`#transferOwnership(address)." in si.symbol:
                    found = any(
                        d == "abi_selector:0xf2fde38b" for d in si.documentation
                    )
                    assert found, (
                        f"Expected abi_selector:0xf2fde38b for Ownable.transferOwnership; "
                        f"got: {list(si.documentation)}"
                    )
                    break
        assert found, "Ownable.transferOwnership(address) symbol not found in index"

    def test_inherited_msg_sender_is_forward_def(self) -> None:
        # Ownable._msgSender() is inherited from Context, not overridden → DECL
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        ownable_msg_sender = [
            o for o in occs if "`Ownable`#_msgSender()." in o.symbol_qualified_name
        ]
        assert ownable_msg_sender, "Expected Ownable._msgSender() inherited occurrence"
        assert all(o.kind == SymbolKind.DECL for o in ownable_msg_sender), (
            f"Expected DECL (ForwardDef) for inherited _msgSender; "
            f"got kinds: {[o.kind for o in ownable_msg_sender]}"
        )

    def test_erc20_custom_error_present(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("ERC20InsufficientBalance(" in n for n in names), (
            f"Expected ERC20InsufficientBalance error def; got: {names!r}"
        )

    def test_ownable_custom_error_present(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("OwnableUnauthorizedAccount(" in n for n in names), (
            f"Expected OwnableUnauthorizedAccount error def; got: {names!r}"
        )

    def test_erc20_approve_overloads_distinct_qualified_names(self) -> None:
        # ERC20 has _approve(address,address,uint256) and _approve(address,address,uint256,bool)
        # Both internal — distinct symbols, no ABI selectors
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        approve_defs = [
            o
            for o in occs
            if o.kind == SymbolKind.DEF
            and "`ERC20`#_approve(" in o.symbol_qualified_name
        ]
        qnames = {o.symbol_qualified_name for o in approve_defs}
        assert len(qnames) == 2, (
            f"Expected 2 distinct _approve overload symbols; got: {qnames!r}"
        )
        assert any("uint256)." in n for n in qnames), "Expected 3-arg _approve"
        assert any("uint256,bool)." in n for n in qnames), "Expected 4-arg _approve"

    def test_qualified_names_use_ethereum_path_format(self) -> None:
        index = parse_scip_file(SOL_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        for occ in occs:
            qn = occ.symbol_qualified_name
            assert not qn.startswith("scip-solidity"), (
                f"qualified_name must not include scheme: {qn!r}"
            )
            assert not qn.startswith("ethereum"), (
                f"qualified_name must not include manager: {qn!r}"
            )
