# GIM-102 — Symbol Index Python Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first real content extractor — `SymbolIndexPython` — reading pre-generated `.scip` files for Python codebases, ingesting into Tantivy + Neo4j via 3-phase bootstrap, and exposing `palace.code.find_references` composite tool with 3-state distinction.

**Architecture:** Operator runs `npx @sourcegraph/scip-python` outside the container; palace-mcp reads the `.scip` file via `PALACE_SCIP_INDEX_PATHS` Settings dict. `SymbolIndexPython` extractor uses all 101a foundation substrate (TantivyBridge, BoundedInDegreeCounter, ensure_custom_schema, eviction, IngestCheckpoint, circuit breaker). `palace.code.find_references` composite tool queries Tantivy + Neo4j with 3-state distinction (genuinely-zero / never-indexed / evicted).

**Tech Stack:** Python 3.11+, `scip` PyPI package (Sourcegraph SCIP bindings), `protobuf>=4.25`, `tantivy-py`, Neo4j 5.26, FastMCP, pytest

**Predecessor:** `bb0e944` (develop tip, GIM-101a merge)
**Spec:** `docs/superpowers/specs/2026-04-27-101b-symbol-index-python-design.md` (rev1)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` | `parse_scip_file()` + `FindScipPath` resolver + SCIP iteration helpers |
| `services/palace-mcp/src/palace_mcp/extractors/symbol_index_python.py` | `SymbolIndexPython(BaseExtractor)` — 3-phase bootstrap using 101a substrate |
| `services/palace-mcp/src/palace_mcp/extractors/registry.py` | Add `symbol_index_python` registration (modify) |
| `services/palace-mcp/src/palace_mcp/code_composite.py` | Add `palace.code.find_references` composite tool (modify) |
| `services/palace-mcp/pyproject.toml` | Add `scip>=0.4.0` + `protobuf>=4.25` dependencies (modify) |
| `tests/extractors/unit/test_scip_parser.py` | Unit tests for SCIP parser + FindScipPath |
| `tests/extractors/unit/test_symbol_index_python.py` | Unit tests for SymbolIndexPython (mocked driver + bridge) |
| `tests/extractors/unit/test_find_references.py` | Unit tests for find_references 3-state logic |
| `tests/extractors/integration/test_symbol_index_python_integration.py` | Integration test with real Neo4j + Tantivy |
| `tests/extractors/integration/test_find_references_wire.py` | MCP wire-contract test (per GIM-91) for all 3 states |
| `tests/extractors/fixtures/` | Small synthetic `.scip` fixture for CI |

All paths are relative to repo root. Test files go under `services/palace-mcp/tests/`.

---

## Task 1: Pin dependencies — `scip` + `protobuf>=4.25`

**Files:**
- Modify: `services/palace-mcp/pyproject.toml`

- [ ] **Step 1: Add scip + protobuf to dependencies**

In `services/palace-mcp/pyproject.toml`, add to the `dependencies` array:

```toml
    "scip>=0.4.0",
    "protobuf>=4.25",
```

- [ ] **Step 2: Run uv sync to install**

Run: `cd services/palace-mcp && uv sync`
Expected: resolves and installs `scip` + `protobuf` without conflicts.

- [ ] **Step 3: Verify import works**

Run: `cd services/palace-mcp && uv run python -c "import scip.scip_pb2; print('scip OK')"`
Expected: `scip OK`

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/pyproject.toml services/palace-mcp/uv.lock
git commit -m "feat(GIM-102): T1 — pin scip>=0.4.0 + protobuf>=4.25

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 2: SCIP parser — `parse_scip_file` + `FindScipPath` + tests

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_scip_parser.py`

### Step 1: Write the failing tests

- [ ] **Step 1a: Create test file**

Create `services/palace-mcp/tests/extractors/unit/test_scip_parser.py`:

```python
"""Tests for SCIP parser and FindScipPath resolver."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from palace_mcp.extractors.scip_parser import (
    FindScipPath,
    ScipFileTooLargeError,
    ScipParseError,
    ScipPathRequiredError,
    parse_scip_file,
)


class TestFindScipPath:
    def test_override_takes_precedence(self) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {"gimle": "/default/path.scip"}
        result = FindScipPath.resolve("gimle", settings, override="/override/path.scip")
        assert result == Path("/override/path.scip")

    def test_settings_dict_lookup(self) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {"gimle": "/repos/gimle/scip/index.scip"}
        result = FindScipPath.resolve("gimle", settings)
        assert result == Path("/repos/gimle/scip/index.scip")

    def test_missing_project_raises(self) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {}
        with pytest.raises(ScipPathRequiredError) as exc_info:
            FindScipPath.resolve("unknown_project", settings)
        assert "unknown_project" in str(exc_info.value)
        assert exc_info.value.error_code == "scip_path_required"


class TestParseScipFile:
    def test_file_too_large_raises(self, tmp_path: Path) -> None:
        big_file = tmp_path / "big.scip"
        big_file.write_bytes(b"\x00" * (2 * 1024 * 1024))
        with pytest.raises(ScipFileTooLargeError) as exc_info:
            parse_scip_file(big_file, max_size_mb=1)
        assert exc_info.value.cap_mb == 1

    def test_corrupt_protobuf_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.scip"
        bad_file.write_bytes(b"\xff\xfe\xfd\xfc" * 100)
        with pytest.raises(ScipParseError):
            parse_scip_file(bad_file)

    def test_valid_empty_index(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.scip"
        empty_file.write_bytes(b"")
        result = parse_scip_file(empty_file)
        assert len(result.documents) == 0

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.scip"
        with pytest.raises(FileNotFoundError):
            parse_scip_file(missing)
```

