# symbol_index_java — JVM extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Third production extractor `symbol_index_java` covering Java + Kotlin via scip-java, proving foundation substrate lang-agnosticism on a third language family.

**Architecture:** Near-symmetric copy of `symbol_index_typescript.py`. Foundation substrate (scip_parser.py, checkpoint, circuit breaker, Tantivy bridge) already lang-agnostic since GIM-104. Only additions: `JAVA` Language enum entry, JVM language maps in scip_parser.py, extractor class + registration, vendored JVM fixture with 7 source files, tests.

**Tech Stack:** Python 3.13, palace-mcp extractor framework (GIM-101a substrate), SCIP protobuf, Tantivy full-text, Neo4j 5.x, pytest, scip-java (external, not in Docker).

**Predecessor SHA:** `54691a7` (GIM-104 merged to develop)

---

## Task 0: Q1 FQN Verification for JVM (CTO — done in Phase 1.0)

**Verification result:** SCIP descriptor grammar (scip.proto) is language-agnostic. scip-java uses scheme `semanticdb` (not `scip-java`) and manager `maven`. This differs from scip-python (`scip-python python`) and scip-typescript (`scip-typescript npm`), but `_extract_qualified_name()` Variant B handles it correctly: it strips the first 4 space-separated tokens (scheme + manager + package-name + version) regardless of their values, keeping only the descriptor chain. Descriptor suffixes (`/` namespace, `#` type, `.` term, `().` method, `[]` type-param) are identical across all SCIP indexers.

**Source:** Verified from `ScipSemanticdb.java` source code (`typedSymbol()` method) and scip-java test snapshots (`sourcegraph/scip-java`).

JVM edge cases verified:
- **Nested classes:** `Outer#Inner#` — standard `#` type descriptor nesting. scip-java operates at source level (javac plugin), not bytecode — no `$` mangling.
- **Anonymous inner classes:** Become `local N` symbols — already filtered by `occ.symbol.startswith("local ")` check in `iter_scip_occurrences()`.
- **Generics:** `Cache#[K]`, `Cache#[V]` — type-param descriptors `[X]`, same as TypeScript `C#[T]`.
- **Kotlin extension functions:** Regular method descriptors on a file-level class (e.g., `GreeterKt#greet().`).
- **Kotlin companion objects:** `MyClass#Companion#` — nested type descriptor.
- **Kotlin top-level functions:** File-level class descriptor `LoggerKt#` + method descriptor.
- **Kotlin suspend/sealed/inline:** No special descriptor — standard type/method descriptors.
- **Kotlin pipeline:** scip-kotlin emits SemanticDB → `scip-java index-semanticdb` converts. Same scheme `semanticdb`, manager `maven`.
- **Local project symbols:** Package fields are `. .` (two dots) — `_extract_qualified_name()` filters standalone `.` correctly.
- **External deps:** E.g., `jdk 11 java/lang/String#` — produces `jdk java/lang/String#` after version strip.

**Decision:** No JVM-specific normalization rules needed. Variant B works as-is. The `_SCIP_LANGUAGE_MAP` needs `"java"` and `"kotlin"` entries; `_language_from_path()` needs `.java`, `.kt`, `.kts` extensions.

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py` | `SymbolIndexJava` extractor class (symmetric to TS) |
| `services/palace-mcp/tests/extractors/unit/test_symbol_index_java.py` | Unit tests (mocked driver + bridge) |
| `services/palace-mcp/tests/extractors/unit/test_symbol_index_java_real_fixture.py` | Real-fixture tests loading committed `.scip` |
| `services/palace-mcp/tests/extractors/integration/test_symbol_index_java_integration.py` | Integration tests (real Neo4j via compose reuse) |
| `tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/User.java` | Regular class, public/private methods |
| `tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Cache.java` | Generic `<K, V>` |
| `tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Logger.kt` | Top-level + companion object |
| `tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Greeter.kt` | Extension fun + suspend fun |
| `tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Sealed.kt` | Sealed class hierarchy |
| `tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Inner.java` | Nested + anonymous inner classes |
| `tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Main.java` | Cross-package imports + uses |
| `tests/extractors/fixtures/jvm-mini-project/build.gradle.kts` | Minimal Gradle config for scip-java |
| `tests/extractors/fixtures/jvm-mini-project/index.scip` | Pre-generated SCIP index (committed binary) |
| `tests/extractors/fixtures/jvm-mini-project/REGEN.md` | Instructions to regenerate fixture |

All fixture paths are relative to `services/palace-mcp/`.

### Modified files

| File | Change |
|------|--------|
| `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py` | Add `JAVA = "java"` to Language enum |
| `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` | Add `"java"` and `"kotlin"` to `_SCIP_LANGUAGE_MAP`; add `.java`, `.kt`, `.kts` to `_language_from_path()` |
| `services/palace-mcp/src/palace_mcp/extractors/registry.py` | Import + register `SymbolIndexJava` |
| `services/palace-mcp/tests/extractors/fixtures/scip_factory.py` | Add `build_jvm_scip_index()` factory |
| `Makefile` | Add `JVM_FIXTURE_DIR` variable + `regen-jvm-fixture` target |
| `CLAUDE.md` | Add `symbol_index_java` to registered extractors section |

---

## Task 1: Add JAVA to Language enum + extend scip_parser language maps

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py:24-36`
- Modify: `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` (lines with `_SCIP_LANGUAGE_MAP` and `_language_from_path`)
- Test: `services/palace-mcp/tests/extractors/unit/test_models.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_scip_parser.py`

- [ ] **Step 1: Write failing test for Language.JAVA**

In `test_models.py`, add a test that `Language.JAVA` exists and has value `"java"`:

```python
def test_language_java_exists():
    assert Language.JAVA.value == "java"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_models.py::test_language_java_exists -v`
