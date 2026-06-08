"""
IndexStore direct-read via ctypes/libIndexStore.dylib (GIM-1167 F1B-SPIKE-V2).

Queries caller occurrences from DerivedData IndexStoreDB without sourcekit-lsp.
Uses the _f (function-pointer) variants of the IndexStore C API, which accept
regular C function pointers and are compatible with ctypes without ObjC blocks.

IndexStore v5 on-disk layout::

    <store_path>/
        v5/units/*.IDXU   – compiled-unit descriptors
        v5/records/*.IDXR – per-source-file symbol occurrence records

Query strategy:

1. Iterate every unit in the store.
2. For each unit, walk its RECORD dependencies to discover
   ``(record_name, file_path)`` pairs.
3. For each unseen record, open a record reader and search for occurrences of
   the target symbol by short name.
4. Collect non-definition occurrences as :class:`CallerRecord` instances.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IndexStore symbol-role bit flags (clang/include/indexstore/IndexStore.h)
# ---------------------------------------------------------------------------

_ROLE_DECLARATION = 1 << 0  # 1
_ROLE_DEFINITION = 1 << 1  # 2
_ROLE_REFERENCE = 1 << 2  # 4
_ROLE_READ = 1 << 3  # 8
_ROLE_WRITE = 1 << 4  # 16
_ROLE_CALL = 1 << 5  # 32

_UNIT_DEP_RECORD = 2  # indexstore_unit_dependency_kind_t::RECORD

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallerRecord:
    """A single caller-site occurrence of a symbol in the IndexStore."""

    source_file: str  # absolute path to the Swift/ObjC file (empty if unknown)
    record_name: str  # IndexStore record hash
    symbol_name: str  # short name as stored (e.g. "BalanceData")
    symbol_usr: str  # Unified Symbol Resolution identifier
    line: int  # 1-based line number
    col: int  # 1-based column number
    roles: int  # bitmask from indexstore_symbol_role_t


# ---------------------------------------------------------------------------
# libIndexStore path resolution
# ---------------------------------------------------------------------------


def _find_lib_path() -> str:
    env_override = os.environ.get("PALACE_INDEXSTORE_LIB_PATH")
    if env_override:
        return env_override

    candidates = [
        Path("/Applications/Xcode.app/Contents/SharedFrameworks")
        / "IndexStore.framework/Versions/A/IndexStore",
        Path("/Applications/Xcode-beta.app/Contents/SharedFrameworks")
        / "IndexStore.framework/Versions/A/IndexStore",
        Path.home() / ".swiftly/toolchains/swift-latest/usr/lib/libIndexStore.dylib",
    ]
    for p in candidates:
        if p.exists():
            return str(p)

    # Fallback: ask xcrun for the Swift toolchain path
    try:
        swift_bin = subprocess.check_output(
            ["xcrun", "--find", "swift"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        if swift_bin:
            usr = Path(swift_bin).parent.parent
            for candidate in [
                usr / "lib" / "libIndexStore.dylib",
                usr.parent
                / "SharedFrameworks/IndexStore.framework/Versions/A/IndexStore",
            ]:
                if candidate.exists():
                    return str(candidate)
    except Exception:
        pass

    raise RuntimeError(
        "libIndexStore.dylib not found. Ensure Xcode is installed or set "
        "PALACE_INDEXSTORE_LIB_PATH to the dylib path."
    )


# ---------------------------------------------------------------------------
# ctypes helpers
# ---------------------------------------------------------------------------


class _StringRef(ctypes.Structure):
    """Mirrors ``indexstore_string_ref_t = { const char *data; size_t length; }``."""

    _fields_ = [
        ("data", ctypes.c_void_p),
        ("length", ctypes.c_size_t),
    ]

    def decode(self) -> str:
        if not self.data or self.length == 0:
            return ""
        raw = (ctypes.c_char * self.length).from_address(self.data)
        return bytes(raw).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Library singleton with bound symbols
# ---------------------------------------------------------------------------


class _BoundLib:
    """Loaded + symbol-bound libIndexStore."""

    def __init__(self, path: str) -> None:
        lib = ctypes.CDLL(path)
        vp = ctypes.c_void_p
        u32 = ctypes.c_uint
        u64 = ctypes.c_uint64
        b = ctypes.c_bool
        cp = ctypes.c_char_p

        # store
        lib.indexstore_store_create.restype = vp
        lib.indexstore_store_create.argtypes = [cp, vp]
        lib.indexstore_store_dispose.restype = None  # dispose, not destroy
        lib.indexstore_store_dispose.argtypes = [vp]

        self.UnitApplierF = ctypes.CFUNCTYPE(b, vp, cp)
        lib.indexstore_store_units_apply_f.restype = b
        lib.indexstore_store_units_apply_f.argtypes = [vp, u32, vp, self.UnitApplierF]

        # unit reader
        lib.indexstore_unit_reader_create.restype = vp
        lib.indexstore_unit_reader_create.argtypes = [vp, cp, vp]
        lib.indexstore_unit_reader_dispose.restype = None
        lib.indexstore_unit_reader_dispose.argtypes = [vp]

        self.DepApplierF = ctypes.CFUNCTYPE(b, vp, vp)
        lib.indexstore_unit_reader_dependencies_apply_f.restype = b
        lib.indexstore_unit_reader_dependencies_apply_f.argtypes = [
            vp,
            vp,
            self.DepApplierF,
        ]

        # unit dependency
        lib.indexstore_unit_dependency_get_kind.restype = ctypes.c_int
        lib.indexstore_unit_dependency_get_kind.argtypes = [vp]
        lib.indexstore_unit_dependency_get_name.restype = _StringRef
        lib.indexstore_unit_dependency_get_name.argtypes = [vp]
        lib.indexstore_unit_dependency_get_filepath.restype = _StringRef
        lib.indexstore_unit_dependency_get_filepath.argtypes = [vp]

        # record reader
        lib.indexstore_record_reader_create.restype = vp
        lib.indexstore_record_reader_create.argtypes = [vp, cp, vp]
        lib.indexstore_record_reader_dispose.restype = None
        lib.indexstore_record_reader_dispose.argtypes = [vp]

        self.OccApplierF = ctypes.CFUNCTYPE(b, vp, vp)
        # Note: occurrences_in_symbol_name_apply_f absent in CommandLineTools version;
        # use occurrences_apply_f and filter by name in the applier callback.
        lib.indexstore_record_reader_occurrences_apply_f.restype = b
        lib.indexstore_record_reader_occurrences_apply_f.argtypes = [
            vp,
            vp,
            self.OccApplierF,
        ]

        # occurrence
        lib.indexstore_occurrence_get_symbol.restype = vp
        lib.indexstore_occurrence_get_symbol.argtypes = [vp]
        lib.indexstore_occurrence_get_roles.restype = u64
        lib.indexstore_occurrence_get_roles.argtypes = [vp]
        lib.indexstore_occurrence_get_line_col.restype = None
        lib.indexstore_occurrence_get_line_col.argtypes = [
            vp,
            ctypes.POINTER(u32),
            ctypes.POINTER(u32),
        ]

        # symbol
        lib.indexstore_symbol_get_name.restype = _StringRef
        lib.indexstore_symbol_get_name.argtypes = [vp]
        lib.indexstore_symbol_get_usr.restype = _StringRef
        lib.indexstore_symbol_get_usr.argtypes = [vp]

        self._lib = lib

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        return getattr(self._lib, name)


_bound: _BoundLib | None = None
_bound_lock = threading.Lock()


def _get_lib() -> _BoundLib:
    global _bound  # noqa: PLW0603
    if _bound is None:
        with _bound_lock:
            if _bound is None:
                _bound = _BoundLib(_find_lib_path())
    return _bound


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_callers(
    symbol_name: str,
    store_path: str,
    *,
    max_results: int = 500,
    include_definitions: bool = False,
) -> list[CallerRecord]:
    """Find occurrences of ``symbol_name`` across the IndexStore.

    By default, pure definition/declaration sites are excluded so the result
    reflects *callers and users* of the symbol rather than its declaration.

    Args:
        symbol_name:        Short symbol name to search (e.g. ``"BalanceData"``).
        store_path:         Absolute path to the IndexStoreDB DataStore directory.
        max_results:        Cap on returned :class:`CallerRecord` entries.
        include_definitions: When True, also include definition-only occurrences.

    Returns:
        List of :class:`CallerRecord`, deduplicated by ``(record_name, line, col)``.
    """
    lb = _get_lib()

    store = lb.indexstore_store_create(store_path.encode(), None)
    if not store:
        raise RuntimeError(f"indexstore_store_create failed for: {store_path}")

    try:
        return _query(lb, store, symbol_name, max_results, include_definitions)
    finally:
        lb.indexstore_store_dispose(store)


def _query(
    lb: _BoundLib,
    store: int,
    symbol_name: str,
    max_results: int,
    include_definitions: bool,
) -> list[CallerRecord]:
    """Inner query: collect unit names → record map → occurrence list."""

    # ------------------------------------------------------------------ #
    # Pass 1 – collect all unit names                                      #
    # ------------------------------------------------------------------ #

    unit_names: list[str] = []

    @lb.UnitApplierF  # type: ignore[untyped-decorator]
    def _unit_applier(_ctx: int, name_bytes: bytes | None) -> bool:
        if name_bytes:
            unit_names.append(name_bytes.decode("utf-8", errors="replace"))
        return True

    lb.indexstore_store_units_apply_f(store, 0, None, _unit_applier)

    # ------------------------------------------------------------------ #
    # Pass 2 – for each unit, map record_name → source_file_path           #
    # ------------------------------------------------------------------ #

    record_to_file: dict[str, str] = {}

    @lb.DepApplierF  # type: ignore[untyped-decorator]
    def _dep_applier(_ctx: int, dep: int) -> bool:
        kind = lb.indexstore_unit_dependency_get_kind(dep)
        if kind == _UNIT_DEP_RECORD:
            rec = lb.indexstore_unit_dependency_get_name(dep).decode()
            fp = lb.indexstore_unit_dependency_get_filepath(dep).decode()
            if rec and rec not in record_to_file:
                record_to_file[rec] = fp
        return True

    for unit_name in unit_names:
        reader = lb.indexstore_unit_reader_create(store, unit_name.encode(), None)
        if not reader:
            continue
        lb.indexstore_unit_reader_dependencies_apply_f(reader, None, _dep_applier)
        lb.indexstore_unit_reader_dispose(reader)

    # ------------------------------------------------------------------ #
    # Pass 3 – search each record for symbol_name occurrences              #
    # ------------------------------------------------------------------ #

    results: list[CallerRecord] = []
    seen_occ: set[tuple[str, int, int]] = set()

    # Shared mutable state for the occurrence callback (avoids per-iteration closure).
    # Using occurrences_apply_f (iterate all) + name filter because
    # occurrences_in_symbol_name_apply_f is absent in the CommandLineTools dylib.
    _ctx_state: dict[str, str] = {"file": "", "rec": ""}

    @lb.OccApplierF  # type: ignore[untyped-decorator]
    def _occ_applier(_ctx: int, occ: int) -> bool:
        if len(results) >= max_results:
            return False

        sym = lb.indexstore_occurrence_get_symbol(occ)
        if not sym:
            return True

        # Name filter — only proceed if this occurrence is for our target symbol
        sym_name_ref = lb.indexstore_symbol_get_name(sym)
        if sym_name_ref.length != len(symbol_name):
            return True
        sym_name = sym_name_ref.decode()
        if sym_name != symbol_name:
            return True

        roles = int(lb.indexstore_occurrence_get_roles(occ))
        is_def_only = bool(roles & (_ROLE_DEFINITION | _ROLE_DECLARATION)) and not bool(
            roles & (_ROLE_REFERENCE | _ROLE_CALL | _ROLE_READ | _ROLE_WRITE)
        )
        if is_def_only and not include_definitions:
            return True

        line_out = ctypes.c_uint(0)
        col_out = ctypes.c_uint(0)
        lb.indexstore_occurrence_get_line_col(
            occ, ctypes.byref(line_out), ctypes.byref(col_out)
        )
        line = int(line_out.value)
        col = int(col_out.value)

        key = (_ctx_state["rec"], line, col)
        if key in seen_occ:
            return True
        seen_occ.add(key)

        sym_usr = lb.indexstore_symbol_get_usr(sym).decode()

        results.append(
            CallerRecord(
                source_file=_ctx_state["file"],
                record_name=_ctx_state["rec"],
                symbol_name=sym_name,
                symbol_usr=sym_usr,
                line=line,
                col=col,
                roles=roles,
            )
        )
        return True

    seen_records: set[str] = set()
    for rec_name, file_path in record_to_file.items():
        if len(results) >= max_results:
            break
        if rec_name in seen_records:
            continue
        seen_records.add(rec_name)

        _ctx_state["file"] = (
            file_path  # update shared state BEFORE each synchronous call
        )
        _ctx_state["rec"] = rec_name

        rec_reader = lb.indexstore_record_reader_create(store, rec_name.encode(), None)
        if not rec_reader:
            continue
        lb.indexstore_record_reader_occurrences_apply_f(rec_reader, None, _occ_applier)
        lb.indexstore_record_reader_dispose(rec_reader)

    logger.info(
        "indexstore.find_callers(%r): %d occurrences from %d/%d records",
        symbol_name,
        len(results),
        len(seen_records),
        len(record_to_file),
    )
    return results