- [ ] **Step 1b: Run tests to verify they fail**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser.py -v`
Expected: ImportError — `palace_mcp.extractors.scip_parser` does not exist yet.

### Step 2: Implement scip_parser.py

- [ ] **Step 2a: Create the module**

Create `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`:

```python
"""SCIP file parser + path resolver for symbol index extractors.

scip PyPI package provides protobuf bindings for Sourcegraph's SCIP format.
protobuf>=4.25 pinned for recursion-depth DoS fix + upb backend (handles
files >64 MiB that the pure-Python backend cannot).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import scip.scip_pb2 as scip_pb2
from google.protobuf.message import DecodeError

from palace_mcp.extractors.foundation.errors import ExtractorErrorCode

if TYPE_CHECKING:
    from palace_mcp.config import PalaceSettings


@dataclass
class ScipPathRequiredError(Exception):
    """No .scip path configured for this project."""

    project: str
    action_required: str
    error_code: str = ExtractorErrorCode.SCIP_PATH_REQUIRED.value

    def __post_init__(self) -> None:
        super().__init__(
            f"No .scip path for project {self.project!r}. {self.action_required}"
        )


@dataclass
class ScipFileTooLargeError(Exception):
    """SCIP file exceeds configured size cap."""

    path: Path
    size_mb: int
    cap_mb: int

    def __post_init__(self) -> None:
        super().__init__(
            f".scip file {self.path} is {self.size_mb} MB, exceeds cap {self.cap_mb} MB"
        )


@dataclass
class ScipParseError(Exception):
    """Protobuf decode failed on .scip file."""

    path: Path
    cause: str

    def __post_init__(self) -> None:
        super().__init__(f"Failed to parse {self.path}: {self.cause}")


class FindScipPath:
    """Resolve .scip file path for a project slug."""

    @staticmethod
    def resolve(
        project: str,
        settings: Any,
        override: str | None = None,
    ) -> Path:
        """Per-call override > Settings dict. Raises ScipPathRequiredError if neither."""
        if override is not None:
            return Path(override)
        path = settings.palace_scip_index_paths.get(project)
        if path is None:
            raise ScipPathRequiredError(
                project=project,
                action_required=(
                    f"Set PALACE_SCIP_INDEX_PATHS env var to JSON dict including "
                    f"'{project}' key, or pass scip_path argument to "
                    f"palace.ingest.run_extractor"
                ),
            )
        return Path(path)


def parse_scip_file(
    path: Path,
    max_size_mb: int = 500,
    timeout_s: int = 60,
) -> scip_pb2.Index:
    """Parse SCIP protobuf with size guard.

    Raises ScipFileTooLargeError if file exceeds max_size_mb.
    Raises ScipParseError on protobuf decode failure.
    Raises FileNotFoundError if path does not exist.
    """
    size = path.stat().st_size
    if size > max_size_mb * 1024 * 1024:
        raise ScipFileTooLargeError(
            path=path,
            size_mb=size // (1024 * 1024),
            cap_mb=max_size_mb,
        )
    data = path.read_bytes()
    index = scip_pb2.Index()
    try:
        index.ParseFromString(data)
    except DecodeError as e:
        raise ScipParseError(path=path, cause=str(e)) from e
    return index
```

- [ ] **Step 2b: Run tests**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 2c: Lint + typecheck**

Run: `cd services/palace-mcp && uv run ruff check src/palace_mcp/extractors/scip_parser.py && uv run mypy src/palace_mcp/extractors/scip_parser.py`
Expected: clean.

- [ ] **Step 2d: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/scip_parser.py \
      services/palace-mcp/tests/extractors/unit/test_scip_parser.py
git commit -m "feat(GIM-102): T2 — SCIP parser + FindScipPath + unit tests

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 3: SCIP occurrence iterator — `iter_scip_occurrences`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_scip_iterator.py`
- Create: `services/palace-mcp/tests/extractors/fixtures/` (tiny synthetic `.scip`)

### Step 1: Write the failing tests

- [ ] **Step 1a: Create fixture generator helper**

Create `services/palace-mcp/tests/extractors/fixtures/__init__.py` (empty).

Create `services/palace-mcp/tests/extractors/fixtures/scip_factory.py`:

```python
"""Factory for building synthetic SCIP Index protos for testing."""

from __future__ import annotations

from pathlib import Path

import scip.scip_pb2 as scip_pb2


def build_minimal_scip_index(
    *,
    language: str = "python",
    relative_path: str = "src/example.py",
    symbols: list[tuple[str, int]] | None = None,
) -> scip_pb2.Index:
    """Build a minimal SCIP Index with one document and configurable symbols.

    symbols: list of (symbol_string, scip_role_int) tuples.
    Default: one def symbol.
    """
    index = scip_pb2.Index()
    metadata = scip_pb2.Metadata()
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion
    metadata.tool_info.name = "test"
    metadata.tool_info.version = "0.0.1"
    metadata.project_root = "file:///test"
    index.metadata.CopyFrom(metadata)

    doc = index.documents.add()
    doc.relative_path = relative_path
    doc.language = language

    if symbols is None:
        symbols = [("scip-python python example . example_func .", 0)]

    for sym_str, role in symbols:
        occ = doc.occurrences.add()
        occ.range.extend([1, 0, 10])
        occ.symbol = sym_str
        occ.symbol_roles = role

    return index


def write_scip_fixture(index: scip_pb2.Index, path: Path) -> Path:
    """Serialize SCIP Index to a file."""
    path.write_bytes(index.SerializeToString())
    return path
```

- [ ] **Step 1b: Create iterator test**

Create `services/palace-mcp/tests/extractors/unit/test_scip_iterator.py`:

```python
"""Tests for SCIP occurrence iteration."""

from __future__ import annotations

from pathlib import Path

import scip.scip_pb2 as scip_pb2

from palace_mcp.extractors.foundation.models import SymbolKind
from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file
from tests.extractors.fixtures.scip_factory import build_minimal_scip_index, write_scip_fixture


class TestIterScipOccurrences:
    def test_single_def(self, tmp_path: Path) -> None:
        index = build_minimal_scip_index(
            symbols=[("scip-python python example . MyClass .", 1)],
        )
        path = write_scip_fixture(index, tmp_path / "test.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="abc123"))
        assert len(occs) == 1
        assert occs[0].kind == SymbolKind.DEF
        assert "MyClass" in occs[0].symbol_qualified_name
        assert occs[0].file_path == "src/example.py"
        assert occs[0].commit_sha == "abc123"

    def test_multiple_roles(self, tmp_path: Path) -> None:
        index = build_minimal_scip_index(
            symbols=[
                ("scip-python python example . func_a .", 1),
                ("scip-python python example . func_b .", 0),
            ],
        )
        path = write_scip_fixture(index, tmp_path / "test.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="def456"))
        assert len(occs) == 2
        kinds = {o.kind for o in occs}
        assert SymbolKind.DEF in kinds or SymbolKind.USE in kinds

    def test_empty_index_yields_nothing(self, tmp_path: Path) -> None:
        index = scip_pb2.Index()
        path = write_scip_fixture(index, tmp_path / "empty.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="000"))
        assert occs == []

    def test_vendor_path_detected(self, tmp_path: Path) -> None:
        index = build_minimal_scip_index(
            relative_path=".venv/lib/something.py",
            symbols=[("scip-python python venv . pkg .", 0)],
        )
        path = write_scip_fixture(index, tmp_path / "vendor.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="v1"))
        assert len(occs) == 1
        assert ".venv/" in occs[0].file_path
```

- [ ] **Step 1c: Run tests to verify they fail**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_iterator.py -v`
Expected: ImportError — `iter_scip_occurrences` not yet defined.

### Step 2: Implement iter_scip_occurrences

- [ ] **Step 2a: Add to scip_parser.py**

Append to `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`:

```python
from collections.abc import Iterator

from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import Language, SymbolKind, SymbolOccurrence

_SCIP_ROLE_DEF = 1
_SCIP_ROLE_IMPORT = 2
_SCIP_ROLE_WRITE_ACCESS = 4
_SCIP_ROLE_READ_ACCESS = 8
_SCIP_ROLE_GENERATED = 16
_SCIP_ROLE_TEST = 32
_SCIP_ROLE_FORWARD_DEF = 64


def _scip_role_to_kind(symbol_roles: int) -> SymbolKind:
    """Map SCIP symbol_roles bitmask to SymbolKind."""
    if symbol_roles & _SCIP_ROLE_DEF:
        return SymbolKind.DEF
    if symbol_roles & _SCIP_ROLE_FORWARD_DEF:
        return SymbolKind.DECL
    if symbol_roles & _SCIP_ROLE_WRITE_ACCESS:
        return SymbolKind.ASSIGN
    return SymbolKind.USE


def _extract_qualified_name(scip_symbol: str) -> str:
    """Extract a human-readable qualified name from a SCIP symbol string.

    SCIP format: 'scip-python python <package> . <module> . <name> .'
    Strips the scheme prefix and trailing dots, joins components with '.'.
    """
    parts = scip_symbol.strip().split(" ")
    name_parts = [p for p in parts[2:] if p and p != "."]
    return ".".join(name_parts) if name_parts else scip_symbol


def iter_scip_occurrences(
    index: scip_pb2.Index,
    *,
    commit_sha: str,
    ingest_run_id: str = "",
) -> Iterator[SymbolOccurrence]:
    """Yield SymbolOccurrence from a parsed SCIP Index.

    Each SCIP Document maps to a file; each Occurrence within it maps to
    a SymbolOccurrence with file_path, line, col derived from the SCIP range.
    """
    for doc in index.documents:
        file_path = doc.relative_path
        for occ in doc.occurrences:
            if not occ.symbol or occ.symbol.startswith("local "):
                continue

            kind = _scip_role_to_kind(occ.symbol_roles)
            qname = _extract_qualified_name(occ.symbol)
            sym_id = symbol_id_for(qname)

            range_vals = list(occ.range)
            line = range_vals[0] if len(range_vals) > 0 else 0
            col_start = range_vals[1] if len(range_vals) > 1 else 0
            col_end = range_vals[2] if len(range_vals) > 2 else col_start

            if len(range_vals) == 4:
                col_end = range_vals[3]

            doc_key = f"{sym_id}:{file_path}:{line}:{col_start}"

            yield SymbolOccurrence(
                doc_key=doc_key,
                symbol_id=sym_id,
                symbol_qualified_name=qname,
                kind=kind,
                language=Language.PYTHON,
                file_path=file_path,
                line=line,
                col_start=col_start,
                col_end=col_end,
                importance=0.0,
                commit_sha=commit_sha,
                ingest_run_id=ingest_run_id,
            )
```

- [ ] **Step 2b: Run tests**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_iterator.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 2c: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/scip_parser.py \
      services/palace-mcp/tests/extractors/unit/test_scip_iterator.py \
      services/palace-mcp/tests/extractors/fixtures/
git commit -m "feat(GIM-102): T3 — SCIP occurrence iterator + fixture factory

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 4: `SymbolIndexPython` extractor — core implementation

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/symbol_index_python.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_symbol_index_python.py`

### Step 1: Write the failing tests

- [ ] **Step 1a: Create unit test file**

Create `services/palace-mcp/tests/extractors/unit/test_symbol_index_python.py`:

```python
"""Unit tests for SymbolIndexPython extractor (mocked driver + bridge)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext, ExtractorStats
from palace_mcp.extractors.symbol_index_python import SymbolIndexPython
from tests.extractors.fixtures.scip_factory import build_minimal_scip_index, write_scip_fixture