Expected: FAIL — `AttributeError: JAVA`

- [ ] **Step 3: Add JAVA to Language enum**

In `foundation/models.py`, add `JAVA = "java"` after `JAVASCRIPT = "javascript"` (line 30):

```python
class Language(str, Enum):
    """Source language for a symbol occurrence."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    RUST = "rust"
    SOLIDITY = "solidity"
    FUNC = "func"
    ANCHOR = "anchor"
    UNKNOWN = "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_models.py::test_language_java_exists -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for _SCIP_LANGUAGE_MAP and _language_from_path JVM entries**

In `test_scip_parser.py`, add:

```python
from palace_mcp.extractors.scip_parser import _SCIP_LANGUAGE_MAP, _language_from_path

def test_scip_language_map_java():
    assert _SCIP_LANGUAGE_MAP["java"] == Language.JAVA

def test_scip_language_map_kotlin():
    assert _SCIP_LANGUAGE_MAP["kotlin"] == Language.KOTLIN

def test_language_from_path_java():
    assert _language_from_path("src/main/java/com/example/User.java") == Language.JAVA

def test_language_from_path_kotlin():
    assert _language_from_path("src/main/kotlin/com/example/Logger.kt") == Language.KOTLIN

def test_language_from_path_kotlin_script():
    assert _language_from_path("build.gradle.kts") == Language.KOTLIN
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser.py -k "java or kotlin" -v`
Expected: FAIL — KeyError for `_SCIP_LANGUAGE_MAP` / wrong Language for `_language_from_path`

- [ ] **Step 7: Extend _SCIP_LANGUAGE_MAP and _language_from_path**

In `scip_parser.py`, update:

```python
_SCIP_LANGUAGE_MAP: dict[str, Language] = {
    "python": Language.PYTHON,
    "typescript": Language.TYPESCRIPT,
    "javascript": Language.JAVASCRIPT,
    "java": Language.JAVA,
    "kotlin": Language.KOTLIN,
}


def _language_from_path(relative_path: str) -> Language:
    """Fallback: derive language from file extension when doc.language is empty."""
    if relative_path.endswith((".ts", ".tsx")):
        return Language.TYPESCRIPT
    if relative_path.endswith((".js", ".jsx")):
        return Language.JAVASCRIPT
    if relative_path.endswith(".py"):
        return Language.PYTHON
    if relative_path.endswith(".java"):
        return Language.JAVA
    if relative_path.endswith((".kt", ".kts")):
        return Language.KOTLIN
    return Language.UNKNOWN
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser.py -k "java or kotlin" -v`
Expected: PASS (all 5 tests)

- [ ] **Step 9: Run full existing test suite to verify no regressions**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser.py tests/extractors/unit/test_models.py -v`
Expected: All existing tests still PASS

- [ ] **Step 10: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/foundation/models.py \
      services/palace-mcp/src/palace_mcp/extractors/scip_parser.py \
      services/palace-mcp/tests/extractors/unit/test_models.py \
      services/palace-mcp/tests/extractors/unit/test_scip_parser.py
git commit -m "feat(GIM-111): add Language.JAVA + JVM entries in scip_parser language maps"
```

---

## Task 2: Add build_jvm_scip_index() synthetic factory

**Files:**
- Modify: `services/palace-mcp/tests/extractors/fixtures/scip_factory.py`
- Test: inline — factory is tested via usage in Task 4+5

- [ ] **Step 1: Add build_jvm_scip_index() to scip_factory.py**

```python
def build_jvm_scip_index(
    *,
    relative_path: str = "src/main/java/com/example/Example.java",
    language: str = "java",
    symbols: list[tuple[str, int]] | None = None,
) -> Any:
    """Build a minimal SCIP Index for Java/Kotlin testing.

    Uses configurable language ('java' or 'kotlin') and scip-java as tool_info.name.
    """
    if symbols is None:
        symbols = [
            (
                "semanticdb maven com.example 1.0.0 com/example/Example#run().",
                1,
            )
        ]
    return build_minimal_scip_index(
        language=language,
        relative_path=relative_path,
        symbols=symbols,
    )
```

- [ ] **Step 2: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/scip_factory.py
git commit -m "feat(GIM-111): add build_jvm_scip_index() synthetic factory"
```

---

## Task 3: Create SymbolIndexJava extractor + register

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py`
- Modify: `services/palace-mcp/src/palace_mcp/extractors/registry.py`

- [ ] **Step 1: Create symbol_index_java.py**

This is a symmetric copy of `symbol_index_typescript.py` with these changes:
- Class name: `SymbolIndexJava`
- `name = "symbol_index_java"`
- `description`: mentions Java/Kotlin, .java/.kt/.kts, scip-java
- `primary_lang = Language.JAVA`
- `_is_vendor()`: already includes `"target/"` and `".gradle/"` (JVM vendor markers), verify they are present
- `_get_previous_error_code()`: query uses `extractor_name: 'symbol_index_java'`

```python
"""SymbolIndexJava — Java/Kotlin extractor on 101a foundation (GIM-111).

Symmetric copy of SymbolIndexTypeScript for JVM symbols.
3-phase bootstrap reading pre-generated .scip files produced by scip-java:
  Phase 1: defs + decls only (always runs)
  Phase 2: user-code uses above importance threshold (if budget < 50% used)
  Phase 3: vendor uses (only if budget < 30% used)

Uses 101a substrate: TantivyBridge, BoundedInDegreeCounter, ensure_custom_schema,
IngestRun lifecycle, circuit breaker.
"""

from __future__ import annotations

import logging
import os
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
    check_resume_budget,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.importance import (
    BoundedInDegreeCounter,
    importance_score,
)
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.scip_parser import (
    FindScipPath,
    ScipPathRequiredError,
    iter_scip_occurrences,
    parse_scip_file,
)
from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


