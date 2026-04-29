"""Unit tests for scip_emit.solidity — slither AST → SCIP Index (GIM-124).

Uses mock slither-like objects (types.SimpleNamespace) to avoid requiring
a real slither installation in the uv venv. Tests cover Tasks 3-5:
  - Task 3: basic emit (contract, function, event, modifier, state var)
  - Task 4: constructor/fallback/receive, inheritance, overloads, public getter
  - Task 5: mapping type backtick-escape in parameter lists
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from palace_mcp.scip_emit.abi_selector import compute_abi_selector
from palace_mcp.scip_emit.solidity import (
    _format_params,
    _scip_escape_type,
    emit_index,
)

# SCIP role bitmasks
_ROLE_DEF = 1
_ROLE_FORWARD_DEF = 64

# SymbolInformation.Kind integer constants (from scip.proto)
_KIND_CONTRACT = 62
_KIND_LIBRARY = 64
_KIND_INTERFACE = 21
_KIND_FUNCTION = 17
_KIND_CONSTRUCTOR = 9
_KIND_EVENT = 13
_KIND_MODIFIER = 65
_KIND_FIELD = 15
_KIND_ERROR = 63


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _filename(tmp_path: Path, rel: str) -> SimpleNamespace:
    abs_path = str(tmp_path / rel)
    return SimpleNamespace(absolute=abs_path, relative=rel, short=rel)


def _source_mapping(tmp_path: Path, rel: str) -> SimpleNamespace:
    return SimpleNamespace(filename=_filename(tmp_path, rel))


def _func(
    canonical_name: str,
    *,
    visibility: str = "public",
    is_constructor: bool = False,
    is_fallback: bool = False,
    is_receive: bool = False,
) -> SimpleNamespace:
    dot_idx = canonical_name.index(".")
    sig = canonical_name[dot_idx + 1 :]
    name = sig[: sig.index("(")]
    return SimpleNamespace(
        name=name,
        canonical_name=canonical_name,
        visibility=visibility,
        is_constructor=is_constructor,
        is_fallback=is_fallback,
        is_receive=is_receive,
    )


def _event(canonical_name: str) -> SimpleNamespace:
    dot_idx = canonical_name.index(".")
    sig = canonical_name[dot_idx + 1 :]
    name = sig[: sig.index("(")]
    return SimpleNamespace(name=name, canonical_name=canonical_name)


def _modifier(canonical_name: str) -> SimpleNamespace:
    dot_idx = canonical_name.index(".")
    sig = canonical_name[dot_idx + 1 :]
    name = sig[: sig.index("(")]
    return SimpleNamespace(name=name, canonical_name=canonical_name)


def _var(name: str, *, visibility: str = "internal") -> SimpleNamespace:
    return SimpleNamespace(name=name, visibility=visibility)


def _error(canonical_name: str) -> SimpleNamespace:
    dot_idx = canonical_name.index(".")
    sig = canonical_name[dot_idx + 1 :]
    name = sig[: sig.index("(")]
    return SimpleNamespace(name=name, canonical_name=canonical_name)


def _contract(
    name: str,
    tmp_path: Path,
    rel_path: str,
    *,
    kind: str = "contract",
    functions: list[SimpleNamespace] | None = None,
    events: list[SimpleNamespace] | None = None,
    modifiers: list[SimpleNamespace] | None = None,
    state_vars: list[SimpleNamespace] | None = None,
    custom_errors: list[SimpleNamespace] | None = None,
    functions_inherited: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        source_mapping=_source_mapping(tmp_path, rel_path),
        contract_kind=kind,
        is_library=(kind == "library"),
        is_interface=(kind == "interface"),
        functions_declared=functions or [],
        events_declared=events or [],
        modifiers_declared=modifiers or [],
        state_variables_declared=state_vars or [],
        custom_errors_declared=custom_errors or [],
        functions_inherited=functions_inherited or [],
    )


def _slither(*contracts: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(contracts=list(contracts))


def _def_symbols(doc: object) -> set[str]:
    return {occ.symbol for occ in doc.occurrences if occ.symbol_roles & _ROLE_DEF}


def _kind_map(doc: object) -> dict[str, int]:
    return {si.symbol: si.kind for si in doc.symbols}


def _abi_selector_map(doc: object) -> dict[str, str]:
    result: dict[str, str] = {}
    for si in doc.symbols:
        for d in si.documentation:
            if d.startswith("abi_selector:"):
                result[si.symbol] = d[len("abi_selector:") :]
    return result


# ---------------------------------------------------------------------------
# Task 3: basic emit
# ---------------------------------------------------------------------------


class TestEmitIndexSingleContract:
    """1 contract with 1 function + 1 event + 1 modifier + 1 state var."""

    @pytest.fixture
    def slither_obj(self, tmp_path: Path) -> SimpleNamespace:
        c = _contract(
            "Token",
            tmp_path,
            "contracts/Token.sol",
            functions=[_func("Token.transfer(address,uint256)")],
            events=[_event("Token.Transfer(address,address,uint256)")],
            modifiers=[_modifier("Token.onlyOwner()")],
            state_vars=[_var("_owner")],
        )
        return _slither(c)

    def test_one_document(self, slither_obj: SimpleNamespace, tmp_path: Path) -> None:
        index = emit_index(slither_obj, tmp_path)
        assert len(index.documents) == 1

    def test_document_language(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        assert index.documents[0].language == "solidity"

    def test_document_relative_path(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        assert index.documents[0].relative_path == "contracts/Token.sol"

    def test_contract_def_symbol(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        syms = _def_symbols(index.documents[0])
        assert (
            "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#."
            in syms
        )

    def test_function_def_symbol(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        syms = _def_symbols(index.documents[0])
        expected = "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#transfer(address,uint256)."
        assert expected in syms

    def test_event_def_symbol(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        syms = _def_symbols(index.documents[0])
        expected = "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#Transfer(address,address,uint256)."
        assert expected in syms

    def test_modifier_def_symbol(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        syms = _def_symbols(index.documents[0])
        expected = "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#onlyOwner()."
        assert expected in syms

    def test_state_var_def_symbol(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        syms = _def_symbols(index.documents[0])
        expected = "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#_owner."
        assert expected in syms

    def test_symbol_info_kinds(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        km = _kind_map(index.documents[0])
        rel = "contracts/Token.sol"
        assert km[f"scip-solidity ethereum {rel} . {rel}/`Token`#."] == _KIND_CONTRACT
        assert (
            km[
                f"scip-solidity ethereum {rel} . {rel}/`Token`#transfer(address,uint256)."
            ]
            == _KIND_FUNCTION
        )
        assert (
            km[
                f"scip-solidity ethereum {rel} . {rel}/`Token`#Transfer(address,address,uint256)."
            ]
            == _KIND_EVENT
        )
        assert (
            km[f"scip-solidity ethereum {rel} . {rel}/`Token`#onlyOwner()."]
            == _KIND_MODIFIER
        )
        assert (
            km[f"scip-solidity ethereum {rel} . {rel}/`Token`#_owner."] == _KIND_FIELD
        )

    def test_public_function_has_abi_selector(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        selectors = _abi_selector_map(index.documents[0])
        rel = "contracts/Token.sol"
        sym = f"scip-solidity ethereum {rel} . {rel}/`Token`#transfer(address,uint256)."
        assert sym in selectors
        assert selectors[sym] == "0xa9059cbb"

    def test_internal_var_has_no_abi_selector(
        self, slither_obj: SimpleNamespace, tmp_path: Path
    ) -> None:
        index = emit_index(slither_obj, tmp_path)
        selectors = _abi_selector_map(index.documents[0])
        rel = "contracts/Token.sol"
        var_sym = f"scip-solidity ethereum {rel} . {rel}/`Token`#_owner."
        assert var_sym not in selectors

    def test_two_contracts_same_file_one_document(self, tmp_path: Path) -> None:
        rel = "contracts/Two.sol"
        c1 = _contract("A", tmp_path, rel)
        c2 = _contract("B", tmp_path, rel)
        index = emit_index(_slither(c1, c2), tmp_path)
        assert len(index.documents) == 1

    def test_two_contracts_different_files_two_documents(self, tmp_path: Path) -> None:
        c1 = _contract("A", tmp_path, "contracts/A.sol")
        c2 = _contract("B", tmp_path, "contracts/B.sol")
        index = emit_index(_slither(c1, c2), tmp_path)
        assert len(index.documents) == 2


class TestContractKinds:
    def test_library_kind(self, tmp_path: Path) -> None:
        c = _contract("Lib", tmp_path, "lib/Lib.sol", kind="library")
        index = emit_index(_slither(c), tmp_path)
        km = _kind_map(index.documents[0])
        rel = "lib/Lib.sol"
        assert km[f"scip-solidity ethereum {rel} . {rel}/`Lib`#."] == _KIND_LIBRARY

    def test_interface_kind(self, tmp_path: Path) -> None:
        c = _contract("IToken", tmp_path, "contracts/IToken.sol", kind="interface")
        index = emit_index(_slither(c), tmp_path)
        km = _kind_map(index.documents[0])
        rel = "contracts/IToken.sol"
        assert km[f"scip-solidity ethereum {rel} . {rel}/`IToken`#."] == _KIND_INTERFACE


class TestCustomErrors:
    def test_custom_error_symbol_and_kind(self, tmp_path: Path) -> None:
        c = _contract(
            "Errors",
            tmp_path,
            "contracts/Errors.sol",
            custom_errors=[_error("Errors.InsufficientBalance(address,uint256)")],
        )
        index = emit_index(_slither(c), tmp_path)
        syms = _def_symbols(index.documents[0])
        rel = "contracts/Errors.sol"
        expected = f"scip-solidity ethereum {rel} . {rel}/`Errors`#InsufficientBalance(address,uint256)."
        assert expected in syms
        assert _kind_map(index.documents[0])[expected] == _KIND_ERROR


# ---------------------------------------------------------------------------
# Task 4: constructor, fallback, receive
# ---------------------------------------------------------------------------


class TestSpecialFunctions:
    def test_constructor_named_after_contract(self, tmp_path: Path) -> None:
        c = _contract(
            "Token",
            tmp_path,
            "contracts/Token.sol",
            functions=[_func("Token.constructor(address)", is_constructor=True)],
        )
        index = emit_index(_slither(c), tmp_path)
        syms = _def_symbols(index.documents[0])
        rel = "contracts/Token.sol"
        expected = f"scip-solidity ethereum {rel} . {rel}/`Token`#Token(address)."
        assert expected in syms

    def test_constructor_kind_is_constructor(self, tmp_path: Path) -> None:
        c = _contract(
            "Token",
            tmp_path,
            "contracts/Token.sol",
            functions=[_func("Token.constructor()", is_constructor=True)],
        )
        index = emit_index(_slither(c), tmp_path)
        rel = "contracts/Token.sol"
        sym = f"scip-solidity ethereum {rel} . {rel}/`Token`#Token()."
        assert _kind_map(index.documents[0])[sym] == _KIND_CONSTRUCTOR

    def test_constructor_has_no_abi_selector(self, tmp_path: Path) -> None:
        c = _contract(
            "Token",
            tmp_path,
            "contracts/Token.sol",
            functions=[
                _func(
                    "Token.constructor(address)",
                    is_constructor=True,
                    visibility="public",
                )
            ],
        )
        index = emit_index(_slither(c), tmp_path)
        selectors = _abi_selector_map(index.documents[0])
        rel = "contracts/Token.sol"
        sym = f"scip-solidity ethereum {rel} . {rel}/`Token`#Token(address)."
        assert sym not in selectors

    def test_fallback_named_fallback(self, tmp_path: Path) -> None:
        c = _contract(
            "Token",
            tmp_path,
            "contracts/Token.sol",
            functions=[_func("Token.fallback()", is_fallback=True)],
        )
        index = emit_index(_slither(c), tmp_path)
        syms = _def_symbols(index.documents[0])
        rel = "contracts/Token.sol"
        assert f"scip-solidity ethereum {rel} . {rel}/`Token`#fallback()." in syms

    def test_receive_named_receive(self, tmp_path: Path) -> None:
        c = _contract(
            "Token",
            tmp_path,
            "contracts/Token.sol",
            functions=[_func("Token.receive()", is_receive=True)],
        )
        index = emit_index(_slither(c), tmp_path)
        syms = _def_symbols(index.documents[0])
        rel = "contracts/Token.sol"
        assert f"scip-solidity ethereum {rel} . {rel}/`Token`#receive()." in syms


# ---------------------------------------------------------------------------
# Task 4: public state var auto-getter
# ---------------------------------------------------------------------------


class TestPublicStateVarGetter:
    def test_public_var_emits_field_and_getter(self, tmp_path: Path) -> None:
        c = _contract(
            "ERC20",
            tmp_path,
            "contracts/ERC20.sol",
            state_vars=[_var("totalSupply", visibility="public")],
        )
        index = emit_index(_slither(c), tmp_path)
        syms = _def_symbols(index.documents[0])
        rel = "contracts/ERC20.sol"
        field_sym = f"scip-solidity ethereum {rel} . {rel}/`ERC20`#totalSupply."
        getter_sym = f"scip-solidity ethereum {rel} . {rel}/`ERC20`#totalSupply()."
        assert field_sym in syms
        assert getter_sym in syms

    def test_public_var_getter_kind_is_function(self, tmp_path: Path) -> None:
        c = _contract(
            "ERC20",
            tmp_path,
            "contracts/ERC20.sol",
            state_vars=[_var("totalSupply", visibility="public")],
        )
        index = emit_index(_slither(c), tmp_path)
        rel = "contracts/ERC20.sol"
        getter_sym = f"scip-solidity ethereum {rel} . {rel}/`ERC20`#totalSupply()."
        assert _kind_map(index.documents[0])[getter_sym] == _KIND_FUNCTION

    def test_public_var_getter_has_abi_selector(self, tmp_path: Path) -> None:
        c = _contract(
            "ERC20",
            tmp_path,
            "contracts/ERC20.sol",
            state_vars=[_var("totalSupply", visibility="public")],
        )
        index = emit_index(_slither(c), tmp_path)
        rel = "contracts/ERC20.sol"
        getter_sym = f"scip-solidity ethereum {rel} . {rel}/`ERC20`#totalSupply()."
        selectors = _abi_selector_map(index.documents[0])
        assert getter_sym in selectors
        assert selectors[getter_sym] == compute_abi_selector("totalSupply()")

    def test_internal_var_has_no_getter(self, tmp_path: Path) -> None:
        c = _contract(
            "ERC20",
            tmp_path,
            "contracts/ERC20.sol",
            state_vars=[_var("_balances", visibility="internal")],
        )
        index = emit_index(_slither(c), tmp_path)
        syms = _def_symbols(index.documents[0])
        rel = "contracts/ERC20.sol"
        getter_sym = f"scip-solidity ethereum {rel} . {rel}/`ERC20`#_balances()."
        assert getter_sym not in syms


# ---------------------------------------------------------------------------
# Task 4: inheritance
# ---------------------------------------------------------------------------


class TestInheritance:
    def test_inherited_member_emitted_at_inheriting_contract(
        self, tmp_path: Path
    ) -> None:
        """B inherits A.foo() without overriding → symbol at B-level emitted."""
        base_func = _func("Base.foo()", visibility="public")
        base = _contract("Base", tmp_path, "contracts/Base.sol", functions=[base_func])

        # Child inherits foo() but does not override
        child_inherited_foo = _func("Base.foo()", visibility="public")
        child = _contract(
            "Child",
            tmp_path,
            "contracts/Child.sol",
            functions_inherited=[child_inherited_foo],
        )

        index = emit_index(_slither(base, child), tmp_path)

        # Base still has its own definition
        base_doc = next(
            d for d in index.documents if d.relative_path == "contracts/Base.sol"
        )
        assert (
            "scip-solidity ethereum contracts/Base.sol . contracts/Base.sol/`Base`#foo()."
            in _def_symbols(base_doc)
        )

        # Child has a ForwardDef for foo()
        child_doc = next(
            d for d in index.documents if d.relative_path == "contracts/Child.sol"
        )
        child_foo_sym = "scip-solidity ethereum contracts/Child.sol . contracts/Child.sol/`Child`#foo()."
        fwd_syms = {
            occ.symbol
            for occ in child_doc.occurrences
            if occ.symbol_roles & _ROLE_FORWARD_DEF
        }
        assert child_foo_sym in fwd_syms

    def test_overridden_member_not_forwarded(self, tmp_path: Path) -> None:
        """B overrides A.foo() → no ForwardDef at B-level for the inherited copy."""
        # Child overrides foo()
        child_declared_foo = _func("Child.foo()", visibility="public")
        child_inherited_foo = _func("Base.foo()", visibility="public")

        child = _contract(
            "Child",
            tmp_path,
            "contracts/Child.sol",
            functions=[child_declared_foo],
            functions_inherited=[child_inherited_foo],
        )

        index = emit_index(_slither(child), tmp_path)
        child_doc = index.documents[0]

        # DEF for the override should be present
        child_foo_sym = "scip-solidity ethereum contracts/Child.sol . contracts/Child.sol/`Child`#foo()."
        assert child_foo_sym in _def_symbols(child_doc)

        # No ForwardDef
        fwd_syms = {
            occ.symbol
            for occ in child_doc.occurrences
            if occ.symbol_roles & _ROLE_FORWARD_DEF
        }
        assert child_foo_sym not in fwd_syms


# ---------------------------------------------------------------------------
# Task 4: overloads
# ---------------------------------------------------------------------------


class TestOverloads:
    def test_overloads_produce_distinct_symbols(self, tmp_path: Path) -> None:
        mint_a = _func("Token.mint(address)", visibility="public")
        mint_b = _func("Token.mint(address,uint256)", visibility="public")
        c = _contract(
            "Token",
            tmp_path,
            "contracts/Token.sol",
            functions=[mint_a, mint_b],
        )
        index = emit_index(_slither(c), tmp_path)
        syms = _def_symbols(index.documents[0])
        rel = "contracts/Token.sol"
        sym_a = f"scip-solidity ethereum {rel} . {rel}/`Token`#mint(address)."
        sym_b = f"scip-solidity ethereum {rel} . {rel}/`Token`#mint(address,uint256)."
        assert sym_a in syms
        assert sym_b in syms

    def test_overloads_have_distinct_abi_selectors(self, tmp_path: Path) -> None:
        mint_a = _func("Token.mint(address)", visibility="public")
        mint_b = _func("Token.mint(address,uint256)", visibility="public")
        c = _contract(
            "Token",
            tmp_path,
            "contracts/Token.sol",
            functions=[mint_a, mint_b],
        )
        index = emit_index(_slither(c), tmp_path)
        selectors = _abi_selector_map(index.documents[0])
        rel = "contracts/Token.sol"
        sym_a = f"scip-solidity ethereum {rel} . {rel}/`Token`#mint(address)."
        sym_b = f"scip-solidity ethereum {rel} . {rel}/`Token`#mint(address,uint256)."
        assert sym_a in selectors
        assert sym_b in selectors
        assert selectors[sym_a] != selectors[sym_b]


# ---------------------------------------------------------------------------
# Task 5: mapping type backtick-escape
# ---------------------------------------------------------------------------


class TestScipEscapeType:
    def test_plain_type_unchanged(self) -> None:
        assert _scip_escape_type("address") == "address"
        assert _scip_escape_type("uint256") == "uint256"
        assert _scip_escape_type("bool") == "bool"

    def test_mapping_type_backtick_escaped(self) -> None:
        result = _scip_escape_type("mapping(address => uint256)")
        assert result == "`mapping(address => uint256)`"

    def test_internal_backtick_doubled(self) -> None:
        result = _scip_escape_type("mapping(address => `weird`)")
        assert result == "`mapping(address => ``weird``)`"


class TestFormatParams:
    def test_empty_params(self) -> None:
        assert _format_params("") == ""

    def test_simple_types(self) -> None:
        assert _format_params("address,uint256") == "address,uint256"

    def test_mapping_type_escaped(self) -> None:
        result = _format_params("mapping(address => uint256)")
        assert result == "`mapping(address => uint256)`"

    def test_mixed_params_with_mapping(self) -> None:
        result = _format_params("mapping(address => uint256),address")
        assert result == "`mapping(address => uint256)`,address"


class TestMappingTypeInFunctionSymbol:
    def test_mapping_param_in_symbol_backtick_escaped(self, tmp_path: Path) -> None:
        """internal function with mapping param → symbol has backtick-escaped type."""
        # Only internal visibility is valid for mapping storage params in Solidity
        f = _func(
            "Token._setBalance(mapping(address => uint256),address)",
            visibility="internal",
        )
        c = _contract("Token", tmp_path, "contracts/Token.sol", functions=[f])
        index = emit_index(_slither(c), tmp_path)
        syms = _def_symbols(index.documents[0])
        rel = "contracts/Token.sol"
        expected = (
            f"scip-solidity ethereum {rel} . {rel}/`Token`#"
            f"_setBalance(`mapping(address => uint256)`,address)."
        )
        assert expected in syms

    def test_mapping_param_round_trips_through_split(self, tmp_path: Path) -> None:
        """Verify scip_parser._split_scip_top_level handles backtick-escaped mapping."""
        from palace_mcp.extractors.scip_parser import _split_scip_top_level

        f = _func(
            "Token._setBalance(mapping(address => uint256),address)",
            visibility="internal",
        )
        c = _contract("Token", tmp_path, "contracts/Token.sol", functions=[f])
        index = emit_index(_slither(c), tmp_path)
        doc = index.documents[0]
        for occ in doc.occurrences:
            if "_setBalance" in occ.symbol:
                parts = _split_scip_top_level(occ.symbol)
                # Should split into exactly 5 top-level tokens (no spurious splits
                # inside the backtick-escaped mapping type)
                assert len(parts) == 5, f"Expected 5 parts; got {len(parts)}: {parts}"
                break
        else:
            pytest.fail("_setBalance symbol not found in occurrences")