@pytest.fixture
def extractor() -> SymbolIndexPython:
    return SymbolIndexPython()


@pytest.fixture
def scip_fixture(tmp_path: Path) -> Path:
    index = build_minimal_scip_index(
        symbols=[
            ("scip-python python example . ClassA .", 1),
            ("scip-python python example . func_b .", 1),
            ("scip-python python example . func_b .", 0),
        ],
    )
    return write_scip_fixture(index, tmp_path / "test.scip")


@pytest.fixture
def run_ctx(tmp_path: Path, scip_fixture: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="test-project",
        group_id="project/test-project",
        repo_path=tmp_path,
        run_id="test-run-001",
        duration_ms=0,
        logger=MagicMock(),
    )


@pytest.fixture
def mock_settings(tmp_path: Path, scip_fixture: Path) -> MagicMock:
    settings = MagicMock()
    settings.palace_scip_index_paths = {"test-project": str(scip_fixture)}
    settings.palace_tantivy_index_path = str(tmp_path / "tantivy")
    settings.palace_tantivy_heap_mb = 50
    settings.palace_max_occurrences_total = 50_000_000
    settings.palace_max_occurrences_per_project = 10_000_000
    settings.palace_importance_threshold_use = 0.05
    settings.palace_max_occurrences_per_symbol = 5_000
    settings.palace_recency_decay_days = 30.0
    return settings


class TestSymbolIndexPythonMeta:
    def test_name(self, extractor: SymbolIndexPython) -> None:
        assert extractor.name == "symbol_index_python"

    def test_description_nonempty(self, extractor: SymbolIndexPython) -> None:
        assert len(extractor.description) > 10