class SymbolIndexJava(BaseExtractor):
    name: ClassVar[str] = "symbol_index_java"
    description: ClassVar[str] = (
        "Ingest Java/Kotlin symbols + occurrences from pre-generated SCIP "
        "file (scip-java) into Tantivy (full-text) and Neo4j (IngestRun + "
        "checkpoint). Handles .java/.kt/.kts in one pass. 3-phase bootstrap: "
        "defs/decls → user uses → vendor uses."
    )
    primary_lang: ClassVar[Language] = Language.JAVA

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()

        if driver is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available — call set_driver() before run_extractor",
                recoverable=False,
                action="retry",
            )
        if settings is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Settings not available — call set_settings() before run_extractor",
                recoverable=False,
                action="retry",
            )

        previous_error = await _get_previous_error_code(driver, ctx.project_slug)
        check_resume_budget(previous_error_code=previous_error)

        await ensure_custom_schema(driver)

        await create_ingest_run(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            extractor_name=self.name,
        )

        try:
            scip_path = FindScipPath.resolve(ctx.project_slug, settings)
            scip_index = parse_scip_file(scip_path)
            commit_sha = _read_head_sha(ctx.repo_path)

            all_occs = list(
                iter_scip_occurrences(
                    scip_index,
                    commit_sha=commit_sha,
                    ingest_run_id=ctx.run_id,
                )
            )

            tantivy_path = Path(settings.palace_tantivy_index_path)
            counter = _load_or_reset_counter(tantivy_path, ctx.run_id)
            for occ in all_occs:
                if occ.kind == SymbolKind.USE:
                    counter.increment(occ.symbol_qualified_name)

            total_written = 0
            async with TantivyBridge(
                tantivy_path,
                heap_size_mb=settings.palace_tantivy_heap_mb,
            ) as bridge:
                check_phase_budget(
                    nodes_written_so_far=total_written,
                    max_occurrences_total=settings.palace_max_occurrences_total,
                    phase="phase1_defs",
                )
                phase1 = [
                    o for o in all_occs if o.kind in (SymbolKind.DEF, SymbolKind.DECL)
                ]
                p1 = await _ingest_batch(bridge, phase1)
                await bridge.commit_async()
                await write_checkpoint(
                    driver,
                    run_id=ctx.run_id,
                    project=ctx.project_slug,
                    phase="phase1_defs",
                    expected_doc_count=p1,
                )
                total_written += p1
                logger.info("Phase 1 (defs+decls): %d written", p1)

                p2 = 0
                budget_frac = total_written / max(
                    settings.palace_max_occurrences_per_project, 1
                )
                if budget_frac < 0.5:
                    check_phase_budget(
                        nodes_written_so_far=total_written,
                        max_occurrences_total=settings.palace_max_occurrences_total,
                        phase="phase2_user_uses",
                    )
                    phase2 = [
                        _with_importance(o, counter, settings)
                        for o in all_occs
                        if o.kind == SymbolKind.USE and not _is_vendor(o.file_path)
                    ]
                    phase2 = [
                        o
                        for o in phase2
                        if o.importance >= settings.palace_importance_threshold_use
                    ]
                    p2 = await _ingest_batch(bridge, phase2)
                    await bridge.commit_async()
                    await write_checkpoint(
                        driver,
                        run_id=ctx.run_id,
                        project=ctx.project_slug,
                        phase="phase2_user_uses",
                        expected_doc_count=p1 + p2,
                    )
                    total_written += p2
                    logger.info("Phase 2 (user uses): %d written", p2)

                p3 = 0
                budget_frac = total_written / max(
                    settings.palace_max_occurrences_per_project, 1
                )
                if budget_frac < 0.3:
                    check_phase_budget(
                        nodes_written_so_far=total_written,
                        max_occurrences_total=settings.palace_max_occurrences_total,
                        phase="phase3_vendor_uses",
                    )
                    phase3 = [
                        _with_importance(o, counter, settings)
                        for o in all_occs
                        if o.kind == SymbolKind.USE and _is_vendor(o.file_path)
                    ]
                    p3 = await _ingest_batch(bridge, phase3)
                    if p3 > 0:
                        await bridge.commit_async()
                        await write_checkpoint(
                            driver,
                            run_id=ctx.run_id,
                            project=ctx.project_slug,
                            phase="phase3_vendor_uses",
                            expected_doc_count=p1 + p2 + p3,
                        )
                    total_written += p3
                    logger.info("Phase 3 (vendor uses): %d written", p3)

            counter_path = tantivy_path / "in_degree_counter.json"
            counter.to_disk(counter_path, run_id=ctx.run_id)

            await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
            return ExtractorStats(nodes_written=total_written, edges_written=0)

        except ScipPathRequiredError as e:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code=ExtractorErrorCode.SCIP_PATH_REQUIRED.value,
            )
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCIP_PATH_REQUIRED,
                message=str(e),
                recoverable=False,
                action="manual_cleanup",
            ) from e
        except ExtractorError:
            await finalize_ingest_run(
                driver, run_id=ctx.run_id, success=False, error_code="extractor_error"
            )
            raise
        except Exception:
            await finalize_ingest_run(
                driver, run_id=ctx.run_id, success=False, error_code="unknown"
            )
            raise


async def _ingest_batch(
    bridge: TantivyBridge, occurrences: list[SymbolOccurrence]
) -> int:
    written = 0
    for occ in occurrences:
        await bridge.add_or_replace_async(occ)
        written += 1
    return written


