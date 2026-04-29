"""scip_emit.solidity — slither AST → SCIP Index protobuf emitter (GIM-124).

Converts slither's parsed Solidity AST to a SCIP Index protobuf. Accepts any
duck-typed object with slither's Contract interface; real slither is only needed
by the CLI entry point (lazy-imported at __main__).

SCIP symbol scheme:
  scip-solidity ethereum <rel_path> . <rel_path>/`<Contract>`#.         (contract)
  scip-solidity ethereum <rel_path> . <rel_path>/`<Contract>`#<fn>(<p>).  (function)
  scip-solidity ethereum <rel_path> . <rel_path>/`<Contract>`#<ev>(<p>).  (event)
  scip-solidity ethereum <rel_path> . <rel_path>/`<Contract>`#<mod>(<p>). (modifier)
  scip-solidity ethereum <rel_path> . <rel_path>/`<Contract>`#<var>.    (state var)
  scip-solidity ethereum <rel_path> . <rel_path>/`<Contract>`#<Err>(<p>). (custom error)

Inheritance: inherited-but-not-overridden functions are emitted at the inheriting
contract's qualified_name with FORWARD_DEF role (per GIM-124 spec, Q1 FQN var B).

Mapping types: `mapping(address => uint256)` contains SCIP-special chars (spaces,
parentheses, =>, etc.) and are backtick-escaped per SCIP grammar (GIM-123).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from palace_mcp.proto import scip_pb2
from palace_mcp.scip_emit.abi_selector import compute_abi_selector

_SCIP_ROLE_DEF = 1  # SymbolRole.Definition
_SCIP_ROLE_FORWARD_DEF = 64  # SymbolRole.ForwardDefinition

# SymbolInformation.Kind integer values from scip.proto
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
# Descriptor / symbol helpers
# ---------------------------------------------------------------------------


def _scip_escape_type(type_str: str) -> str:
    """Backtick-escape a Solidity type string if it contains SCIP-special characters.

    SCIP descriptors are split on whitespace; mapping types like
    'mapping(address => uint256)' contain spaces and must be wrapped in backticks
    per the SCIP grammar (GIM-123). Internal backticks are doubled per the
    escape rule.
    """
    special = set(" `()=>")
    if any(c in special for c in type_str):
        escaped = type_str.replace("`", "``")
        return f"`{escaped}`"
    return type_str


def _split_params(params_str: str) -> list[str]:
    """Split a comma-joined params string respecting balanced parentheses.

    Needed because mapping types contain commas: 'mapping(address => uint256)'.
    """
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in params_str:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts


def _format_params(params_str: str) -> str:
    """Re-escape individual parameter types from a pre-joined canonical params string."""
    if not params_str:
        return ""
    return ",".join(_scip_escape_type(t) for t in _split_params(params_str))


def _parse_canonical(canonical_name: str) -> tuple[str, str]:
    """Return (member_name, params_str) from 'Contract.member(params)'.

    Examples:
      "Token.transfer(address,uint256)" → ("transfer", "address,uint256")
      "Token.Token(address)"           → ("Token", "address")
      "Token.fallback()"               → ("fallback", "")
    """
    dot_idx = canonical_name.index(".")
    sig = canonical_name[dot_idx + 1 :]  # "func(params)"
    paren_idx = sig.index("(")
    member_name = sig[:paren_idx]  # "func"
    params_str = sig[paren_idx + 1 : -1]  # strip leading "(" and trailing ")"
    return member_name, params_str


def _member_sig(canonical_name: str) -> str:
    """Extract 'funcName(params)' from 'Contract.funcName(params)'."""
    return canonical_name[canonical_name.index(".") + 1 :]


def _symbol_str(rel_path: str, contract_name: str, descriptor: str) -> str:
    return (
        f"scip-solidity ethereum {rel_path} . {rel_path}/`{contract_name}`#{descriptor}"
    )


def _contract_kind(contract: Any) -> int:
    kind = getattr(contract, "contract_kind", "contract")
    if kind == "library":
        return _KIND_LIBRARY
    if kind == "interface":
        return _KIND_INTERFACE
    return _KIND_CONTRACT


# ---------------------------------------------------------------------------
# Occurrence + SymbolInformation writers
# ---------------------------------------------------------------------------


def _add_def_occurrence(doc: Any, symbol: str, role: int = _SCIP_ROLE_DEF) -> None:
    occ = doc.occurrences.add()
    occ.range.extend([0, 0, 0])
    occ.symbol = symbol
    occ.symbol_roles = role


def _add_symbol_info(
    doc: Any, symbol: str, kind: int, docs: list[str] | None = None
) -> None:
    si = doc.symbols.add()
    si.symbol = symbol
    si.kind = kind
    if docs:
        si.documentation.extend(docs)


# ---------------------------------------------------------------------------
# Per-member emitters
# ---------------------------------------------------------------------------


def _emit_function(doc: Any, rel_path: str, contract_name: str, func: Any) -> None:
    """Emit one function symbol (handles constructor, fallback, receive)."""
    canonical = func.canonical_name
    member_name, params_str = _parse_canonical(canonical)

    if func.is_constructor:
        sym = _symbol_str(
            rel_path, contract_name, f"{contract_name}({_format_params(params_str)})."
        )
        _add_def_occurrence(doc, sym)
        _add_symbol_info(doc, sym, _KIND_CONSTRUCTOR)
        return

    if func.is_fallback:
        sym = _symbol_str(rel_path, contract_name, "fallback().")
        _add_def_occurrence(doc, sym)
        _add_symbol_info(doc, sym, _KIND_FUNCTION)
        return

    if func.is_receive:
        sym = _symbol_str(rel_path, contract_name, "receive().")
        _add_def_occurrence(doc, sym)
        _add_symbol_info(doc, sym, _KIND_FUNCTION)
        return

    descriptor = f"{member_name}({_format_params(params_str)})."
    sym = _symbol_str(rel_path, contract_name, descriptor)
    _add_def_occurrence(doc, sym)

    si_docs: list[str] = []
    visibility = getattr(func, "visibility", "internal")
    if visibility in ("public", "external"):
        selector = compute_abi_selector(f"{member_name}({params_str})")
        si_docs.append(f"abi_selector:{selector}")

    _add_symbol_info(doc, sym, _KIND_FUNCTION, si_docs or None)


def _emit_event(doc: Any, rel_path: str, contract_name: str, event: Any) -> None:
    event_name, params_str = _parse_canonical(event.canonical_name)
    descriptor = f"{event_name}({_format_params(params_str)})."
    sym = _symbol_str(rel_path, contract_name, descriptor)
    _add_def_occurrence(doc, sym)
    _add_symbol_info(doc, sym, _KIND_EVENT)


def _emit_modifier(doc: Any, rel_path: str, contract_name: str, mod: Any) -> None:
    mod_name, params_str = _parse_canonical(mod.canonical_name)
    descriptor = f"{mod_name}({_format_params(params_str)})."
    sym = _symbol_str(rel_path, contract_name, descriptor)
    _add_def_occurrence(doc, sym)
    _add_symbol_info(doc, sym, _KIND_MODIFIER)


def _emit_state_var(doc: Any, rel_path: str, contract_name: str, var: Any) -> None:
    sym = _symbol_str(rel_path, contract_name, f"{var.name}.")
    _add_def_occurrence(doc, sym)
    _add_symbol_info(doc, sym, _KIND_FIELD)

    # Public state vars auto-generate a getter function in Solidity
    if getattr(var, "visibility", "internal") == "public":
        getter_sym = _symbol_str(rel_path, contract_name, f"{var.name}().")
        _add_def_occurrence(doc, getter_sym)
        selector = compute_abi_selector(f"{var.name}()")
        _add_symbol_info(doc, getter_sym, _KIND_FUNCTION, [f"abi_selector:{selector}"])


def _emit_custom_error(doc: Any, rel_path: str, contract_name: str, err: Any) -> None:
    err_name, params_str = _parse_canonical(err.canonical_name)
    descriptor = f"{err_name}({_format_params(params_str)})."
    sym = _symbol_str(rel_path, contract_name, descriptor)
    _add_def_occurrence(doc, sym)
    _add_symbol_info(doc, sym, _KIND_ERROR)


def _emit_inherited_functions(
    doc: Any, rel_path: str, contract_name: str, contract: Any
) -> None:
    """Emit ForwardDef occurrences for inherited functions not overridden here.

    Slither's functions_inherited includes all accessible inherited functions,
    including overridden ones. We skip any whose member signature matches a
    function in functions_declared (i.e., the contract provides its own override).
    """
    declared_sigs = {
        _member_sig(f.canonical_name)
        for f in contract.functions_declared
        if not (f.is_constructor or f.is_fallback or f.is_receive)
    }

    for func in getattr(contract, "functions_inherited", []):
        if func.is_constructor or func.is_fallback or func.is_receive:
            continue
        if _member_sig(func.canonical_name) in declared_sigs:
            continue  # overridden — skip

        member_name, params_str = _parse_canonical(func.canonical_name)
        descriptor = f"{member_name}({_format_params(params_str)})."
        sym = _symbol_str(rel_path, contract_name, descriptor)
        _add_def_occurrence(doc, sym, _SCIP_ROLE_FORWARD_DEF)
        _add_symbol_info(doc, sym, _KIND_FUNCTION)


def _emit_contract(doc: Any, rel_path: str, contract: Any) -> None:
    contract_name = contract.name

    # Contract definition
    contract_sym = _symbol_str(rel_path, contract_name, ".")
    _add_def_occurrence(doc, contract_sym)
    _add_symbol_info(doc, contract_sym, _contract_kind(contract))

    for func in contract.functions_declared:
        _emit_function(doc, rel_path, contract_name, func)

    for event in contract.events_declared:
        _emit_event(doc, rel_path, contract_name, event)

    for mod in contract.modifiers_declared:
        _emit_modifier(doc, rel_path, contract_name, mod)

    for var in contract.state_variables_declared:
        _emit_state_var(doc, rel_path, contract_name, var)

    for err in getattr(contract, "custom_errors_declared", []):
        _emit_custom_error(doc, rel_path, contract_name, err)

    _emit_inherited_functions(doc, rel_path, contract_name, contract)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def emit_index(slither_obj: Any, root_path: Path) -> Any:
    """Convert a slither object to a SCIP Index protobuf.

    Accepts any duck-typed object providing slither's Contract/Function/Event/
    Modifier/Variable interface. Real slither is not imported here.

    The root_path is used to compute relative file paths from absolute paths
    returned by contract.source_mapping.filename.absolute.

    Returns a scip_pb2.Index with:
    - One Document per .sol source file
    - DEF occurrences for contracts, functions, events, modifiers, state vars, errors
    - ForwardDef occurrences for inherited-but-not-overridden functions
    - ABI selectors in SymbolInformation.documentation for public/external functions
    """
    index = scip_pb2.Index()  # type: ignore[attr-defined]

    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = "scip-solidity"
    metadata.tool_info.version = "0.1.0"
    metadata.project_root = root_path.as_uri()
    index.metadata.CopyFrom(metadata)

    docs: dict[str, Any] = {}

    def get_doc(rel_path: str) -> Any:
        if rel_path not in docs:
            doc = index.documents.add()
            doc.relative_path = rel_path
            doc.language = "solidity"
            docs[rel_path] = doc
        return docs[rel_path]

    for contract in slither_obj.contracts:
        abs_path = str(contract.source_mapping.filename.absolute)
        rel_path = str(Path(abs_path).relative_to(root_path))
        doc = get_doc(rel_path)
        _emit_contract(doc, rel_path, contract)

    return index


# ---------------------------------------------------------------------------
# Convenience wrapper (used by regen.sh and tests that have slither available)
# ---------------------------------------------------------------------------


def _make_aggregator(root_path: Path) -> Path:
    """Create a temporary aggregator .sol that imports every .sol in root_path.

    Plain solc mode (foundry_ignore=True) requires a single file target.
    Importing all .sol files in one aggregator file lets slither parse the full
    project; Solidity's import system deduplicates files referenced multiple times.
    The caller is responsible for deleting the returned path when done.
    """
    sol_files = sorted(root_path.rglob("*.sol"))
    lines = ["// SPDX-License-Identifier: MIT", "pragma solidity ^0.8.20;"]
    for f in sol_files:
        rel = f.relative_to(root_path)
        lines.append(f'import "./{rel}";')
    agg_path = root_path / "_scip_all.sol"
    agg_path.write_text("\n".join(lines) + "\n")
    return agg_path


def emit_index_from_path(root_path: Path, **slither_kwargs: Any) -> Any:
    """Load slither from root_path and emit a SCIP Index.

    Requires slither-analyzer (not a runtime dep — fixture regen only).
    Pass foundry_ignore=True to skip Foundry detection and use plain solc.

    When foundry_ignore=True, creates a temporary aggregator .sol that imports
    all .sol files so slither can analyse a directory in plain solc mode.
    """
    try:
        from slither import Slither
    except ImportError as exc:
        raise ImportError(
            "slither-analyzer is not installed. "
            "Install it manually: pip install slither-analyzer"
        ) from exc

    if slither_kwargs.get("foundry_ignore") and root_path.is_dir():
        agg_path = _make_aggregator(root_path)
        try:
            slither_obj = Slither(str(agg_path), **slither_kwargs)
        finally:
            agg_path.unlink(missing_ok=True)
    else:
        slither_obj = Slither(str(root_path), **slither_kwargs)

    return emit_index(slither_obj, root_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Emit Solidity SCIP index from slither AST"
    )
    parser.add_argument(
        "--project-root", required=True, help="Path to Solidity project root"
    )
    parser.add_argument("--output", required=True, help="Path to output index.scip")
    parser.add_argument(
        "--foundry-ignore",
        action="store_true",
        default=False,
        help="Skip Foundry detection and use plain solc (needed if forge is not installed)",
    )
    parser.add_argument("--solc", default=None, help="Path to solc binary")
    args = parser.parse_args()

    try:
        from slither import Slither
    except ImportError:
        print(
            "slither-analyzer is not installed. "
            "Install it manually: pip install slither-analyzer",
            file=sys.stderr,
        )
        sys.exit(1)

    root = Path(args.project_root).resolve()
    output = Path(args.output)

    kwargs: dict[str, Any] = {}
    if args.foundry_ignore:
        kwargs["foundry_ignore"] = True
    if args.solc:
        kwargs["solc"] = args.solc

    print(f"Running slither on {root}...", file=sys.stderr)
    if kwargs.get("foundry_ignore") and root.is_dir():
        agg_path = _make_aggregator(root)
        try:
            slither_obj = Slither(str(agg_path), **kwargs)
        finally:
            agg_path.unlink(missing_ok=True)
    else:
        slither_obj = Slither(str(root), **kwargs)

    print("Emitting SCIP index...", file=sys.stderr)
    index = emit_index(slither_obj, root)

    output.write_bytes(index.SerializeToString())

    n_docs = len(index.documents)
    n_occs = sum(len(doc.occurrences) for doc in index.documents)
    print(f"Wrote {output}: {n_docs} docs, {n_occs} occurrences", file=sys.stderr)


if __name__ == "__main__":
    _main()