class TestSymbolIndexPythonRun:
    @pytest.mark.asyncio
    async def test_missing_scip_path_returns_error(
        self, extractor: SymbolIndexPython, run_ctx: ExtractorRunContext
    ) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {}
        graphiti = AsyncMock()
        driver = AsyncMock()

        result = await extractor.run(graphiti=graphiti, ctx=run_ctx)
        # SymbolIndexPython should handle ScipPathRequiredError
        # and return ExtractorStats with 0 writes (or raise ExtractorError)
        # Exact behavior depends on implementation — test will be adjusted.

    @pytest.mark.asyncio
    async def test_scip_file_not_found_raises(
        self, extractor: SymbolIndexPython, run_ctx: ExtractorRunContext
    ) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {"test-project": "/nonexistent/path.scip"}
        # Test that run() raises or returns error envelope
```

Note: these tests establish the contract — the implementer will refine assertions based on the actual error-handling flow (the extractor calls `run()` which receives `graphiti` + `ctx`; the `SymbolIndexPython` must additionally receive `driver` and `settings` via a mechanism — see Step 2 for the design decision).

- [ ] **Step 1b: Run to verify failure**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_symbol_index_python.py -v`
Expected: ImportError — module does not exist yet.

### Step 2: Implement SymbolIndexPython

- [ ] **Step 2a: Create the extractor module**

Create `services/palace-mcp/src/palace_mcp/extractors/symbol_index_python.py`:

```python
"""SymbolIndexPython — first real content extractor on 101a foundation.

3-phase bootstrap reading pre-generated .scip files:
  Phase 1: defs + decls only (always runs)
  Phase 2: user-code uses above importance threshold (if budget < 50% used)
  Phase 3: vendor uses (only on large machines, budget < 30% used)

Uses 101a substrate: TantivyBridge, BoundedInDegreeCounter, ensure_custom_schema,
eviction, IngestCheckpoint, circuit breaker.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run,
    finalize_ingest_run,
    write_checkpoint,
)
from palace_mcp.extractors.foundation.circuit_breaker import (
    check_phase_budget,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.importance import (
    BoundedInDegreeCounter,
    importance_score,
)
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
    SymbolOccurrenceShadow,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.scip_parser import (
    FindScipPath,
    ScipPathRequiredError,
    iter_scip_occurrences,
    parse_scip_file,
)

logger = logging.getLogger(__name__)


class SymbolIndexPython(BaseExtractor):
    name: ClassVar[str] = "symbol_index_python"
    description: ClassVar[str] = (
        "Ingest Python symbols + occurrences from pre-generated SCIP file"
    )

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        # Access driver + settings from mcp_server module-level state
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()

        if driver is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available",
                recoverable=False,
                action="retry",
            )

        # 1. Idempotent schema bootstrap
        await ensure_custom_schema(driver)

        # 2. Create IngestRun
        await create_ingest_run(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            extractor_name=self.name,
        )

        try:
            # 3. Resolve .scip path
            scip_path = FindScipPath.resolve(
                ctx.project_slug, settings
            )

            # 4. Parse SCIP file
            scip_index = parse_scip_file(scip_path)

            # 5. Get commit SHA from repo path
            commit_sha = self._read_head_sha(ctx.repo_path)

            # 6. Iterate all occurrences
            all_occs = list(iter_scip_occurrences(
                scip_index,
                commit_sha=commit_sha,
                ingest_run_id=ctx.run_id,
            ))

            # 7. Build in-degree counter from USE occurrences
            counter = BoundedInDegreeCounter()
            for occ in all_occs:
                if occ.kind == SymbolKind.USE:
                    counter.increment(occ.symbol_qualified_name)

            # 8. 3-phase ingest
            tantivy_path = Path(settings.palace_tantivy_index_path)
            total_written = 0

            async with TantivyBridge(
                tantivy_path,
                heap_size_mb=settings.palace_tantivy_heap_mb,
            ) as bridge:
                # Phase 1: defs + decls (always)
                check_phase_budget(
                    nodes_written_so_far=total_written,
                    max_occurrences_total=settings.palace_max_occurrences_total,
                    phase="phase1_defs",
                )
                phase1_occs = [
                    o for o in all_occs
                    if o.kind in (SymbolKind.DEF, SymbolKind.DECL)
                ]
                p1 = await self._ingest_batch(
                    bridge, driver, phase1_occs, counter, ctx, settings
                )
                await bridge.commit_async()
                await write_checkpoint(
                    driver,
                    run_id=ctx.run_id,
                    project=ctx.project_slug,
                    phase="phase1_defs",
                    expected_doc_count=p1,
                )
                total_written += p1
                logger.info("Phase 1 (defs+decls): %d occurrences written", p1)

                # Phase 2: user-code uses (if budget < 50%)
                p2 = 0
                budget_used = total_written / max(
                    settings.palace_max_occurrences_per_project, 1
                )
                if budget_used < 0.5:
                    check_phase_budget(
                        nodes_written_so_far=total_written,
                        max_occurrences_total=settings.palace_max_occurrences_total,
                        phase="phase2_user_uses",
                    )
                    phase2_occs = [
                        self._with_importance(o, counter, settings)
                        for o in all_occs
                        if o.kind == SymbolKind.USE
                        and not self._is_vendor(o.file_path)
                    ]
                    phase2_occs = [
                        o for o in phase2_occs
                        if o.importance >= settings.palace_importance_threshold_use
                    ]
                    p2 = await self._ingest_batch(
                        bridge, driver, phase2_occs, counter, ctx, settings
                    )
                    await bridge.commit_async()
                    await write_checkpoint(
                        driver,
                        run_id=ctx.run_id,
                        project=ctx.project_slug,
                        phase="phase2_user_uses",
                        expected_doc_count=p1 + p2,
                    )
                    total_written += p2
                    logger.info("Phase 2 (user uses): %d occurrences written", p2)

                # Phase 3: vendor uses (if budget < 30%)
                p3 = 0
                budget_used = total_written / max(
                    settings.palace_max_occurrences_per_project, 1
                )
                if budget_used < 0.3:
                    check_phase_budget(
                        nodes_written_so_far=total_written,
                        max_occurrences_total=settings.palace_max_occurrences_total,
                        phase="phase3_vendor_uses",
                    )
                    phase3_occs = [
                        self._with_importance(o, counter, settings)
                        for o in all_occs
                        if o.kind == SymbolKind.USE
                        and self._is_vendor(o.file_path)
                    ]
                    p3 = await self._ingest_batch(
                        bridge, driver, phase3_occs, counter, ctx, settings
                    )
                    await bridge.commit_async()
                    await write_checkpoint(
                        driver,
                        run_id=ctx.run_id,
                        project=ctx.project_slug,
                        phase="phase3_vendor_uses",
                        expected_doc_count=p1 + p2 + p3,
                    )
                    total_written += p3
                    logger.info("Phase 3 (vendor uses): %d occurrences written", p3)

            # 9. Persist counter
            counter_path = tantivy_path / "in_degree_counter.json"
            counter.to_disk(counter_path, run_id=ctx.run_id)

            # 10. Finalize IngestRun as success
            await finalize_ingest_run(
                driver, run_id=ctx.run_id, success=True
            )

            return ExtractorStats(
                nodes_written=total_written,
                edges_written=0,
            )

        except ScipPathRequiredError as e:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code=e.error_code,
            )
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCIP_PATH_REQUIRED,
                message=str(e),
                recoverable=False,
                action="manual_cleanup",
            ) from e
        except ExtractorError:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code="extractor_error",
            )
            raise
        except Exception as e:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code="unknown",
            )
            raise

    async def _ingest_batch(
        self,
        bridge: TantivyBridge,
        driver: object,
        occurrences: list[SymbolOccurrence],
        counter: BoundedInDegreeCounter,
        ctx: ExtractorRunContext,
        settings: object,
    ) -> int:
        """Write a batch of occurrences to Tantivy. Returns count written."""
        written = 0
        for occ in occurrences:
            await bridge.add_or_replace_async(occ)
            written += 1
        return written

    def _with_importance(
        self,
        occ: SymbolOccurrence,
        counter: BoundedInDegreeCounter,
        settings: object,
    ) -> SymbolOccurrence:
        """Recompute importance for a USE occurrence using the in-degree counter."""
        score = importance_score(
            cms_in_degree=counter.estimate(occ.symbol_qualified_name),
            file_path=occ.file_path,
            kind=occ.kind,
            last_seen_at=datetime.now(tz=timezone.utc),
            language=occ.language,
            primary_lang=Language.PYTHON,
            half_life_days=getattr(settings, "palace_recency_decay_days", 30.0),
        )
        return SymbolOccurrence(
            doc_key=occ.doc_key,
            symbol_id=occ.symbol_id,
            symbol_qualified_name=occ.symbol_qualified_name,
            kind=occ.kind,
            language=occ.language,
            file_path=occ.file_path,
            line=occ.line,
            col_start=occ.col_start,
            col_end=occ.col_end,
            importance=score,
            commit_sha=occ.commit_sha,
            ingest_run_id=occ.ingest_run_id,
        )

    @staticmethod
    def _is_vendor(file_path: str) -> bool:
        """Check if file path is vendor/third-party."""
        vendor_markers = [
            "node_modules/", "vendor/", ".venv/", "site-packages/",
            "__pycache__/", "dist/", "build/", "target/", ".gradle/",
        ]
        return any(marker in file_path for marker in vendor_markers)

    @staticmethod
    def _read_head_sha(repo_path: Path) -> str:
        """Read HEAD commit SHA from the repo. Falls back to 'unknown'."""
        head_file = repo_path / ".git" / "HEAD"
        try:
            ref = head_file.read_text().strip()
            if ref.startswith("ref: "):
                ref_path = repo_path / ".git" / ref[5:]
                return ref_path.read_text().strip()[:40]
            return ref[:40]
        except (FileNotFoundError, OSError):
            return "unknown"
```