def _load_or_reset_counter(tantivy_path: Path, run_id: str) -> BoundedInDegreeCounter:
    counter = BoundedInDegreeCounter()
    counter_path = tantivy_path / "in_degree_counter.json"
    if not counter_path.exists():
        return counter
    if not counter.from_disk(counter_path, expected_run_id=run_id):
        if os.environ.get("PALACE_COUNTER_RESET") != "1":
            raise ExtractorError(
                error_code=ExtractorErrorCode.COUNTER_STATE_CORRUPT,
                message=(
                    f"Counter state corrupt or run_id mismatch at {counter_path}. "
                    "Set PALACE_COUNTER_RESET=1 to reset, or rebuild the index."
                ),
                recoverable=False,
                action="manual_cleanup",
            )
        return BoundedInDegreeCounter()
    return counter


def _with_importance(
    occ: SymbolOccurrence,
    counter: BoundedInDegreeCounter,
    settings: object,
) -> SymbolOccurrence:
    score = importance_score(
        cms_in_degree=counter.estimate(occ.symbol_qualified_name),
        file_path=occ.file_path,
        kind=occ.kind,
        last_seen_at=datetime.now(tz=timezone.utc),
        language=occ.language,
        primary_lang=Language.JAVA,
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


def _is_vendor(file_path: str) -> bool:
    _VENDOR_MARKERS = (
        "node_modules/",
        "vendor/",
        ".venv/",
        "site-packages/",
        "__pycache__/",
        "dist/",
        "build/",
        "target/",
        ".gradle/",
    )
    return any(m in file_path for m in _VENDOR_MARKERS)


def _read_head_sha(repo_path: Path) -> str:
    head_file = repo_path / ".git" / "HEAD"
    try:
        ref = head_file.read_text().strip()
        if ref.startswith("ref: "):
            ref_path = repo_path / ".git" / ref[5:]
            return ref_path.read_text().strip()[:40]
        return ref[:40]
    except (FileNotFoundError, OSError):
        return "unknown"


async def _get_previous_error_code(driver: AsyncDriver, project: str) -> str | None:
    _QUERY = """
    MATCH (r:IngestRun {project: $project, extractor_name: 'symbol_index_java'})
    WHERE r.success = false
    RETURN r.error_code AS error_code
    ORDER BY r.started_at DESC
    LIMIT 1
    """
    async with driver.session() as session:
        result = await session.run(_QUERY, project=project)
        record = await result.single()
        return None if record is None else record["error_code"]
```

- [ ] **Step 2: Register in registry.py**

Add import and entry:

```python
from palace_mcp.extractors.symbol_index_java import SymbolIndexJava

EXTRACTORS: dict[str, BaseExtractor] = {
    "heartbeat": HeartbeatExtractor(),
    "codebase_memory_bridge": CodebaseMemoryBridgeExtractor(),
    "symbol_index_python": SymbolIndexPython(),
    "symbol_index_typescript": SymbolIndexTypeScript(),
    "symbol_index_java": SymbolIndexJava(),
}
```

- [ ] **Step 3: Verify import works**

Run: `cd services/palace-mcp && uv run python -c "from palace_mcp.extractors.registry import EXTRACTORS; print(list(EXTRACTORS.keys()))"`
Expected: includes `symbol_index_java`

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py \
      services/palace-mcp/src/palace_mcp/extractors/registry.py
git commit -m "feat(GIM-111): add SymbolIndexJava extractor + registry entry"
```

---

## Task 4: Unit tests for SymbolIndexJava (mocked driver + bridge)

**Files:**
- Create: `services/palace-mcp/tests/extractors/unit/test_symbol_index_java.py`

- [ ] **Step 1: Write unit tests**

Mirror `test_symbol_index_typescript.py` structure. Key tests:

```python
"""Unit tests for SymbolIndexJava extractor (mocked driver + bridge)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.symbol_index_java import SymbolIndexJava
from tests.extractors.fixtures.scip_factory import (
    build_jvm_scip_index,
    write_scip_fixture,
)


@pytest.fixture
def extractor() -> SymbolIndexJava:
    return SymbolIndexJava()


@pytest.fixture
def scip_fixture(tmp_path: Path) -> Path:
    index = build_jvm_scip_index(
        symbols=[
            (
                "semanticdb maven com.example 1.0.0 com/example/User#.",
                1,
            ),
            (
                "semanticdb maven com.example 1.0.0 com/example/User#getName().",
                1,
            ),
            (
                "semanticdb maven com.example 1.0.0 com/example/User#getName().",
                0,
            ),
        ],
    )
    return write_scip_fixture(index, tmp_path / "test.scip")


@pytest.fixture
def run_ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="test-project",
        group_id="project/test-project",
        repo_path=tmp_path,
        run_id="test-run-java-001",
        duration_ms=0,
        logger=MagicMock(),
    )


def _make_driver() -> MagicMock:
    inner_session = AsyncMock()
    result_mock = AsyncMock()
    result_mock.single = AsyncMock(return_value=None)
    inner_session.run = AsyncMock(return_value=result_mock)
    session_ctx = AsyncMock()
    session_ctx.__aenter__ = AsyncMock(return_value=inner_session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session_ctx)
    return driver


def test_extractor_metadata(extractor: SymbolIndexJava) -> None:
    assert extractor.name == "symbol_index_java"
    assert extractor.primary_lang == Language.JAVA
    assert "Java" in extractor.description
    assert "Kotlin" in extractor.description


def test_extractor_registered() -> None:
    from palace_mcp.extractors.registry import EXTRACTORS
    assert "symbol_index_java" in EXTRACTORS
    assert isinstance(EXTRACTORS["symbol_index_java"], SymbolIndexJava)


@pytest.mark.asyncio
async def test_run_no_driver(extractor: SymbolIndexJava, run_ctx: ExtractorRunContext) -> None:
    with patch("palace_mcp.extractors.symbol_index_java.get_driver", return_value=None), \
         patch("palace_mcp.extractors.symbol_index_java.get_settings", return_value=MagicMock()):
        with pytest.raises(ExtractorError) as exc_info:
            await extractor.run(graphiti=MagicMock(), ctx=run_ctx)
        assert exc_info.value.error_code == ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED


@pytest.mark.asyncio
async def test_run_no_settings(extractor: SymbolIndexJava, run_ctx: ExtractorRunContext) -> None:
    with patch("palace_mcp.extractors.symbol_index_java.get_driver", return_value=_make_driver()), \
         patch("palace_mcp.extractors.symbol_index_java.get_settings", return_value=None):
        with pytest.raises(ExtractorError) as exc_info:
            await extractor.run(graphiti=MagicMock(), ctx=run_ctx)
        assert exc_info.value.error_code == ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED


@pytest.mark.asyncio
async def test_run_scip_path_required(
    extractor: SymbolIndexJava, run_ctx: ExtractorRunContext
) -> None:
    settings = MagicMock()
    settings.palace_scip_index_paths = {}
    with patch("palace_mcp.extractors.symbol_index_java.get_driver", return_value=_make_driver()), \
         patch("palace_mcp.extractors.symbol_index_java.get_settings", return_value=settings), \
         patch("palace_mcp.extractors.symbol_index_java.ensure_custom_schema", new_callable=AsyncMock), \
         patch("palace_mcp.extractors.symbol_index_java.create_ingest_run", new_callable=AsyncMock), \
         patch("palace_mcp.extractors.symbol_index_java.finalize_ingest_run", new_callable=AsyncMock):
        with pytest.raises(ExtractorError) as exc_info:
            await extractor.run(graphiti=MagicMock(), ctx=run_ctx)
        assert exc_info.value.error_code == ExtractorErrorCode.SCIP_PATH_REQUIRED
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_symbol_index_java.py -v`
Expected: All PASS (these are testing the newly created extractor code)

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_symbol_index_java.py
git commit -m "test(GIM-111): unit tests for SymbolIndexJava extractor"
```

---

## Task 5: Vendored JVM mini-project fixture (7 source files + index.scip)

**Files:**
- Create: all files under `services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/`

This task creates the vendored fixture. The `.scip` must be generated externally (requires scip-java + JVM). For CI, the committed `index.scip` is used as-is.

- [ ] **Step 1: Create build.gradle.kts**

```kotlin
// services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/build.gradle.kts
plugins {
    kotlin("jvm") version "1.9.22"
    java
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation(kotlin("stdlib"))
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.0")
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
```

- [ ] **Step 2: Create User.java (regular class, public/private methods)**

```java
// services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/User.java
package com.example;

public class User {
    private String name;
    private int age;

    public User(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    private String formatDisplay() {
        return name + " (" + age + ")";
    }

    @Override
    public String toString() {
        return formatDisplay();
    }
}
```

- [ ] **Step 3: Create Cache.java (generic <K, V>)**

```java
// services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Cache.java
package com.example;

import java.util.HashMap;
import java.util.Map;

public class Cache<K, V> {
    private final Map<K, V> store = new HashMap<>();

    public void put(K key, V value) {
        store.put(key, value);
    }

    public V get(K key) {
        return store.get(key);
    }

    public int size() {
        return store.size();
    }
}
```

- [ ] **Step 4: Create Inner.java (nested + anonymous inner classes)**

```java
// services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Inner.java
package com.example;

public class Inner {
    public static class Nested {
        public String value() {
            return "nested";
        }
    }

    public class MemberInner {
        public String value() {
            return "member-inner";
        }
    }

    public Runnable createAnonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };
    }
}
```

- [ ] **Step 5: Create Main.java (cross-package imports + uses)**

```java
// services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Main.java
package com.example;

public class Main {
    public static void main(String[] args) {
        User user = new User("Alice", 30);
        System.out.println(user.getName());

        Cache<String, User> cache = new Cache<>();
        cache.put("alice", user);

        Inner.Nested nested = new Inner.Nested();
        System.out.println(nested.value());
    }
}
```

- [ ] **Step 6: Create Logger.kt (Kotlin top-level + companion object)**

```kotlin
// services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Logger.kt
package com.example

fun log(message: String) {
    println("[LOG] $message")
}

class Logger private constructor(val tag: String) {
    fun info(message: String) {
        log("[$tag] $message")
    }

    companion object {
        fun create(tag: String): Logger = Logger(tag)
    }
}
```

- [ ] **Step 7: Create Greeter.kt (extension fun + suspend fun)**

```kotlin
// services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Greeter.kt
package com.example

import kotlinx.coroutines.delay

fun User.greet(): String {
    return "Hello, ${getName()}!"
}

suspend fun fetchUserAsync(name: String): User {
    delay(100)
    return User(name, 25)
}

class Greeter(private val prefix: String) {
    fun greetUser(user: User): String {
        return "$prefix ${user.greet()}"
    }
}
```

- [ ] **Step 8: Create Sealed.kt (sealed class hierarchy)**

```kotlin
// services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Sealed.kt
package com.example

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Failure(val error: String) : Result<Nothing>()
    data object Loading : Result<Nothing>()
}

fun <T> Result<T>.getOrNull(): T? = when (this) {
    is Result.Success -> data
    is Result.Failure -> null
    is Result.Loading -> null
}
```

- [ ] **Step 9: Create REGEN.md**

```markdown
# Regenerating index.scip

The committed `index.scip` is a pre-built fixture. To regenerate it after
changing the source files:

## Prerequisites

- JDK 17+
- Coursier (cs): `brew install coursier/formulas/coursier`
- scip-java: `cs install scip-java`

## Steps

```bash
cd services/palace-mcp/tests/extractors/fixtures/jvm-mini-project
scip-java index --output index.scip
```

Or use the top-level Makefile target:

```bash
make regen-jvm-fixture
```

## Fixture contents

- `src/main/java/com/example/User.java` — regular class, public/private methods
- `src/main/java/com/example/Cache.java` — generic <K, V>
- `src/main/java/com/example/Inner.java` — nested + anonymous inner classes
- `src/main/java/com/example/Main.java` — cross-package imports + uses
- `src/main/kotlin/com/example/Logger.kt` — Kotlin top-level + companion object
- `src/main/kotlin/com/example/Greeter.kt` — extension fun + suspend fun
- `src/main/kotlin/com/example/Sealed.kt` — sealed class hierarchy

The fixture intentionally has both defs (role=1) and uses (role=0) so 3-phase
bootstrap tests can verify phase1_defs and phase2_user_uses checkpoint writes.
```

- [ ] **Step 10: Generate index.scip**

This step requires scip-java installed locally (JVM + coursier). Run:

```bash
cd services/palace-mcp/tests/extractors/fixtures/jvm-mini-project
scip-java index --output index.scip
```

If scip-java is not available, create a synthetic `.scip` using `build_jvm_scip_index()` as a temporary placeholder. The real fixture MUST be generated before Phase 3.1 CR review.

**Synthetic placeholder (if no JVM available):**

```python
# Run once from services/palace-mcp/
python3 -c "
from tests.extractors.fixtures.scip_factory import build_jvm_scip_index, write_scip_fixture
from pathlib import Path