- [ ] **Step 2b: Run tests**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_symbol_index_python.py -v`
Expected: tests pass (adjust mocks as needed for the actual `get_driver`/`get_settings` pattern).

- [ ] **Step 2c: Lint + typecheck**

Run: `cd services/palace-mcp && uv run ruff check src/palace_mcp/extractors/symbol_index_python.py && uv run mypy src/palace_mcp/extractors/symbol_index_python.py`

- [ ] **Step 2d: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/symbol_index_python.py \
      services/palace-mcp/tests/extractors/unit/test_symbol_index_python.py
git commit -m "feat(GIM-102): T4 — SymbolIndexPython extractor + unit tests

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 5: Register `symbol_index_python` in registry

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/registry.py`

- [ ] **Step 1: Add import and registration**

Add to `services/palace-mcp/src/palace_mcp/extractors/registry.py`:

```python
from palace_mcp.extractors.symbol_index_python import SymbolIndexPython
```

And add to the `EXTRACTORS` dict:

```python
    "symbol_index_python": SymbolIndexPython(),
```

- [ ] **Step 2: Run existing registry tests**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_registry.py -v`
Expected: PASS (no duplicate name conflicts).

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/registry.py
git commit -m "feat(GIM-102): T5 — register symbol_index_python in extractor registry

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 6: `palace.code.find_references` composite tool — 3-state distinction

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/code_composite.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_find_references.py`

### Step 1: Write the failing tests

- [ ] **Step 1a: Create test file**

Create `services/palace-mcp/tests/extractors/unit/test_find_references.py`:

```python
"""Tests for palace.code.find_references 3-state distinction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.code_composite import (
    FindReferencesRequest,
    _query_ingest_run_for_project,
    _query_eviction_record,
)


class TestFindReferencesRequest:
    def test_valid_request(self) -> None:
        req = FindReferencesRequest(qualified_name="foo.bar.baz")
        assert req.qualified_name == "foo.bar.baz"
        assert req.max_results == 100

    def test_empty_qn_rejected(self) -> None:
        with pytest.raises(Exception):
            FindReferencesRequest(qualified_name="")


class TestQueryIngestRun:
    @pytest.mark.asyncio
    async def test_no_ingest_run_returns_none(self) -> None:
        driver = AsyncMock()
        session = AsyncMock()
        driver.session.return_value.__aenter__ = AsyncMock(return_value=session)
        driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        result_mock = AsyncMock()
        result_mock.single.return_value = None
        session.run.return_value = result_mock

        result = await _query_ingest_run_for_project(driver, "test", "symbol_index_python")
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_run_returns_dict(self) -> None:
        driver = AsyncMock()
        session = AsyncMock()
        driver.session.return_value.__aenter__ = AsyncMock(return_value=session)
        driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        record = {"run_id": "r1", "success": True, "error_code": None}
        result_mock = AsyncMock()
        result_mock.single.return_value = record
        session.run.return_value = result_mock

        result = await _query_ingest_run_for_project(driver, "test", "symbol_index_python")
        assert result is not None
        assert result["success"] is True


class TestQueryEvictionRecord:
    @pytest.mark.asyncio
    async def test_no_eviction_returns_none(self) -> None:
        driver = AsyncMock()
        session = AsyncMock()
        driver.session.return_value.__aenter__ = AsyncMock(return_value=session)
        driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        result_mock = AsyncMock()
        result_mock.single.return_value = None
        session.run.return_value = result_mock

        result = await _query_eviction_record(driver, "foo.bar", "test")
        assert result is None
```

- [ ] **Step 1b: Run to verify failure**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_find_references.py -v`
Expected: ImportError — `FindReferencesRequest`, `_query_ingest_run_for_project`, `_query_eviction_record` not yet defined.

### Step 2: Implement find_references helpers + composite tool

- [ ] **Step 2a: Add helpers to code_composite.py**

Add to `services/palace-mcp/src/palace_mcp/code_composite.py` (before `register_code_composite_tools`):

```python
from palace_mcp.extractors.foundation.identifiers import symbol_id_for


class FindReferencesRequest(BaseModel):
    """Input model for palace.code.find_references."""

    qualified_name: str = Field(..., min_length=1, max_length=500)
    project: str | None = None
    max_results: int = Field(100, ge=1, le=500)


_QUERY_INGEST_RUN = """
MATCH (r:IngestRun {project: $project, extractor_name: $extractor_name})
WHERE r.success = true
RETURN r.run_id AS run_id, r.success AS success, r.error_code AS error_code
ORDER BY r.started_at DESC
LIMIT 1
"""

_QUERY_EVICTION_RECORD = """
MATCH (e:EvictionRecord {symbol_qualified_name: $qn, project: $project})
RETURN e.eviction_round AS eviction_round,
       e.evicted_at AS evicted_at,
       e.run_id AS run_id
LIMIT 1
"""

_COUNT_EVICTED_FOR_SYMBOL = """
MATCH (e:EvictionRecord {project: $project})
WHERE e.symbol_qualified_name STARTS WITH $qn_prefix
RETURN count(e) AS total_evicted
"""


async def _query_ingest_run_for_project(
    driver: object, project: str, extractor_name: str
) -> dict[str, object] | None:
    """Check if a successful IngestRun exists for this project+extractor."""
    async with driver.session() as session:  # type: ignore[union-attr]
        result = await session.run(
            _QUERY_INGEST_RUN,
            project=project,
            extractor_name=extractor_name,
        )
        record = await result.single()
        if record is None:
            return None
        return dict(record)


async def _query_eviction_record(
    driver: object, qualified_name: str, project: str
) -> dict[str, object] | None:
    """Check if an EvictionRecord exists for this symbol."""
    async with driver.session() as session:  # type: ignore[union-attr]
        result = await session.run(
            _QUERY_EVICTION_RECORD,
            qn=qualified_name,
            project=project,
        )
        record = await result.single()
        if record is None:
            return None
        eviction_data = dict(record)
        # Count total evicted for coverage_pct
        count_result = await session.run(
            _COUNT_EVICTED_FOR_SYMBOL,
            project=project,
            qn_prefix=qualified_name.split(".")[0],
        )
        count_record = await count_result.single()
        eviction_data["total_evicted"] = (
            count_record["total_evicted"] if count_record else 0
        )
        return eviction_data
```

- [ ] **Step 2b: Add find_references registration in `register_code_composite_tools`**

Inside `register_code_composite_tools`, add the new tool (after `palace_code_test_impact`):

```python
    _DESC_FIND_REFS = (
        "Find all references (occurrences) of a symbol by qualified_name. "
        "Returns 3-state distinction: genuinely-zero-refs (ok, no warning), "
        "project-not-indexed (warning: project_not_indexed), or "
        "partial-index-due-to-eviction (warning: partial_index + coverage_pct)."
    )

    @tool_decorator("palace.code.find_references", _DESC_FIND_REFS)
    async def palace_code_find_references(
        qualified_name: str,
        project: str | None = None,
        max_results: int = 100,
    ) -> dict[str, Any]:
        from palace_mcp.mcp_server import get_driver
        from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

        driver = get_driver()
        if driver is None:
            handle_tool_error(RuntimeError("Neo4j driver not initialised"))

        try:
            req = FindReferencesRequest(
                qualified_name=qualified_name,
                project=project,
                max_results=max_results,
            )
        except ValidationError as e:
            return {
                "ok": False,
                "error_code": "validation_error",
                "requested_qualified_name": qualified_name,
                "message": str(e),
            }

        resolved_project = req.project or default_project

        # State B check: never-indexed
        ingest_run = await _query_ingest_run_for_project(
            driver, resolved_project, "symbol_index_python"
        )
        if ingest_run is None or not ingest_run.get("success"):
            return {
                "ok": True,
                "occurrences": [],
                "total_found": 0,
                "warning": "project_not_indexed",
                "action_required": (
                    f"Run palace.ingest.run_extractor('symbol_index_python', "
                    f"'{resolved_project}') before relying on this answer"
                ),
            }

        # Search Tantivy for occurrences
        from palace_mcp.mcp_server import get_settings
        settings = get_settings()
        tantivy_path = Path(settings.palace_tantivy_index_path)
        sym_id = symbol_id_for(req.qualified_name)

        occurrences: list[dict[str, Any]] = []
        try:
            async with TantivyBridge(tantivy_path, heap_size_mb=settings.palace_tantivy_heap_mb) as bridge:
                raw_results = await bridge.search_by_symbol_id_async(
                    sym_id, limit=req.max_results + 1
                )
                truncated = len(raw_results) > req.max_results
                raw_results = raw_results[:req.max_results]
                occurrences = [
                    {
                        "file_path": r.file_path,
                        "line": r.line,
                        "col_start": r.col_start,
                        "col_end": r.col_end,
                        "kind": r.kind,
                        "qualified_name": r.symbol_qualified_name,
                    }
                    for r in raw_results
                ]
        except Exception:
            occurrences = []
            truncated = False

        # State C check: evicted
        eviction_info = await _query_eviction_record(
            driver, req.qualified_name, resolved_project
        )

        response: dict[str, Any] = {
            "ok": True,
            "requested_qualified_name": req.qualified_name,
            "project": resolved_project,
            "occurrences": occurrences,
            "total_found": len(occurrences) + (1 if truncated else 0),
            "truncated": truncated,
        }

        if eviction_info:
            total_evicted = eviction_info.get("total_evicted", 0)
            response["warning"] = "partial_index"
            response["eviction_note"] = (
                f"{total_evicted} occurrences evicted "
                f"(round={eviction_info['eviction_round']}); coverage incomplete"
            )
            total = len(occurrences) + total_evicted
            response["coverage_pct"] = int(
                100 * len(occurrences) / total
            ) if total > 0 else 100

        return response