symbols = [
    ('semanticdb maven com.example 1.0.0 com/example/User#', 1),
    ('semanticdb maven com.example 1.0.0 com/example/User#getName().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/User#getAge().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/User#formatDisplay().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/User#toString().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Cache#', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Cache#[K]', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Cache#[V]', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Cache#put().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Cache#get().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Cache#size().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Inner#', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Inner#Nested#', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Inner#Nested#value().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Inner#MemberInner#', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Inner#MemberInner#value().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Inner#createAnonymous().', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Main#', 1),
    ('semanticdb maven com.example 1.0.0 com/example/Main#main().', 1),
    # Uses
    ('semanticdb maven com.example 1.0.0 com/example/User#getName().', 0),
    ('semanticdb maven com.example 1.0.0 com/example/Cache#put().', 0),
    ('semanticdb maven com.example 1.0.0 com/example/Inner#Nested#value().', 0),
]

# Java docs
index = build_jvm_scip_index(
    relative_path='src/main/java/com/example/User.java',
    language='java',
    symbols=[(s, r) for s, r in symbols if 'User' in s],
)

# Full multi-doc index
from palace_mcp.proto import scip_pb2
full_index = scip_pb2.Index()
full_index.metadata.CopyFrom(index.metadata)

java_files = {
    'src/main/java/com/example/User.java': [s for s in symbols if 'User' in s[0]],
    'src/main/java/com/example/Cache.java': [s for s in symbols if 'Cache' in s[0]],
    'src/main/java/com/example/Inner.java': [s for s in symbols if 'Inner' in s[0]],
    'src/main/java/com/example/Main.java': [s for s in symbols if 'Main' in s[0]],
}

kotlin_files = {
    'src/main/kotlin/com/example/Logger.kt': [
        ('semanticdb maven com.example 1.0.0 com/example/LoggerKt#log().', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Logger#', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Logger#info().', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Logger#Companion#', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Logger#Companion#create().', 1),
    ],
    'src/main/kotlin/com/example/Greeter.kt': [
        ('semanticdb maven com.example 1.0.0 com/example/GreeterKt#greet().', 1),
        ('semanticdb maven com.example 1.0.0 com/example/GreeterKt#fetchUserAsync().', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Greeter#', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Greeter#greetUser().', 1),
        ('semanticdb maven com.example 1.0.0 com/example/User#getName().', 0),
    ],
    'src/main/kotlin/com/example/Sealed.kt': [
        ('semanticdb maven com.example 1.0.0 com/example/Result#', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Result#Success#', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Result#Failure#', 1),
        ('semanticdb maven com.example 1.0.0 com/example/Result#Loading#', 1),
        ('semanticdb maven com.example 1.0.0 com/example/SealedKt#getOrNull().', 1),
    ],
}

for fp, syms in {**java_files, **kotlin_files}.items():
    doc = full_index.documents.add()
    doc.relative_path = fp
    doc.language = 'kotlin' if fp.endswith(('.kt', '.kts')) else 'java'
    for sym_str, role in syms:
        occ = doc.occurrences.add()
        occ.range.extend([1, 0, 10])
        occ.symbol = sym_str
        occ.symbol_roles = role

out = Path('tests/extractors/fixtures/jvm-mini-project/index.scip')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(full_index.SerializeToString())
print(f'Written {out} ({out.stat().st_size} bytes, {len(full_index.documents)} docs)')
"
```

- [ ] **Step 11: Verify fixture file count = 7 source files**

```bash
find services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src -name "*.java" -o -name "*.kt" | wc -l
# Expected: 7
ls -la services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/
ls -la services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/
```

- [ ] **Step 12: Commit all fixture files**

```bash
git add services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/
git commit -m "feat(GIM-111): vendored JVM mini-project fixture (7 source files + index.scip)"
```

---

## Task 6: Real-fixture tests

**Files:**
- Create: `services/palace-mcp/tests/extractors/unit/test_symbol_index_java_real_fixture.py`

- [ ] **Step 1: Write real-fixture tests**

```python
"""Real-fixture tests for symbol_index_java — load committed .scip, assert JVM symbols."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.extractors.foundation.models import Language, SymbolKind
from palace_mcp.extractors.scip_parser import (
    iter_scip_occurrences,
    parse_scip_file,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "jvm-mini-project"
SCIP_PATH = FIXTURE_DIR / "index.scip"


@pytest.fixture
def jvm_occurrences() -> list:
    index = parse_scip_file(SCIP_PATH)
    return list(
        iter_scip_occurrences(
            index, commit_sha="fixture-test", ingest_run_id="fixture-run"
        )
    )


def test_fixture_exists() -> None:
    assert SCIP_PATH.exists(), f"Committed fixture not found: {SCIP_PATH}"


def test_fixture_has_occurrences(jvm_occurrences: list) -> None:
    assert len(jvm_occurrences) > 0, "No occurrences parsed from JVM fixture"


def test_java_class_symbol(jvm_occurrences: list) -> None:
    user_defs = [
        o for o in jvm_occurrences
        if "User#" in o.symbol_qualified_name
        and o.kind == SymbolKind.DEF
    ]
    assert len(user_defs) > 0, "User class def not found"


def test_java_method_symbol(jvm_occurrences: list) -> None:
    get_name = [
        o for o in jvm_occurrences
        if "User#getName()." in o.symbol_qualified_name
    ]
    assert len(get_name) > 0, "User#getName() not found"


def test_java_generic_type_params(jvm_occurrences: list) -> None:
    cache_syms = [
        o for o in jvm_occurrences
        if "Cache#" in o.symbol_qualified_name
        and o.kind == SymbolKind.DEF
    ]
    assert len(cache_syms) > 0, "Cache generic class not found"

    cache_put = [
        o for o in jvm_occurrences
        if "Cache#put()." in o.symbol_qualified_name
    ]
    assert len(cache_put) > 0, "Cache#put() not found"


def test_java_nested_class(jvm_occurrences: list) -> None:
    nested = [
        o for o in jvm_occurrences
        if "Inner#Nested#" in o.symbol_qualified_name
        and o.kind == SymbolKind.DEF
    ]
    assert len(nested) > 0, "Inner.Nested class not found"


def test_kotlin_top_level_function(jvm_occurrences: list) -> None:
    log_fn = [
        o for o in jvm_occurrences
        if "log()." in o.symbol_qualified_name
        and o.kind == SymbolKind.DEF
    ]
    assert len(log_fn) > 0, "Kotlin top-level log() not found"


def test_kotlin_companion_object(jvm_occurrences: list) -> None:
    companion = [
        o for o in jvm_occurrences
        if "Logger#Companion#" in o.symbol_qualified_name
        and o.kind == SymbolKind.DEF
    ]
    assert len(companion) > 0, "Logger.Companion not found"


def test_kotlin_extension_function(jvm_occurrences: list) -> None:
    greet = [
        o for o in jvm_occurrences
        if "greet()." in o.symbol_qualified_name
        and o.kind == SymbolKind.DEF
    ]
    assert len(greet) > 0, "Kotlin extension greet() not found"


def test_kotlin_sealed_class(jvm_occurrences: list) -> None:
    result = [
        o for o in jvm_occurrences
        if "Result#" in o.symbol_qualified_name
        and o.kind == SymbolKind.DEF
    ]
    assert len(result) > 0, "Sealed Result class not found"

    success = [
        o for o in jvm_occurrences
        if "Result#Success#" in o.symbol_qualified_name
    ]
    assert len(success) > 0, "Result.Success not found"


def test_language_detection_java(jvm_occurrences: list) -> None:
    java_occs = [o for o in jvm_occurrences if o.file_path.endswith(".java")]
    assert len(java_occs) > 0, "No Java occurrences found"
    assert all(o.language == Language.JAVA for o in java_occs), "Java file not detected as JAVA"


def test_language_detection_kotlin(jvm_occurrences: list) -> None:
    kt_occs = [o for o in jvm_occurrences if o.file_path.endswith(".kt")]
    assert len(kt_occs) > 0, "No Kotlin occurrences found"
    assert all(o.language == Language.KOTLIN for o in kt_occs), "Kotlin file not detected as KOTLIN"


def test_variant_b_qualified_name_no_version(jvm_occurrences: list) -> None:
    for occ in jvm_occurrences:
        assert "1.0.0" not in occ.symbol_qualified_name, (
            f"Version found in qualified_name: {occ.symbol_qualified_name}"
        )
        assert not occ.symbol_qualified_name.startswith("scip-java"), (
            f"Scheme found in qualified_name: {occ.symbol_qualified_name}"
        )


def test_has_both_defs_and_uses(jvm_occurrences: list) -> None:
    defs = [o for o in jvm_occurrences if o.kind == SymbolKind.DEF]
    uses = [o for o in jvm_occurrences if o.kind == SymbolKind.USE]
    assert len(defs) > 0, "No DEF occurrences"
    assert len(uses) > 0, "No USE occurrences"
```

- [ ] **Step 2: Run tests**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_symbol_index_java_real_fixture.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_symbol_index_java_real_fixture.py
git commit -m "test(GIM-111): real-fixture tests for JVM symbols"
```

---

## Task 7: Drift-check test with requires_scip_java marker

**Files:**
- Modify: `services/palace-mcp/tests/extractors/unit/test_symbol_index_java_real_fixture.py` (add drift test)
- Modify: `services/palace-mcp/pyproject.toml` (add marker)

- [ ] **Step 1: Register pytest marker in pyproject.toml**

Add to the `[tool.pytest.ini_options]` markers list:

```toml
"requires_scip_java: tests needing scip-java binary (skip in CI)"
```

- [ ] **Step 2: Add drift-check test**

Append to `test_symbol_index_java_real_fixture.py`:

```python
@pytest.mark.requires_scip_java
def test_drift_check_regen() -> None:
    """Regenerate index.scip and compare with committed version.

    Skipped in CI (no JVM). Run locally to catch drift between source files
    and the committed .scip fixture.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["scip-java", "index", "--output", f"{tmpdir}/index.scip"],
            cwd=str(FIXTURE_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"scip-java failed: {result.stderr}"

        committed = SCIP_PATH.read_bytes()
        regenerated = Path(f"{tmpdir}/index.scip").read_bytes()

        committed_index = parse_scip_file(SCIP_PATH)
        regen_index = parse_scip_file(Path(f"{tmpdir}/index.scip"))

        committed_symbols = {
            occ.symbol
            for doc in committed_index.documents
            for occ in doc.occurrences
            if occ.symbol
        }
        regen_symbols = {
            occ.symbol
            for doc in regen_index.documents
            for occ in doc.occurrences
            if occ.symbol
        }

        missing = committed_symbols - regen_symbols
        added = regen_symbols - committed_symbols

        assert not missing, f"Symbols in committed but not in regen: {missing}"
        assert not added, f"New symbols in regen not in committed: {added}"
```

- [ ] **Step 3: Verify test is skipped in CI**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_symbol_index_java_real_fixture.py::test_drift_check_regen -v`
Expected: SKIPPED (unless scip-java is installed locally)

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_symbol_index_java_real_fixture.py \
      services/palace-mcp/pyproject.toml
git commit -m "test(GIM-111): drift-check test with requires_scip_java marker"
```

---

## Task 8: Integration tests (real Neo4j via compose reuse)

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_symbol_index_java_integration.py`

- [ ] **Step 1: Write integration test**

Mirror `test_symbol_index_python_integration.py` pattern:

```python
"""Integration tests for SymbolIndexJava — real Neo4j via testcontainers/compose."""

from __future__ import annotations

import pytest

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.symbol_index_java import SymbolIndexJava


@pytest.mark.integration
class TestSymbolIndexJavaIntegration:
    def test_extractor_name(self) -> None:
        ext = SymbolIndexJava()
        assert ext.name == "symbol_index_java"

    def test_primary_lang(self) -> None:
        ext = SymbolIndexJava()
        assert ext.primary_lang == Language.JAVA
```

Note: Full integration tests requiring real Neo4j use the existing `conftest.py` fixtures from the integration test directory. The pattern follows `test_symbol_index_python_integration.py`. Add more tests as the integration infra evolves.

- [ ] **Step 2: Run integration test (if compose available)**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_symbol_index_java_integration.py -v -m integration`
Expected: PASS (or SKIP if no Neo4j)

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_symbol_index_java_integration.py
git commit -m "test(GIM-111): integration test skeleton for SymbolIndexJava"
```

---

## Task 9: Makefile regen-jvm-fixture target

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add JVM fixture dir variable and target**

```makefile
JVM_FIXTURE_DIR := $(PALACE_MCP_DIR)/tests/extractors/fixtures/jvm-mini-project

.PHONY: regen-jvm-fixture

# Regenerate the committed JVM SCIP fixture.
# Requires: JDK 17+, coursier, scip-java (cs install scip-java).
regen-jvm-fixture:
	cd $(JVM_FIXTURE_DIR) && scip-java index --output index.scip
	@echo "Regenerated $(JVM_FIXTURE_DIR)/index.scip"
```

- [ ] **Step 2: Verify Makefile parses**

Run: `make -n regen-jvm-fixture`
Expected: prints the commands without executing

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(GIM-111): Makefile regen-jvm-fixture target"
```

---

## Task 10: Update CLAUDE.md registered extractors

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add symbol_index_java to registered extractors section**

In the `### Registered extractors` section of CLAUDE.md, add after `symbol_index_python`:

```markdown
- `symbol_index_java` — Java/Kotlin symbol indexer. Reads a pre-generated `.scip`
  file (produced by `scip-java` outside the container).
  Writes occurrences into Tantivy (full-text) and `:IngestRun` + checkpoints
  into Neo4j. 3-phase bootstrap: defs/decls → user uses → vendor uses.
  Query via `palace.code.find_references(qualified_name, project)`.
```

- [ ] **Step 2: Add operator workflow section**

After the `### Operator workflow: Python symbol index` section, add:

```markdown
### Operator workflow: JVM symbol index

1. Install scip-java via Coursier:
   ```bash
   cs install scip-java
   ```

2. Generate `.scip` file outside the container:
   ```bash
   cd /repos/your-jvm-project
   scip-java index --output ./scip/index.scip
   ```

3. Set env var for palace-mcp container in `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={"your-slug":"/repos/your-slug/scip/index.scip"}
   ```

4. Run the extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_java", project="your-slug")
   ```

5. Query references:
   ```
   palace.code.find_references(qualified_name="com/example/User#getName().", project="your-slug")
   ```
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(GIM-111): add symbol_index_java to CLAUDE.md registered extractors"
```

---

## Task 11: Final validation + push

- [ ] **Step 1: Run full lint + typecheck + test suite**

```bash
cd services/palace-mcp
uv run ruff check
uv run mypy src/
uv run pytest -m "not slow and not requires_scip_java" -v
```

Expected: All green

- [ ] **Step 2: Verify fixture file count (Phase 3.1 CR assertion)**

```bash
find services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src -name "*.java" -o -name "*.kt" | sort
```

Expected output (exactly 7 files):
```
services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Cache.java
services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Inner.java
services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/Main.java
services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/User.java
services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Greeter.kt
services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Logger.kt
services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/Sealed.kt
```

- [ ] **Step 3: Push feature branch**

```bash
git push origin feature/GIM-111-symbol-index-java
```

---

## Phase 3.1 CR Checklist (for CodeReviewer)

The following MUST be verified during mechanical review:

1. `uv run ruff check && uv run mypy src/ && uv run pytest` output pasted in APPROVE comment
2. **Fixture file count assertion**: `find services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src -name "*.java" -o -name "*.kt" | wc -l` = **7**
3. `ls -la services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/java/com/example/` shows: User.java, Cache.java, Inner.java, Main.java
4. `ls -la services/palace-mcp/tests/extractors/fixtures/jvm-mini-project/src/main/kotlin/com/example/` shows: Logger.kt, Greeter.kt, Sealed.kt
5. Edge case coverage matrix from spec matches landed fixture (see spec Risk 4)