```

- [ ] **Step 2c: Run tests**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_find_references.py -v`
Expected: all tests PASS.

- [ ] **Step 2d: Lint + typecheck**

Run: `cd services/palace-mcp && uv run ruff check src/palace_mcp/code_composite.py && uv run mypy src/palace_mcp/code_composite.py`

- [ ] **Step 2e: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/code_composite.py \
      services/palace-mcp/tests/extractors/unit/test_find_references.py
git commit -m "feat(GIM-102): T6 — palace.code.find_references 3-state composite tool

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 7: 250 MiB CI fixture decode round-trip test

**Files:**
- Create: `services/palace-mcp/tests/extractors/unit/test_scip_large_fixture.py`

- [ ] **Step 1: Write the test**

Create `services/palace-mcp/tests/extractors/unit/test_scip_large_fixture.py`:

```python
"""CI fixture: 250 MiB synthetic .scip decode round-trip.

Validates that protobuf>=4.25 upb backend handles large SCIP files
without hitting the 64 MiB pure-Python limit (Python-pro Finding F-J).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scip.scip_pb2 as scip_pb2

from palace_mcp.extractors.scip_parser import parse_scip_file


@pytest.mark.slow
def test_250mb_scip_decode_roundtrip(tmp_path: Path) -> None:
    """Build a ~250 MiB SCIP Index, serialize, parse back, verify counts."""
    index = scip_pb2.Index()
    metadata = scip_pb2.Metadata()
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion
    metadata.tool_info.name = "ci-stress"
    metadata.tool_info.version = "1.0.0"
    metadata.project_root = "file:///ci-test"
    index.metadata.CopyFrom(metadata)

    target_bytes = 250 * 1024 * 1024
    symbols_per_doc = 500
    doc_count = 0

    while index.ByteSize() < target_bytes:
        doc = index.documents.add()
        doc.relative_path = f"src/generated/module_{doc_count}.py"
        doc.language = "python"
        for j in range(symbols_per_doc):
            occ = doc.occurrences.add()
            occ.range.extend([j, 0, 80])
            occ.symbol = f"scip-python python gen . mod{doc_count} . func{j} ."
            occ.symbol_roles = 1 if j % 5 == 0 else 0
        doc_count += 1

    scip_file = tmp_path / "large.scip"
    data = index.SerializeToString()
    scip_file.write_bytes(data)
    actual_mb = len(data) // (1024 * 1024)
    assert actual_mb >= 200, f"Fixture only {actual_mb} MiB, need >= 200"

    parsed = parse_scip_file(scip_file, max_size_mb=500)
    assert len(parsed.documents) == doc_count
    total_occs = sum(len(d.occurrences) for d in parsed.documents)
    assert total_occs == doc_count * symbols_per_doc
```

Note: mark with `@pytest.mark.slow` — configure `pytest.ini` or `pyproject.toml` to skip slow tests by default unless `--runslow` is passed. Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = ["slow: marks tests as slow (deselect with '-m \"not slow\"')"]
```

- [ ] **Step 2: Run test locally**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_large_fixture.py -v -m slow --timeout=120`
Expected: PASS (may take 30-60s to generate + serialize + parse 250 MiB).

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_scip_large_fixture.py \
      services/palace-mcp/pyproject.toml
git commit -m "test(GIM-102): T7 — 250 MiB SCIP decode round-trip CI fixture

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 8: Integration test — SymbolIndexPython with real Neo4j

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_symbol_index_python_integration.py`

- [ ] **Step 1: Write the integration test**

Create `services/palace-mcp/tests/extractors/integration/test_symbol_index_python_integration.py`:

```python
"""Integration test: SymbolIndexPython on real Neo4j + Tantivy.

Verifies end-to-end ingest from synthetic .scip through 3-phase bootstrap
to Tantivy query. Requires Neo4j running (docker compose --profile review).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.symbol_index_python import SymbolIndexPython
from tests.extractors.fixtures.scip_factory import (
    build_minimal_scip_index,
    write_scip_fixture,
)


@pytest.mark.integration
class TestSymbolIndexPythonIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle(
        self, neo4j_driver, tmp_path: Path
    ) -> None:
        """Ingest synthetic .scip, verify :IngestRun + :IngestCheckpoint in Neo4j."""
        # Build fixture with defs + uses
        index = build_minimal_scip_index(
            symbols=[
                ("scip-python python example . ClassA .", 1),
                ("scip-python python example . ClassA . __init__ .", 1),
                ("scip-python python example . helper .", 1),
                ("scip-python python example . ClassA .", 0),
                ("scip-python python example . helper .", 0),
                ("scip-python python example . helper .", 0),
            ],
        )
        scip_path = write_scip_fixture(index, tmp_path / "test.scip")

        # Mock settings
        settings = MagicMock()
        settings.palace_scip_index_paths = {"test-proj": str(scip_path)}
        settings.palace_tantivy_index_path = str(tmp_path / "tantivy")
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        ctx = ExtractorRunContext(
            project_slug="test-proj",
            group_id="project/test-proj",
            repo_path=tmp_path,
            run_id="integration-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexPython()
        graphiti = MagicMock()

        with patch("palace_mcp.extractors.symbol_index_python.get_driver", return_value=neo4j_driver), \
             patch("palace_mcp.extractors.symbol_index_python.get_settings", return_value=settings):
            (tmp_path / "tantivy").mkdir(exist_ok=True)
            stats = await extractor.run(graphiti=graphiti, ctx=ctx)

        assert stats.nodes_written >= 3  # at least 3 defs

        # Verify IngestRun in Neo4j
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid="integration-run-001",
            )
            record = await result.single()
            assert record is not None
            assert record["success"] is True

        # Verify IngestCheckpoint
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) RETURN c.phase AS phase",
                rid="integration-run-001",
            )
            records = await result.data()
            phases = {r["phase"] for r in records}
            assert "phase1_defs" in phases
```

- [ ] **Step 2: Run integration test**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_symbol_index_python_integration.py -v -m integration`
Expected: PASS (requires Neo4j running).

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_symbol_index_python_integration.py
git commit -m "test(GIM-102): T8 — SymbolIndexPython integration test with real Neo4j

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 9: MCP wire-contract test — find_references 3-state (per GIM-91)

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_find_references_wire.py`

- [ ] **Step 1: Write the wire-contract test**

Create `services/palace-mcp/tests/extractors/integration/test_find_references_wire.py`:

```python
"""MCP wire-contract test for palace.code.find_references (per GIM-91).

All 3 states must be reachable via real streamablehttp_client.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.wire
class TestFindReferencesWireContract:
    @pytest.mark.asyncio
    async def test_state_b_never_indexed(self, mcp_client) -> None:
        """Query a project that has never been indexed → project_not_indexed."""
        result = await mcp_client.call_tool(
            "palace.code.find_references",
            arguments={
                "qualified_name": "nonexistent.symbol",
                "project": "never-indexed-project",
            },
        )
        data = mcp_client.parse_result(result)
        assert data["ok"] is True
        assert data["warning"] == "project_not_indexed"
        assert data["total_found"] == 0
        assert "action_required" in data

    @pytest.mark.asyncio
    async def test_state_a_genuinely_zero_refs(self, mcp_client, indexed_project) -> None:
        """Query a symbol that exists but has no callers → empty, no warning."""
        result = await mcp_client.call_tool(
            "palace.code.find_references",
            arguments={
                "qualified_name": "isolated_function_no_refs",
                "project": indexed_project,
            },
        )
        data = mcp_client.parse_result(result)
        assert data["ok"] is True
        assert data["total_found"] == 0
        assert "warning" not in data

    @pytest.mark.asyncio
    async def test_state_c_evicted(self, mcp_client, evicted_project) -> None:
        """Query a symbol with EvictionRecord → partial_index + coverage_pct."""
        result = await mcp_client.call_tool(
            "palace.code.find_references",
            arguments={
                "qualified_name": "evicted_symbol",
                "project": evicted_project,
            },
        )
        data = mcp_client.parse_result(result)
        assert data["ok"] is True
        assert data.get("warning") == "partial_index"
        assert "coverage_pct" in data

    @pytest.mark.asyncio
    async def test_dedup_pattern_21(self, mcp_client) -> None:
        """palace.code.find_references appears exactly once in tools/list (Pattern #21)."""
        tools = await mcp_client.list_tools()
        find_refs_tools = [
            t for t in tools if t.name == "palace.code.find_references"
        ]
        assert len(find_refs_tools) == 1
```

- [ ] **Step 2: Run wire test**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_find_references_wire.py -v -m "integration and wire"`
Expected: PASS (requires full palace-mcp running with MCP transport).

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_find_references_wire.py
git commit -m "test(GIM-102): T9 — MCP wire-contract test for find_references 3-state (GIM-91)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Task 10: Documentation — CLAUDE.md operator workflow + README

**Files:**
- Modify: `CLAUDE.md` (add operator workflow for scip-python + PALACE_SCIP_INDEX_PATHS)
- Modify: `services/palace-mcp/README.md` (if exists; add symbol-index extractor section)

- [ ] **Step 1: Add operator workflow to CLAUDE.md**

In `CLAUDE.md`, under the `### Registered extractors` section, add:

```markdown
- `symbol_index_python` — Python symbol indexer. Reads pre-generated `.scip`
  file (produced by `npx @sourcegraph/scip-python` outside the container).
  Writes `:Symbol` + `:SymbolOccurrenceShadow` nodes to Neo4j and indexes
  occurrences in Tantivy. 3-phase bootstrap: defs/decls → user uses → vendor
  uses. Query via `palace.code.find_references(qualified_name, project)`.
```

In `CLAUDE.md`, under `### Running an extractor` section, add a new subsection:

```markdown
### Operator workflow: Python symbol index

1. Generate `.scip` file outside the container:
   ```bash
   cd /repos/gimle
   npx @sourcegraph/scip-python index --output ./scip/index.scip
   ```

2. Set env var for palace-mcp container:
   ```
   PALACE_SCIP_INDEX_PATHS='{"gimle":"/repos/gimle/scip/index.scip"}'
   ```

3. Run the extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_python", project="gimle")
   ```

4. Query references:
   ```
   palace.code.find_references(qualified_name="register_code_tools", project="gimle")
   ```
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(GIM-102): T10 — operator workflow for Python symbol index

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Full lint + test gate (pre-handoff to CR)

- [ ] **Run full lint + typecheck + test suite**

```bash
cd services/palace-mcp
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/ -v -m "not slow and not integration"
```

Expected: all green.

- [ ] **Push branch**

```bash
git push -u origin feature/101b-symbol-index-python
```

---

## Acceptance Checklist (from spec)

| # | Criterion | Task |
|---|-----------|------|
| 1 | `scip>=0.4.0` + `protobuf>=4.25` pinned | T1 |
| 2 | `parse_scip_file` size cap + protobuf error envelope | T2 |
| 3 | `FindScipPath.resolve` with ScipPathRequiredError | T2 |
| 4 | `SymbolIndexPython` 3-phase on real `.scip` | T4, T8 |
| 5 | Restart-survivability (doc_key uniqueness) | T8 integration |
| 6 | `find_references` 3-state distinction | T6, T9 |
| 7 | MCP wire-contract test (GIM-91) | T9 |
| 8 | Pattern #21 dedup | T9 |
| 9 | CR + Opus + QA passed | T7-T10 (downstream phases) |
