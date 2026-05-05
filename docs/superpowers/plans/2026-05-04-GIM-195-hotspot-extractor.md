# Hotspot Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `hotspot` extractor (Roadmap #44) — file-level Tornhill log-log score + per-function complexity — and two MCP query tools (`palace.code.find_hotspots`, `palace.code.list_functions`).

**Architecture:** Per `docs/superpowers/specs/2026-05-04-hotspot-extractor-design.md` (rev2). Stand-alone Python extractor under `services/palace-mcp/src/palace_mcp/extractors/hotspot/`. Walks repo with `Path.rglob` + stop-list, calls `lizard` subprocess in 50-file batches, parses `--xml` output, writes `:File` props + `:Function` nodes via 5-phase Cypher pipeline. Reads commit churn from existing `git_history` `:Commit -[:TOUCHED]-> :File` graph. Score: `log(ccn_total+1) * log(churn_count+1)`. Cross-extractor isolation enforced by source-grep test.

**Tech Stack:** Python 3.13+, Pydantic v2, `lizard>=1.17.20,<2.0`, Neo4j (`graphiti_core` driver), pytest + testcontainers, MCP via FastMCP.

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `services/palace-mcp/pyproject.toml` | Add `lizard>=1.17.20,<2.0` to `[project.dependencies]` |
| `services/palace-mcp/src/palace_mcp/config.py` | Add 4 `PALACE_HOTSPOT_*` env-var fields to `Settings` |
| `services/palace-mcp/src/palace_mcp/extractors/hotspot/__init__.py` | Package init |
| `services/palace-mcp/src/palace_mcp/extractors/hotspot/models.py` | `ParsedFunction`, `ParsedFile` Pydantic frozen models |
| `services/palace-mcp/src/palace_mcp/extractors/hotspot/file_walker.py` | `_walk()`, `_STOP_DIRS`, `_LIZARD_EXTENSIONS`, `_FIXTURE_STOP_PARTS` |
| `services/palace-mcp/src/palace_mcp/extractors/hotspot/lizard_runner.py` | Subprocess wrapper + XML parse + timeout policy |
| `services/palace-mcp/src/palace_mcp/extractors/hotspot/churn_query.py` | Single Cypher round-trip for churn count in window |
| `services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py` | 5 phase write functions; cross-extractor-safe (no SET on `project_id`/`path`) |
| `services/palace-mcp/src/palace_mcp/extractors/hotspot/extractor.py` | `HotspotExtractor(BaseExtractor)` orchestrator |
| `services/palace-mcp/src/palace_mcp/extractors/registry.py` | Add `hotspot` to `EXTRACTORS` mapping |
| `services/palace-mcp/src/palace_mcp/code/find_hotspots.py` | `palace.code.find_hotspots` MCP tool |
| `services/palace-mcp/src/palace_mcp/code/list_functions.py` | `palace.code.list_functions` MCP tool |
| `services/palace-mcp/src/palace_mcp/server.py` | Register both MCP tools |
| `services/palace-mcp/tests/extractors/unit/test_hotspot_models.py` | Pydantic validators |
| `services/palace-mcp/tests/extractors/unit/test_hotspot_file_walker.py` | `_walk` stop-list, fixture parts check, extension filter |
| `services/palace-mcp/tests/extractors/unit/test_hotspot_lizard_runner.py` | XML parse + timeout drop_batch + fail_run |
| `services/palace-mcp/tests/extractors/unit/test_hotspot_neo4j_writer.py` | Phase 1/3/4/5 Cypher param shape (mock driver) |
| `services/palace-mcp/tests/extractors/unit/test_cross_extractor_file_isolation.py` | Source-grep guard for invariant 1 (acceptance #11) |
| `services/palace-mcp/tests/extractors/integration/test_hotspot_integration.py` | Real Neo4j: full pipeline + idempotency via `result.consume().counters` |
| `services/palace-mcp/tests/integration/test_find_hotspots_tool.py` | Wire-contract: 4 rows from spec §7.2 error matrix |
| `services/palace-mcp/tests/integration/test_list_functions_tool.py` | Wire-contract: 4 rows from spec §7.2 error matrix |
| `services/palace-mcp/tests/extractors/fixtures/hotspot-mini-project/` | Mini fixture: 3-language tree with known CCN/churn |
| `CLAUDE.md` | New `hotspot` row in registered extractors table + new "Operator workflow: Hotspot extractor" subsection |

---

## Task 1: Add `lizard` dependency + 4 env vars

**Files:**
- Modify: `services/palace-mcp/pyproject.toml` (`[project.dependencies]`)
- Modify: `services/palace-mcp/src/palace_mcp/config.py:Settings`
- Test: `services/palace-mcp/tests/unit/test_settings_foundation.py` (extend existing)

- [ ] **Step 1: Write failing test for new settings fields**

Append to `services/palace-mcp/tests/unit/test_settings_foundation.py`:

```python
def test_hotspot_settings_defaults(monkeypatch):
    """Uses monkeypatch.setenv + _minimal_env() pattern per test_settings_foundation.py."""
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    settings = Settings()
    assert settings.hotspot_churn_window_days == 90
    assert settings.hotspot_lizard_batch_size == 50
    assert settings.hotspot_lizard_timeout_s == 30
    assert settings.hotspot_lizard_timeout_behavior == "drop_batch"


def test_hotspot_lizard_timeout_behavior_invalid_rejected(monkeypatch):
    import pytest
    from pydantic import ValidationError
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PALACE_HOTSPOT_LIZARD_TIMEOUT_BEHAVIOR", "boom")
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/unit/test_settings_foundation.py::test_hotspot_settings_defaults -v`

Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'hotspot_churn_window_days'`.

- [ ] **Step 3: Implement settings fields**

In `services/palace-mcp/src/palace_mcp/config.py`, append to `Settings`:

```python
from typing import Literal

# inside Settings class
hotspot_churn_window_days: int = Field(
    default=90, ge=1,
    description="Window (days) for :Commit churn aggregation per :File",
)
hotspot_lizard_batch_size: int = Field(
    default=50, ge=1, le=500,
    description="Files per lizard subprocess invocation",
)
hotspot_lizard_timeout_s: int = Field(
    default=30, ge=1,
    description="Per-batch lizard subprocess timeout (seconds)",
)
hotspot_lizard_timeout_behavior: Literal["drop_batch", "fail_run"] = Field(
    default="drop_batch",
    description="On lizard batch timeout: skip batch (drop_batch) or error whole run (fail_run)",
)
```

- [ ] **Step 4: Add lizard to dependencies**

In `services/palace-mcp/pyproject.toml`, append to `[project.dependencies]`:

```toml
"lizard>=1.17.20,<2.0",
```

Run: `cd services/palace-mcp && uv sync`

Expected: lizard resolves and installs.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_settings_foundation.py -v`

Expected: all pass including the 2 new ones.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/pyproject.toml services/palace-mcp/uv.lock services/palace-mcp/src/palace_mcp/config.py services/palace-mcp/tests/unit/test_settings_foundation.py
git commit -m "feat(GIM-195): add lizard dep + 4 PALACE_HOTSPOT_* env vars"
```

---

## Task 2: Models — `ParsedFunction` + `ParsedFile`

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/hotspot/__init__.py` (empty)
- Create: `services/palace-mcp/src/palace_mcp/extractors/hotspot/models.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_hotspot_models.py`

- [ ] **Step 1: Write failing test**

```python
# services/palace-mcp/tests/extractors/unit/test_hotspot_models.py
from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction


def test_parsed_function_minimal():
    fn = ParsedFunction(
        name="parse_x", start_line=10, end_line=25,
        ccn=4, parameter_count=2, nloc=12,
    )
    assert fn.name == "parse_x"
    assert fn.ccn == 4


def test_parsed_function_rejects_negative_ccn():
    with pytest.raises(ValidationError):
        ParsedFunction(
            name="bad", start_line=1, end_line=2, ccn=-1, parameter_count=0, nloc=1,
        )


def test_parsed_function_rejects_end_before_start():
    with pytest.raises(ValidationError):
        ParsedFunction(
            name="bad", start_line=10, end_line=5, ccn=1, parameter_count=0, nloc=1,
        )


def test_parsed_file_ccn_total_sums_functions():
    f1 = ParsedFunction(name="a", start_line=1, end_line=5, ccn=3, parameter_count=0, nloc=4)
    f2 = ParsedFunction(name="b", start_line=10, end_line=20, ccn=7, parameter_count=1, nloc=10)
    pf = ParsedFile(path="src/foo.py", language="python", functions=(f1, f2))
    assert pf.ccn_total == 10


def test_parsed_file_empty_functions_ccn_zero():
    pf = ParsedFile(path="src/foo.py", language="python", functions=())
    assert pf.ccn_total == 0


def test_parsed_file_path_must_be_relative_posix():
    with pytest.raises(ValidationError):
        ParsedFile(path="/abs/path.py", language="python", functions=())
    with pytest.raises(ValidationError):
        ParsedFile(path="windows\\style.py", language="python", functions=())


def test_parsed_models_are_frozen():
    fn = ParsedFunction(name="x", start_line=1, end_line=2, ccn=1, parameter_count=0, nloc=1)
    with pytest.raises(ValidationError):
        fn.ccn = 99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/extractors/unit/test_hotspot_models.py -v`

Expected: FAIL with `ModuleNotFoundError: palace_mcp.extractors.hotspot.models`.

- [ ] **Step 3: Create package init**

```bash
mkdir -p services/palace-mcp/src/palace_mcp/extractors/hotspot
touch services/palace-mcp/src/palace_mcp/extractors/hotspot/__init__.py
```

- [ ] **Step 4: Implement models**

```python
# services/palace-mcp/src/palace_mcp/extractors/hotspot/models.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ParsedFunction(_Frozen):
    name: str = Field(min_length=1, max_length=512)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    ccn: int = Field(ge=0)
    parameter_count: int = Field(ge=0)
    nloc: int = Field(ge=0)

    @model_validator(mode="after")
    def _line_range(self) -> "ParsedFunction":
        if self.end_line < self.start_line:
            raise ValueError(
                f"end_line ({self.end_line}) must be >= start_line ({self.start_line})"
            )
        return self


class ParsedFile(_Frozen):
    path: str = Field(min_length=1, max_length=4096)
    language: str = Field(min_length=1, max_length=64)
    functions: tuple[ParsedFunction, ...]

    @field_validator("path", mode="after")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError(f"path must be repo-relative, got absolute: {v!r}")
        if "\\" in v:
            raise ValueError(f"path must use POSIX separators, got: {v!r}")
        return v

    @property
    def ccn_total(self) -> int:
        return sum(fn.ccn for fn in self.functions)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/extractors/unit/test_hotspot_models.py -v`

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/hotspot/__init__.py services/palace-mcp/src/palace_mcp/extractors/hotspot/models.py services/palace-mcp/tests/extractors/unit/test_hotspot_models.py
git commit -m "feat(GIM-195): hotspot models — ParsedFunction + ParsedFile (Pydantic frozen)"
```

---

## Task 3: File walker — `_walk` with parts-based fixture stop

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/hotspot/file_walker.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_hotspot_file_walker.py`

- [ ] **Step 1: Write failing test**

```python
# services/palace-mcp/tests/extractors/unit/test_hotspot_file_walker.py
from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.hotspot.file_walker import _has_subseq, _walk


def test_has_subseq_basic():
    assert _has_subseq(("a", "b", "c", "d"), ("b", "c")) is True
    assert _has_subseq(("a", "b", "c", "d"), ("c", "b")) is False
    assert _has_subseq(("tests", "extractors", "fixtures", "x.py"), ("tests", "extractors", "fixtures")) is True
    assert _has_subseq(("docs", "tests", "extractors", "fixtures-policy.md"), ("tests", "extractors", "fixtures")) is False


def test_walk_picks_only_known_extensions(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def x(): pass\n")
    (tmp_path / "src" / "a.kt").write_text("fun x() {}\n")
    (tmp_path / "src" / "ignore.txt").write_text("not source\n")
    (tmp_path / "README.md").write_text("# r\n")

    out = sorted(p.relative_to(tmp_path).as_posix() for p in _walk(tmp_path))
    assert out == ["src/a.kt", "src/a.py"]


def test_walk_skips_stop_dirs(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "head.py").write_text("x\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("x\n")
    (tmp_path / "build" / "out").mkdir(parents=True)
    (tmp_path / "build" / "out" / "compiled.kt").write_text("x\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("def x(): pass\n")

    out = sorted(p.relative_to(tmp_path).as_posix() for p in _walk(tmp_path))
    assert out == ["src/ok.py"]


def test_walk_skips_fixture_dirs_subseq_only(tmp_path: Path):
    fixture_dir = tmp_path / "tests" / "extractors" / "fixtures"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "skip_me.py").write_text("x\n")

    not_fixture = tmp_path / "docs" / "tests-fixtures-policy.py"
    not_fixture.parent.mkdir(parents=True)
    not_fixture.write_text("x\n")

    out = sorted(p.relative_to(tmp_path).as_posix() for p in _walk(tmp_path))
    assert out == ["docs/tests-fixtures-policy.py"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/extractors/unit/test_hotspot_file_walker.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement file walker**

```python
# services/palace-mcp/src/palace_mcp/extractors/hotspot/file_walker.py
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

_STOP_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", ".gradle", ".kotlin", ".idea",
    "node_modules", "build", "dist", "target",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    ".tantivy", "__MACOSX",
})

_FIXTURE_STOP_PARTS: tuple[str, ...] = ("tests", "extractors", "fixtures")

_LIZARD_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".java", ".kt", ".kts", ".swift",
    ".ts", ".tsx", ".js", ".jsx",
    ".sol", ".cpp", ".cc", ".h", ".hpp", ".m", ".mm",
    ".rb", ".php", ".scala",
})


def _has_subseq(parts: tuple[str, ...], subseq: tuple[str, ...]) -> bool:
    if not subseq:
        return True
    n = len(subseq)
    return any(parts[i:i + n] == subseq for i in range(len(parts) - n + 1))


def _walk(root: Path) -> Iterator[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in _LIZARD_EXTENSIONS:
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in _STOP_DIRS for part in rel_parts):
            continue
        if _has_subseq(rel_parts, _FIXTURE_STOP_PARTS):
            continue
        yield p
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/extractors/unit/test_hotspot_file_walker.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/hotspot/file_walker.py services/palace-mcp/tests/extractors/unit/test_hotspot_file_walker.py
git commit -m "feat(GIM-195): hotspot file walker — stop-list + parts-based fixture skip"
```

---

## Task 4: Lizard runner — subprocess + XML parse + timeout policy

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/hotspot/lizard_runner.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_hotspot_lizard_runner.py`

See spec §5.2 + §5.6. Implement async subprocess wrapper, XML parser, and timeout-policy branch (`drop_batch` skip+warn vs `fail_run` raise).

- [ ] **Step 1: Write failing tests**

```python
# services/palace-mcp/tests/extractors/unit/test_hotspot_lizard_runner.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from palace_mcp.extractors.hotspot.lizard_runner import (
    LizardBatchTimeout, LizardRunResult, parse_lizard_xml, run_batch,
)

_SAMPLE_XML = """<?xml version="1.0"?>
<cppncss>
  <measure type="Function">
    <labels><label>Nr.</label><label>NCSS</label><label>CCN</label><label>Functions</label></labels>
    <item name="parse_a(...) at /tmp/repo/src/a.py:5">
      <value>1</value><value>10</value><value>3</value><value>parse_a</value>
    </item>
    <item name="big_kotlin(...) at /tmp/repo/src/b.kt:15">
      <value>2</value><value>40</value><value>9</value><value>big_kotlin</value>
    </item>
  </measure>
</cppncss>
"""


def test_parse_lizard_xml_extracts_per_file():
    repo_root = Path("/tmp/repo")
    parsed = parse_lizard_xml(_SAMPLE_XML, repo_root=repo_root)
    by_path = {p.path: p for p in parsed}
    assert by_path["src/a.py"].functions[0].name == "parse_a"
    assert by_path["src/a.py"].functions[0].ccn == 3
    assert by_path["src/b.kt"].functions[0].ccn == 9
    assert by_path["src/b.kt"].language == "kotlin"
    assert by_path["src/a.py"].language == "python"


@pytest.mark.asyncio
async def test_run_batch_drop_batch_on_timeout(tmp_path: Path):
    files = [tmp_path / "a.py", tmp_path / "b.py"]
    for f in files:
        f.write_text("def x(): pass\n")

    async def fake(*args, **kwargs):
        raise TimeoutError("simulated")

    with patch(
        "palace_mcp.extractors.hotspot.lizard_runner._invoke_lizard",
        side_effect=fake,
    ):
        result = await run_batch(files, repo_root=tmp_path, timeout_s=1, behavior="drop_batch")
    assert result.parsed == ()
    assert set(result.skipped_files) == {"a.py", "b.py"}


@pytest.mark.asyncio
async def test_run_batch_fail_run_on_timeout_raises(tmp_path: Path):
    files = [tmp_path / "a.py"]
    files[0].write_text("x\n")

    async def fake(*args, **kwargs):
        raise TimeoutError("simulated")

    with patch(
        "palace_mcp.extractors.hotspot.lizard_runner._invoke_lizard",
        side_effect=fake,
    ):
        with pytest.raises(LizardBatchTimeout):
            await run_batch(files, repo_root=tmp_path, timeout_s=1, behavior="fail_run")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/extractors/unit/test_hotspot_lizard_runner.py -v`

Expected: FAIL on `ModuleNotFoundError`.

- [ ] **Step 3: Implement lizard_runner.py**

```python
# services/palace-mcp/src/palace_mcp/extractors/hotspot/lizard_runner.py
from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction

logger = logging.getLogger(__name__)

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python", ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".swift": "swift", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".sol": "solidity",
    ".cpp": "cpp", ".cc": "cpp", ".h": "cpp", ".hpp": "cpp",
    ".m": "objc", ".mm": "objc",
}

_ITEM_RE = re.compile(r"^(?P<name>[^(]+)\(.*\) at (?P<path>.+?):(?P<line>\d+)$")


class LizardBatchTimeout(Exception):
    pass


@dataclass(frozen=True)
class LizardRunResult:
    parsed: tuple[ParsedFile, ...]
    skipped_files: tuple[str, ...]


async def _invoke_lizard(files: list[Path], *, timeout_s: int) -> str:
    proc = await asyncio.create_subprocess_exec(
        "lizard", "--xml", "--working_threads=1", *map(str, files),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return stdout_b.decode("utf-8", errors="replace")


def parse_lizard_xml(xml_text: str, *, repo_root: Path) -> tuple[ParsedFile, ...]:
    if not xml_text.strip():
        return ()
    root = ET.fromstring(xml_text)
    fns_by_path: dict[str, list[ParsedFunction]] = {}
    for item in root.findall(".//measure[@type='Function']/item"):
        name_attr = item.attrib.get("name", "")
        m = _ITEM_RE.match(name_attr)
        if not m:
            continue
        try:
            abs_path = Path(m.group("path"))
            rel = abs_path.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        values = [int(v.text or "0") for v in item.findall("value")]
        if len(values) < 3:
            continue
        nloc, ccn = values[1], values[2]
        params = _count_params(name_attr)
        fns_by_path.setdefault(rel, []).append(
            ParsedFunction(
                name=m.group("name").strip(),
                start_line=int(m.group("line")),
                end_line=int(m.group("line")) + max(nloc - 1, 0),
                ccn=ccn,
                parameter_count=params,
                nloc=nloc,
            )
        )

    out: list[ParsedFile] = []
    for rel, fns in fns_by_path.items():
        ext = Path(rel).suffix
        lang = _EXT_TO_LANG.get(ext, "unknown")
        out.append(ParsedFile(path=rel, language=lang, functions=tuple(fns)))
    return tuple(out)


def _count_params(name_attr: str) -> int:
    try:
        inner = name_attr.split("(", 1)[1].rsplit(")", 1)[0].strip()
    except IndexError:
        return 0
    if not inner:
        return 0
    return len([p for p in inner.split(",") if p.strip()])


async def run_batch(
    files: list[Path],
    *,
    repo_root: Path,
    timeout_s: int,
    behavior: Literal["drop_batch", "fail_run"],
) -> LizardRunResult:
    if not files:
        return LizardRunResult(parsed=(), skipped_files=())
    try:
        xml_text = await _invoke_lizard(files, timeout_s=timeout_s)
    except TimeoutError:
        skipped = tuple(f.relative_to(repo_root).as_posix() for f in files)
        if behavior == "fail_run":
            raise LizardBatchTimeout(
                f"lizard batch timeout ({timeout_s}s) on {len(files)} files; "
                f"first: {skipped[0] if skipped else '<empty>'}"
            )
        logger.warning(
            "hotspot_lizard_batch_timeout",
            extra={"batch_size": len(files), "first_file": skipped[0] if skipped else None},
        )
        return LizardRunResult(parsed=(), skipped_files=skipped)
    parsed = parse_lizard_xml(xml_text, repo_root=repo_root)
    return LizardRunResult(parsed=parsed, skipped_files=())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/extractors/unit/test_hotspot_lizard_runner.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/hotspot/lizard_runner.py services/palace-mcp/tests/extractors/unit/test_hotspot_lizard_runner.py
git commit -m "feat(GIM-195): hotspot lizard_runner — XML parse + timeout policy"
```

---

## Task 5: Neo4j writer Phase 1 + Cypher constants for 3/4/5

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_hotspot_neo4j_writer.py`

- [ ] **Step 1: Write failing test**

```python
# services/palace-mcp/tests/extractors/unit/test_hotspot_neo4j_writer.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction
from palace_mcp.extractors.hotspot.neo4j_writer import (
    PHASE_1_CYPHER, PHASE_3_CYPHER, PHASE_4_EVICT_CYPHER,
    PHASE_5_DEAD_CYPHER, write_file_and_functions,
)


@pytest.mark.asyncio
async def test_phase1_passes_correct_params():
    driver = MagicMock()
    session = MagicMock()
    session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None

    pf = ParsedFile(
        path="src/foo.py", language="python",
        functions=(ParsedFunction(name="bar", start_line=10, end_line=20,
                                  ccn=4, parameter_count=2, nloc=10),),
    )
    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    await write_file_and_functions(
        driver, project_id="gimle", parsed_file=pf, run_started_at=run_at,
    )
    cypher_arg, params = session.run.await_args.args[0], session.run.await_args.args[1]
    assert cypher_arg is PHASE_1_CYPHER
    assert params["project_id"] == "gimle"
    assert params["path"] == "src/foo.py"
    assert params["ccn_total"] == 4
    assert params["run_started_at"] == run_at.isoformat()
    assert params["functions"] == [{
        "name": "bar", "start_line": 10, "end_line": 20,
        "ccn": 4, "parameter_count": 2, "nloc": 10, "language": "python",
    }]


def test_phase1_cypher_sets_complexity_status_fresh():
    assert "complexity_status = 'fresh'" in PHASE_1_CYPHER


def test_phase3_cypher_sets_complexity_status_fresh():
    assert "complexity_status = 'fresh'" in PHASE_3_CYPHER


def test_phase5_cypher_sets_complexity_status_stale():
    assert "complexity_status = 'stale'" in PHASE_5_DEAD_CYPHER


def test_phase4_cypher_uses_last_run_at_cutoff():
    assert "fn.last_run_at < datetime($run_started_at)" in PHASE_4_EVICT_CYPHER
    assert "DETACH DELETE fn" in PHASE_4_EVICT_CYPHER


def test_no_writer_set_on_file_project_id_or_path():
    forbidden = ("SET f.project_id", "SET f.path")
    for cypher in (PHASE_1_CYPHER, PHASE_3_CYPHER, PHASE_5_DEAD_CYPHER):
        for f in forbidden:
            assert f not in cypher
```

- [ ] **Step 2: Run test (fails on ModuleNotFoundError)**

Run: `uv run pytest tests/extractors/unit/test_hotspot_neo4j_writer.py -v`

- [ ] **Step 3: Implement writer Phase 1 + Cypher constants for 3/4/5**

```python
# services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py
from __future__ import annotations

from datetime import datetime
from typing import Any

PHASE_1_CYPHER = """
MERGE (f:File {project_id: $project_id, path: $path})
SET f.ccn_total = $ccn_total,
    f.complexity_status = 'fresh',
    f.last_complexity_run_at = datetime($run_started_at)
WITH f
UNWIND $functions AS fn_in
MERGE (fn:Function {
  project_id: $project_id,
  path: $path,
  name: fn_in.name,
  start_line: fn_in.start_line
})
SET fn.end_line = fn_in.end_line,
    fn.ccn = fn_in.ccn,
    fn.parameter_count = fn_in.parameter_count,
    fn.nloc = fn_in.nloc,
    fn.language = fn_in.language,
    fn.last_run_at = datetime($run_started_at)
MERGE (f)-[:CONTAINS]->(fn)
""".strip()

PHASE_3_CYPHER = """
MERGE (f:File {project_id: $project_id, path: $path})
SET f.churn_count = $churn,
    f.complexity_window_days = $window_days,
    f.hotspot_score = $score,
    f.complexity_status = 'fresh',
    f.last_complexity_run_at = datetime($run_started_at)
""".strip()

PHASE_4_EVICT_CYPHER = """
MATCH (f:File {project_id: $project_id})-[:CONTAINS]->(fn:Function)
WHERE fn.last_run_at < datetime($run_started_at)
DETACH DELETE fn
""".strip()

PHASE_5_DEAD_CYPHER = """
MATCH (f:File {project_id: $project_id})
WHERE NOT f.path IN $alive_paths
  AND coalesce(f.ccn_total, 0) > 0
SET f.ccn_total = 0,
    f.churn_count = 0,
    f.hotspot_score = 0.0,
    f.complexity_status = 'stale',
    f.last_complexity_run_at = datetime($run_started_at)
""".strip()


def _functions_payload(parsed_file: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": fn.name, "start_line": fn.start_line, "end_line": fn.end_line,
            "ccn": fn.ccn, "parameter_count": fn.parameter_count, "nloc": fn.nloc,
            "language": parsed_file.language,
        }
        for fn in parsed_file.functions
    ]


async def write_file_and_functions(
    driver: Any, *, project_id: str, parsed_file: Any, run_started_at: datetime,
) -> None:
    async with driver.session() as session:
        await session.run(
            PHASE_1_CYPHER,
            {
                "project_id": project_id,
                "path": parsed_file.path,
                "ccn_total": parsed_file.ccn_total,
                "run_started_at": run_started_at.isoformat(),
                "functions": _functions_payload(parsed_file),
            },
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/extractors/unit/test_hotspot_neo4j_writer.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py services/palace-mcp/tests/extractors/unit/test_hotspot_neo4j_writer.py
git commit -m "feat(GIM-195): hotspot writer Phase 1 + Cypher constants for 3/4/5 (D1 SET fresh)"
```

---

## Task 6: Churn query — single Cypher round-trip

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/hotspot/churn_query.py`
- Test: append to `test_hotspot_neo4j_writer.py`

- [ ] **Step 1: Append failing test**

```python
@pytest.mark.asyncio
async def test_fetch_churn_builds_correct_cypher_and_cutoff():
    from palace_mcp.extractors.hotspot.churn_query import CHURN_CYPHER, fetch_churn

    driver = MagicMock()
    session = MagicMock()
    session.run = AsyncMock()
    fake_records = [{"path": "src/a.py", "churn": 12}]

    class FakeResult:
        def __aiter__(self):
            self._idx = 0
            return self
        async def __anext__(self):
            if self._idx >= len(fake_records):
                raise StopAsyncIteration
            v = fake_records[self._idx]
            self._idx += 1
            return v

    session.run.return_value = FakeResult()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None

    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    paths = ["src/a.py", "src/b.py"]
    out = await fetch_churn(
        driver, project_id="gimle", paths=paths,
        window_days=90, run_started_at=run_at,
    )
    cypher_arg, params = session.run.await_args.args[0], session.run.await_args.args[1]
    assert cypher_arg is CHURN_CYPHER
    assert params["project_id"] == "gimle"
    assert params["paths"] == paths
    assert params["cutoff"] == "2026-02-03T12:00:00+00:00"
    assert out["src/a.py"] == 12
    assert out["src/b.py"] == 0
```

- [ ] **Step 2: Run** — fails (ModuleNotFoundError).

- [ ] **Step 3: Implement**

```python
# services/palace-mcp/src/palace_mcp/extractors/hotspot/churn_query.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

CHURN_CYPHER = """
UNWIND $paths AS path
MATCH (f:File {project_id: $project_id, path: path})
OPTIONAL MATCH (c:Commit)-[:TOUCHED]->(f)
WHERE c.committed_at >= datetime($cutoff)
RETURN path, count(c) AS churn
""".strip()


async def fetch_churn(
    driver: Any, *, project_id: str, paths: list[str],
    window_days: int, run_started_at: datetime,
) -> dict[str, int]:
    if not paths:
        return {}
    cutoff = (run_started_at - timedelta(days=window_days)).isoformat()
    out: dict[str, int] = {p: 0 for p in paths}
    async with driver.session() as session:
        result = await session.run(
            CHURN_CYPHER,
            {"project_id": project_id, "paths": paths, "cutoff": cutoff},
        )
        async for record in result:
            out[record["path"]] = int(record["churn"])
    return out
```

- [ ] **Step 4: Run** — Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/hotspot/churn_query.py services/palace-mcp/tests/extractors/unit/test_hotspot_neo4j_writer.py
git commit -m "feat(GIM-195): hotspot churn_query — single Cypher round-trip"
```

---

## Task 7: Writer Phases 3, 4, 5 — score + eviction + dead-files

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py`
- Test: append to `test_hotspot_neo4j_writer.py`

- [ ] **Step 1: Append failing tests**

```python
@pytest.mark.asyncio
async def test_write_hotspot_score_passes_correct_params():
    from palace_mcp.extractors.hotspot.neo4j_writer import write_hotspot_score
    driver = MagicMock(); session = MagicMock(); session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None
    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    await write_hotspot_score(
        driver, project_id="gimle", path="src/foo.py",
        churn=12, score=2.45, window_days=90, run_started_at=run_at,
    )
    params = session.run.await_args.args[1]
    assert params == {
        "project_id": "gimle", "path": "src/foo.py",
        "churn": 12, "score": 2.45, "window_days": 90,
        "run_started_at": run_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_evict_stale_functions_passes_run_started_at():
    from palace_mcp.extractors.hotspot.neo4j_writer import evict_stale_functions
    driver = MagicMock(); session = MagicMock(); session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None
    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    await evict_stale_functions(driver, project_id="gimle", run_started_at=run_at)
    assert session.run.await_args.args[1] == {
        "project_id": "gimle", "run_started_at": run_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_mark_dead_files_zero_passes_alive_paths():
    from palace_mcp.extractors.hotspot.neo4j_writer import mark_dead_files_zero
    driver = MagicMock(); session = MagicMock(); session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None
    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    alive = ["src/a.py", "src/b.py"]
    await mark_dead_files_zero(
        driver, project_id="gimle", alive_paths=alive, run_started_at=run_at,
    )
    assert session.run.await_args.args[1] == {
        "project_id": "gimle", "alive_paths": alive,
        "run_started_at": run_at.isoformat(),
    }
```

- [ ] **Step 2: Run** — fails on import errors.

- [ ] **Step 3: Append Phase 3/4/5 functions to neo4j_writer.py**

```python
async def write_hotspot_score(
    driver: Any, *, project_id: str, path: str,
    churn: int, score: float, window_days: int, run_started_at: datetime,
) -> None:
    async with driver.session() as session:
        await session.run(
            PHASE_3_CYPHER,
            {
                "project_id": project_id, "path": path,
                "churn": churn, "score": score, "window_days": window_days,
                "run_started_at": run_started_at.isoformat(),
            },
        )


async def evict_stale_functions(
    driver: Any, *, project_id: str, run_started_at: datetime,
) -> None:
    async with driver.session() as session:
        await session.run(
            PHASE_4_EVICT_CYPHER,
            {"project_id": project_id, "run_started_at": run_started_at.isoformat()},
        )


async def mark_dead_files_zero(
    driver: Any, *, project_id: str, alive_paths: list[str], run_started_at: datetime,
) -> None:
    async with driver.session() as session:
        await session.run(
            PHASE_5_DEAD_CYPHER,
            {
                "project_id": project_id, "alive_paths": alive_paths,
                "run_started_at": run_started_at.isoformat(),
            },
        )
```

- [ ] **Step 4: Run** — Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py services/palace-mcp/tests/extractors/unit/test_hotspot_neo4j_writer.py
git commit -m "feat(GIM-195): hotspot writer Phase 3/4/5 — score + evict + dead-files"
```

---

## Task 8: Cross-extractor `:File` isolation guard test (acceptance #11)

**Files:**
- Create: `services/palace-mcp/tests/extractors/unit/test_cross_extractor_file_isolation.py`

This test IS the implementation — it source-greps the writer.

- [ ] **Step 1: Write the test**

```python
# services/palace-mcp/tests/extractors/unit/test_cross_extractor_file_isolation.py
"""Static guard for spec §3.4 invariant 1 + acceptance #11.

Hotspot extractor must never SET :File.project_id or :File.path; both are
owned by git_history (first-writer-wins).
"""
from __future__ import annotations

import re
from pathlib import Path

import palace_mcp.extractors.hotspot.neo4j_writer as writer_module

_WRITER_SOURCE_PATH = Path(writer_module.__file__)

_FORBIDDEN_PATTERNS = (
    re.compile(r"SET\s+f\.project_id\b"),
    re.compile(r"SET\s+f\.path\b"),
)


def test_hotspot_writer_does_not_set_file_project_id_or_path():
    src = _WRITER_SOURCE_PATH.read_text(encoding="utf-8")
    matches: list[str] = []
    for pat in _FORBIDDEN_PATTERNS:
        for m in pat.finditer(src):
            matches.append(f"{pat.pattern!r} at offset {m.start()}: {m.group(0)!r}")
    assert not matches, (
        "hotspot/neo4j_writer.py violates spec §3.4 invariant 1 — "
        "must not SET :File.project_id or :File.path. Matches:\n  "
        + "\n  ".join(matches)
    )
```

- [ ] **Step 2: Run — should pass already**

Run: `uv run pytest tests/extractors/unit/test_cross_extractor_file_isolation.py -v`

Expected: PASS.

- [ ] **Step 3: Manually verify guard catches violations**

Edit `neo4j_writer.py` PHASE_3_CYPHER to insert a forbidden line (e.g., `SET f.project_id = 'X',`). Re-run the test and confirm it FAILS. Then revert. One-time validation; no commit needed for the mutation.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_cross_extractor_file_isolation.py
git commit -m "test(GIM-195): cross-extractor :File isolation guard (acceptance #11)"
```

---

## Task 9: HotspotExtractor.run() orchestrator

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/hotspot/extractor.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_hotspot_extractor.py`

- [ ] **Step 1: Write failing test**

```python
# services/palace-mcp/tests/extractors/unit/test_hotspot_extractor.py
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor
from palace_mcp.extractors.hotspot.lizard_runner import LizardRunResult
from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction


@pytest.mark.asyncio
async def test_run_executes_phases_in_order(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    (src / "a.py").write_text("def x(): pass\n")

    pf = ParsedFile(
        path="src/a.py", language="python",
        functions=(ParsedFunction(
            name="x", start_line=1, end_line=1, ccn=1,
            parameter_count=0, nloc=1,
        ),),
    )
    fake_run_result = LizardRunResult(parsed=(pf,), skipped_files=())

    graphiti = MagicMock(); graphiti.driver = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="testproj", group_id="project/testproj",
        repo_path=tmp_path, run_id="run-1", duration_ms=0,
        logger=logging.getLogger("test"),
    )

    with (
        patch("palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
              new=AsyncMock(return_value=fake_run_result)),
        patch("palace_mcp.extractors.hotspot.extractor.churn_query.fetch_churn",
              new=AsyncMock(return_value={"src/a.py": 5})),
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_file_and_functions",
              new=AsyncMock()) as m_p1,
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_hotspot_score",
              new=AsyncMock()) as m_p3,
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.evict_stale_functions",
              new=AsyncMock()) as m_p4,
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.mark_dead_files_zero",
              new=AsyncMock()) as m_p5,
    ):
        stats = await HotspotExtractor().run(graphiti=graphiti, ctx=ctx)

    m_p1.assert_awaited_once()
    m_p3.assert_awaited_once()
    m_p4.assert_awaited_once()
    m_p5.assert_awaited_once()

    p3_kwargs = m_p3.await_args.kwargs
    expected = pytest.approx(__import__("math").log(2) * __import__("math").log(6))
    assert p3_kwargs["score"] == expected
    assert p3_kwargs["churn"] == 5
    assert p3_kwargs["window_days"] == 90
    assert stats.nodes_written >= 1


def test_run_no_try_except_around_inner_phases():
    """invariant 7: extractor.run() must not wrap inner phases in try/except."""
    import re
    from palace_mcp.extractors.hotspot import extractor as ext_mod
    src = Path(ext_mod.__file__).read_text(encoding="utf-8")
    m = re.search(r"async def run\(self,.*?\n(?P<body>(?: {4,}.*\n|\n)+)", src)
    assert m is not None
    body = m.group("body")
    assert "try:" not in body, (
        "extractor.run() must not contain try/except around inner phases (invariant 7)"
    )
```

- [ ] **Step 2: Run** — fails on ModuleNotFoundError.

- [ ] **Step 3: Implement extractor**

```python
# services/palace-mcp/src/palace_mcp/extractors/hotspot/extractor.py
from __future__ import annotations

from datetime import datetime, timezone
from itertools import islice
from math import log
from typing import ClassVar, Iterable

from palace_mcp.extractors.base import (
    BaseExtractor, ExtractorRunContext, ExtractorStats,
)
from palace_mcp.extractors.hotspot import (
    churn_query, file_walker, lizard_runner, neo4j_writer,
)
from palace_mcp.extractors.hotspot.models import ParsedFile


def _chunked(it: Iterable, size: int):
    iterator = iter(it)
    while True:
        batch = list(islice(iterator, size))
        if not batch:
            return
        yield batch


class HotspotExtractor(BaseExtractor):
    name: ClassVar[str] = "hotspot"
    description: ClassVar[str] = (
        "Roadmap #44 — Code Complexity × Churn Hotspot. "
        "Reads :Commit-[:TOUCHED]->:File from git_history; "
        "writes :File.{ccn_total,churn_count,hotspot_score} + :Function nodes."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT function_unique IF NOT EXISTS "
        "FOR (f:Function) REQUIRE (f.project_id, f.path, f.name, f.start_line) IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX file_hotspot_score IF NOT EXISTS "
        "FOR (f:File) ON (f.project_id, f.hotspot_score)",
        "CREATE INDEX function_path IF NOT EXISTS "
        "FOR (f:Function) ON (f.project_id, f.path)",
    ]

    async def run(
        self, *, graphiti, ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_settings  # late import per extractor convention
        settings = get_settings()
        run_started_at = datetime.now(tz=timezone.utc)
        files = list(file_walker._walk(ctx.repo_path))

        parsed: list[ParsedFile] = []
        for batch in _chunked(files, settings.hotspot_lizard_batch_size):
            result = await lizard_runner.run_batch(
                batch,
                repo_root=ctx.repo_path,
                timeout_s=settings.hotspot_lizard_timeout_s,
                behavior=settings.hotspot_lizard_timeout_behavior,
            )
            parsed.extend(result.parsed)

        alive_paths = sorted({pf.path for pf in parsed})
        nodes_w = 0
        edges_w = 0

        for pf in parsed:
            await neo4j_writer.write_file_and_functions(
                graphiti.driver,
                project_id=ctx.project_slug,
                parsed_file=pf,
                run_started_at=run_started_at,
            )
            nodes_w += 1 + len(pf.functions)
            edges_w += len(pf.functions)

        churn_map = await churn_query.fetch_churn(
            graphiti.driver,
            project_id=ctx.project_slug,
            paths=alive_paths,
            window_days=settings.hotspot_churn_window_days,
            run_started_at=run_started_at,
        )

        for pf in parsed:
            churn = churn_map.get(pf.path, 0)
            score = log(pf.ccn_total + 1) * log(churn + 1)
            await neo4j_writer.write_hotspot_score(
                graphiti.driver,
                project_id=ctx.project_slug,
                path=pf.path,
                churn=churn,
                score=score,
                window_days=settings.hotspot_churn_window_days,
                run_started_at=run_started_at,
            )
            nodes_w += 1

        await neo4j_writer.evict_stale_functions(
            graphiti.driver,
            project_id=ctx.project_slug,
            run_started_at=run_started_at,
        )

        await neo4j_writer.mark_dead_files_zero(
            graphiti.driver,
            project_id=ctx.project_slug,
            alive_paths=alive_paths,
            run_started_at=run_started_at,
        )

        return ExtractorStats(nodes_written=nodes_w, edges_written=edges_w)
```

- [ ] **Step 4: Run** — Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/hotspot/extractor.py services/palace-mcp/tests/extractors/unit/test_hotspot_extractor.py
git commit -m "feat(GIM-195): HotspotExtractor.run() orchestrator (invariant 7)"
```

---

## Task 10: Register `hotspot` in `EXTRACTORS` registry

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- Test: extend `services/palace-mcp/tests/extractors/unit/test_registry.py`

- [ ] **Step 1: Append failing test**

```python
def test_hotspot_extractor_registered():
    from palace_mcp.extractors.registry import EXTRACTORS
    assert "hotspot" in EXTRACTORS
    inst = EXTRACTORS["hotspot"]
    assert inst.name == "hotspot"
    assert inst.constraints
    assert inst.indexes
```

- [ ] **Step 2: Run** — fails with KeyError.

- [ ] **Step 3: Add registration**

In `services/palace-mcp/src/palace_mcp/extractors/registry.py`, alongside existing entries:

```python
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor

EXTRACTORS["hotspot"] = HotspotExtractor()
```

- [ ] **Step 4: Run all extractor unit tests**

Run: `uv run pytest tests/extractors/unit/ -v`

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/registry.py services/palace-mcp/tests/extractors/unit/test_registry.py
git commit -m "feat(GIM-195): register hotspot in EXTRACTORS"
```

---

## Task 11: Mini-fixture (3-language tree with known CCN/churn)

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/hotspot-mini-project/`

- [ ] **Step 1: Create directory + 4 source files**

Run:

```bash
FIX=services/palace-mcp/tests/extractors/fixtures/hotspot-mini-project
mkdir -p "$FIX/src"
```

Then create the 4 source files via Write tool:

`$FIX/src/python_simple.py` (CCN ~3 total: 2 functions):

```python
def add(a, b):
    return a + b


def safe_div(a, b):
    if b == 0:
        return None
    return a / b
```

`$FIX/src/python_complex.py` (CCN ~7-8):

```python
def classify(n):
    if n < 0:
        return "neg"
    elif n == 0:
        return "zero"
    elif n < 10:
        return "small"
    elif n < 100:
        return "medium"
    else:
        if n < 1000:
            return "large"
        return "huge"
```

`$FIX/src/main.kt` (CCN ~4-5):

```kotlin
fun route(code: Int): String {
    return when (code) {
        200 -> "ok"
        404 -> "missing"
        500 -> "boom"
        else -> "other"
    }
}
```

`$FIX/src/util.ts` (CCN ~3):

```typescript
export function pickLabel(score: number): string {
  if (score < 0) return "invalid";
  if (score < 50) return "low";
  return "high";
}
```

- [ ] **Step 2: Initialize git history with multiple commits per file**

From `$FIX`:

```bash
cd "$FIX"
git init -q
git config user.email fixture@test
git config user.name fixture
git add src/python_simple.py
git commit -q -m "init python_simple"
echo "" >> src/python_simple.py
git commit -aq -m "tweak python_simple"
git add src/python_complex.py
git commit -q -m "init python_complex"
echo "" >> src/python_complex.py
git commit -aq -m "tweak python_complex 1"
echo "" >> src/python_complex.py
git commit -aq -m "tweak python_complex 2"
echo "" >> src/python_complex.py
git commit -aq -m "tweak python_complex 3"
git add src/main.kt
git commit -q -m "init kotlin"
git add src/util.ts
git commit -q -m "init ts"
cd -
```

Expected commits per file (in last 90 days, all freshly created):
- `src/python_simple.py` — 2
- `src/python_complex.py` — 4
- `src/main.kt` — 1
- `src/util.ts` — 1

- [ ] **Step 3: Verify lizard CCN values match expectations**

Run: `uv run lizard "$FIX/src/python_simple.py" "$FIX/src/python_complex.py" "$FIX/src/main.kt" "$FIX/src/util.ts" -E NS`

Note actual per-function CCN values. Update REGEN.md with the observed ranges.

- [ ] **Step 4: Write REGEN.md**

`$FIX/REGEN.md`:

```markdown
# Hotspot mini-fixture regeneration

Used by: `tests/extractors/integration/test_hotspot_integration.py`

## Reset and regenerate

Delete `.git` and `src` and re-run plan Task 11 steps 1+2.

## Expected metrics (after regen)

| File | CCN range | Commits in last 90d |
|------|-----------|---------------------|
| src/python_simple.py | 2-4 | 2 |
| src/python_complex.py | 7-9 | 4 |
| src/main.kt | 4-5 | 1 |
| src/util.ts | 3 | 1 |

Integration test asserts ranges (not exact CCN) because lizard's per-language
parser may differ slightly across versions.
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/hotspot-mini-project/
git commit -m "test(GIM-195): hotspot mini-fixture — 3-language tree with seeded git history"
```

---

## Task 12: Integration test — real Neo4j + idempotency via consume().counters

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_hotspot_integration.py`

The test uses the project's existing testcontainer/compose Neo4j fixture from `conftest.py` (matches `dependency_surface_integration` pattern). Asserts: (a) `:File` props populated, (b) `:Function` nodes present + connected via `:CONTAINS`, (c) re-run produces zero net writes (verified with `result.consume().counters` on a marker MERGE), (d) eviction round zeroes a deleted file's props and DELETEs its `:Function` children.

- [ ] **Step 1: Write the integration test**

```python
# services/palace-mcp/tests/extractors/integration/test_hotspot_integration.py
from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.git_history.extractor import GitHistoryExtractor
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor

FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures" / "hotspot-mini-project"
)


@pytest.fixture
def registered_project(neo4j_driver):
    project_slug = "hotspot-mini"
    with neo4j_driver.session() as session:
        session.run(
            "MERGE (p:Project {slug: $slug}) SET p.group_id = $gid",
            slug=project_slug, gid=f"project/{project_slug}",
        )
    yield project_slug
    with neo4j_driver.session() as session:
        session.run(
            "MATCH (n) WHERE coalesce(n.project_id, n.group_id) "
            "IN [$gid, $slug] DETACH DELETE n",
            gid=f"project/{project_slug}", slug=project_slug,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotspot_full_pipeline(
    registered_project, neo4j_async_driver, graphiti_runtime,
):
    project_slug = registered_project
    ensure_custom_schema(neo4j_async_driver)

    git_ctx = ExtractorRunContext(
        project_slug=project_slug, group_id=f"project/{project_slug}",
        repo_path=FIXTURE, run_id="git-1", duration_ms=0,
        logger=logging.getLogger("test.git"),
    )
    await GitHistoryExtractor().run(graphiti=graphiti_runtime, ctx=git_ctx)

    hot_ctx = ExtractorRunContext(
        project_slug=project_slug, group_id=f"project/{project_slug}",
        repo_path=FIXTURE, run_id="hot-1", duration_ms=0,
        logger=logging.getLogger("test.hot"),
    )
    stats = await HotspotExtractor().run(graphiti=graphiti_runtime, ctx=hot_ctx)
    assert stats.nodes_written > 0

    async with neo4j_async_driver.session() as session:
        result = await session.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "RETURN f.ccn_total AS ccn, f.churn_count AS churn, "
            "f.hotspot_score AS score, f.complexity_status AS status",
            p=project_slug,
        )
        row = await result.single()
        assert row is not None
        assert row["ccn"] >= 6
        assert row["churn"] == 4
        assert row["score"] > 0
        assert row["status"] == "fresh"

        result2 = await session.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'})"
            "-[:CONTAINS]->(fn:Function) RETURN count(fn) AS n",
            p=project_slug,
        )
        n_row = await result2.single()
        assert n_row is not None
        assert n_row["n"] >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotspot_idempotent_via_consume_counters(
    registered_project, neo4j_async_driver, graphiti_runtime,
):
    project_slug = registered_project
    ensure_custom_schema(neo4j_async_driver)

    git_ctx = ExtractorRunContext(
        project_slug=project_slug, group_id=f"project/{project_slug}",
        repo_path=FIXTURE, run_id="git-2", duration_ms=0,
        logger=logging.getLogger("test"),
    )
    await GitHistoryExtractor().run(graphiti=graphiti_runtime, ctx=git_ctx)

    hot = HotspotExtractor()
    hot_ctx = ExtractorRunContext(
        project_slug=project_slug, group_id=f"project/{project_slug}",
        repo_path=FIXTURE, run_id="hot-2", duration_ms=0,
        logger=logging.getLogger("test"),
    )
    await hot.run(graphiti=graphiti_runtime, ctx=hot_ctx)

    async with neo4j_async_driver.session() as session:
        await hot.run(graphiti=graphiti_runtime, ctx=hot_ctx)
        result = await session.run(
            "MERGE (f:File {project_id: $p, path: 'src/python_simple.py'}) "
            "ON CREATE SET f.marker = true",
            p=project_slug,
        )
        summary = await result.consume()
        assert summary.counters.nodes_created == 0
        assert summary.counters.relationships_created == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotspot_eviction_removes_dead_functions(
    registered_project, neo4j_async_driver, graphiti_runtime, tmp_path,
):
    project_slug = registered_project
    ensure_custom_schema(neo4j_async_driver)

    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)

    git_ctx = ExtractorRunContext(
        project_slug=project_slug, group_id=f"project/{project_slug}",
        repo_path=repo, run_id="git-3", duration_ms=0,
        logger=logging.getLogger("test"),
    )
    await GitHistoryExtractor().run(graphiti=graphiti_runtime, ctx=git_ctx)

    hot_ctx_a = ExtractorRunContext(
        project_slug=project_slug, group_id=f"project/{project_slug}",
        repo_path=repo, run_id="hot-3a", duration_ms=0,
        logger=logging.getLogger("test"),
    )
    await HotspotExtractor().run(graphiti=graphiti_runtime, ctx=hot_ctx_a)

    (repo / "src" / "util.ts").unlink()

    hot_ctx_b = ExtractorRunContext(
        project_slug=project_slug, group_id=f"project/{project_slug}",
        repo_path=repo, run_id="hot-3b", duration_ms=0,
        logger=logging.getLogger("test"),
    )
    await HotspotExtractor().run(graphiti=graphiti_runtime, ctx=hot_ctx_b)

    async with neo4j_async_driver.session() as session:
        result = await session.run(
            "MATCH (f:File {project_id: $p, path: 'src/util.ts'}) "
            "RETURN f.ccn_total AS ccn, f.complexity_status AS status",
            p=project_slug,
        )
        row = await result.single()
        assert row is not None
        assert row["ccn"] == 0
        assert row["status"] == "stale"

        result2 = await session.run(
            "MATCH (f:File {project_id: $p, path: 'src/util.ts'})"
            "-[:CONTAINS]->(fn:Function) RETURN count(fn) AS n",
            p=project_slug,
        )
        n_row = await result2.single()
        assert n_row is not None
        assert n_row["n"] == 0
```

- [ ] **Step 2: Run integration test**

```bash
docker compose --profile review up -d --wait
uv run pytest tests/extractors/integration/test_hotspot_integration.py -v
```

Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_hotspot_integration.py
git commit -m "test(GIM-195): hotspot integration — pipeline + idempotency + eviction"
```

---

## Task 13: MCP tool `palace.code.find_hotspots` + 4-row wire-contract

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/code/find_hotspots.py`
- Modify: `services/palace-mcp/src/palace_mcp/server.py`
- Test: `services/palace-mcp/tests/integration/test_find_hotspots_tool.py`

- [ ] **Step 1: Write failing test (4 rows from spec §7.2 error matrix)**

```python
# services/palace-mcp/tests/integration/test_find_hotspots_tool.py
#
# Wire-contract tests use streamablehttp_client + session.call_tool()
# pattern from test_mcp_wire_pattern.py. No mcp_wire helper exists.
from __future__ import annotations

import json

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_unregistered_project_returns_error(mcp_url: str):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots", {"project": "doesnotexist"},
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_registered_no_files_returns_empty(
    mcp_url: str, registered_project_empty,
):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": registered_project_empty},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_with_data_returns_sorted_descending(
    mcp_url: str, seeded_hotspot_project,
):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": seeded_hotspot_project, "top_n": 5},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    rows = resp["result"]
    assert len(rows) > 0
    scores = [r["hotspot_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    for r in rows:
        for k in ("path", "ccn_total", "churn_count",
                  "hotspot_score", "computed_at", "window_days"):
            assert k in r


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_min_score_filter(
    mcp_url: str, seeded_hotspot_project,
):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": seeded_hotspot_project, "min_score": 1.5},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    for r in resp["result"]:
        assert r["hotspot_score"] >= 1.5
```

`registered_project_empty` and `seeded_hotspot_project` fixtures live in `tests/integration/conftest.py`. Extend conftest with two fixtures mirroring the `dependency_surface` pattern: one creates a bare `:Project` node; the other runs `git_history` then `hotspot` on the mini-fixture.

- [ ] **Step 2: Run** — fails (tool not registered).

- [ ] **Step 3: Implement the MCP tool**

```python
# services/palace-mcp/src/palace_mcp/code/find_hotspots.py
from __future__ import annotations

from typing import Any

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"

_QUERY = """
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.hotspot_score, 0.0) >= $min_score
  AND coalesce(f.complexity_status, 'stale') = 'fresh'
RETURN f.path AS path,
       f.ccn_total AS ccn_total,
       f.churn_count AS churn_count,
       f.hotspot_score AS hotspot_score,
       f.last_complexity_run_at AS computed_at,
       f.complexity_window_days AS window_days
ORDER BY f.hotspot_score DESC
LIMIT $top_n
""".strip()


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def find_hotspots(
    *, driver: Any, project: str, top_n: int = 20, min_score: float = 0.0,
) -> dict[str, Any]:
    async with driver.session() as sess:
        row = await (await sess.run(_GET_PROJECT, slug=project)).single()
    if row is None:
        return _error("project_not_registered", f"no :Project {{slug: {project!r}}}", project)
    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        result = await session.run(
            _QUERY,
            {"project_id": project, "top_n": int(top_n), "min_score": float(min_score)},
        )
        async for rec in result:
            rows.append({
                "path": rec["path"],
                "ccn_total": rec["ccn_total"],
                "churn_count": rec["churn_count"],
                "hotspot_score": rec["hotspot_score"],
                "computed_at": rec["computed_at"].iso_format()
                    if rec["computed_at"] is not None else None,
                "window_days": rec["window_days"],
            })
    return {"ok": True, "result": rows}
```

Pattern note: project-registration check uses direct Cypher `MATCH (p:Project {slug: $slug})` + `row is None` (per `runner.py:119-126`). Error response is a plain dict `{"ok": false, "error_code": ..., "message": ...}` via inline `_error()` helper (per `git/tools.py:58-62`). No shared `error_envelope` or `is_project_registered` function exists.

- [ ] **Step 4: Register tool in server.py**

In `services/palace-mcp/src/palace_mcp/server.py`, alongside other `palace.code.*` registrations:

```python
from palace_mcp.code.find_hotspots import find_hotspots as _find_hotspots_impl


@mcp.tool(name="palace.code.find_hotspots")
async def palace_code_find_hotspots(
    project: str, top_n: int = 20, min_score: float = 0.0,
) -> dict[str, Any]:
    return await _find_hotspots_impl(
        driver=app_state.neo4j_driver,
        project=project, top_n=top_n, min_score=min_score,
    )
```

Match the wiring style the codebase uses for other `palace.code.*` tools (copy decorators/imports from `palace.code.find_references`).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/integration/test_find_hotspots_tool.py -v`

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/code/find_hotspots.py services/palace-mcp/src/palace_mcp/server.py services/palace-mcp/tests/integration/test_find_hotspots_tool.py services/palace-mcp/tests/integration/conftest.py
git commit -m "feat(GIM-195): palace.code.find_hotspots MCP tool + 4-row wire contract"
```

---

## Task 14: MCP tool `palace.code.list_functions` + 4-row wire-contract

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/code/list_functions.py`
- Modify: `services/palace-mcp/src/palace_mcp/server.py`
- Test: `services/palace-mcp/tests/integration/test_list_functions_tool.py`

- [ ] **Step 1: Write failing test**

```python
# services/palace-mcp/tests/integration/test_list_functions_tool.py
#
# Wire-contract tests use streamablehttp_client + session.call_tool()
# pattern from test_mcp_wire_pattern.py. No mcp_wire helper exists.
from __future__ import annotations

import json

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_unregistered_project_returns_error(mcp_url: str):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": "doesnotexist", "path": "src/x.py"},
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_missing_file_returns_empty(
    mcp_url: str, seeded_hotspot_project,
):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": seeded_hotspot_project, "path": "src/does_not_exist.py"},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_min_ccn_filter_excludes_low(
    mcp_url: str, seeded_hotspot_project,
):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {
                    "project": seeded_hotspot_project,
                    "path": "src/python_complex.py",
                    "min_ccn": 100,
                },
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_returns_sorted_by_ccn_desc(
    mcp_url: str, seeded_hotspot_project,
):
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": seeded_hotspot_project, "path": "src/python_complex.py", "min_ccn": 0},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    rows = resp["result"]
    assert len(rows) >= 1
    ccns = [r["ccn"] for r in rows]
    assert ccns == sorted(ccns, reverse=True)
    for r in rows:
        for k in ("name", "start_line", "end_line", "ccn",
                  "parameter_count", "nloc", "language"):
            assert k in r
```

- [ ] **Step 2: Run** — fails (tool not registered).

- [ ] **Step 3: Implement the tool**

```python
# services/palace-mcp/src/palace_mcp/code/list_functions.py
from __future__ import annotations

from typing import Any

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"

_QUERY = """
MATCH (f:File {project_id: $project_id, path: $path})-[:CONTAINS]->(fn:Function)
WHERE fn.ccn >= $min_ccn
RETURN fn.name AS name,
       fn.start_line AS start_line,
       fn.end_line AS end_line,
       fn.ccn AS ccn,
       fn.parameter_count AS parameter_count,
       fn.nloc AS nloc,
       fn.language AS language
ORDER BY fn.ccn DESC, fn.start_line ASC
""".strip()


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def list_functions(
    *, driver: Any, project: str, path: str, min_ccn: int = 0,
) -> dict[str, Any]:
    async with driver.session() as sess:
        row = await (await sess.run(_GET_PROJECT, slug=project)).single()
    if row is None:
        return _error("project_not_registered", f"no :Project {{slug: {project!r}}}", project)
    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        result = await session.run(
            _QUERY,
            {"project_id": project, "path": path, "min_ccn": int(min_ccn)},
        )
        async for rec in result:
            rows.append({k: rec[k] for k in (
                "name", "start_line", "end_line", "ccn",
                "parameter_count", "nloc", "language",
            )})
    return {"ok": True, "result": rows}
```

- [ ] **Step 4: Register in server.py**

```python
from palace_mcp.code.list_functions import list_functions as _list_functions_impl


@mcp.tool(name="palace.code.list_functions")
async def palace_code_list_functions(
    project: str, path: str, min_ccn: int = 0,
) -> dict[str, Any]:
    return await _list_functions_impl(
        driver=app_state.neo4j_driver,
        project=project, path=path, min_ccn=min_ccn,
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/integration/test_list_functions_tool.py -v`

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/code/list_functions.py services/palace-mcp/src/palace_mcp/server.py services/palace-mcp/tests/integration/test_list_functions_tool.py
git commit -m "feat(GIM-195): palace.code.list_functions MCP tool + 4-row wire contract"
```

---

## Task 15: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `hotspot` row to registered extractors bullet list**

In `CLAUDE.md` `### Registered extractors` section, append:

```markdown
- `hotspot` — Code-Complexity × Churn Hotspot extractor (GIM-195, Roadmap #44).
  Walks repo with stop-list, calls `lizard` per-batch (50 files), aggregates
  per-function CCN to per-file `ccn_total`, joins with `git_history`'s
  `(:Commit)-[:TOUCHED]->(:File)` graph for churn count in a configurable
  window (default 90 days), writes Tornhill log-log `hotspot_score` on `:File`
  + new `:Function` nodes. Query via `palace.code.find_hotspots(project)` for
  top-N hotspots and `palace.code.list_functions(project, path)` for per-
  function complexity. Requires `git_history` to have run first (otherwise
  churn = 0).
```

- [ ] **Step 2: Add Operator workflow subsection**

Before `### Running an extractor`, add:

```markdown
### Operator workflow: Hotspot extractor

No external `.scip` file or container env file required. The extractor
walks the mounted repo directly and reads commit data from the Neo4j
graph populated by `git_history`.

1. Ensure the repo is mounted in `docker-compose.yml` at `/repos/<slug>`.
2. Run `git_history` first (so `:Commit -[:TOUCHED]-> :File` exists):
   ```
   palace.ingest.run_extractor(name="git_history", project="<slug>")
   ```
3. Run hotspot:
   ```
   palace.ingest.run_extractor(name="hotspot", project="<slug>")
   ```
4. Query top-N:
   ```
   palace.code.find_hotspots(project="<slug>", top_n=20)
   ```
5. For per-function detail on a specific file:
   ```
   palace.code.list_functions(project="<slug>", path="<file>", min_ccn=10)
   ```

**Configurable env vars** (in `.env`, all optional with sane defaults):

| Variable | Default | Notes |
|----------|---------|-------|
| `PALACE_HOTSPOT_CHURN_WINDOW_DAYS` | `90` | Tornhill recommends 90 or 180 |
| `PALACE_HOTSPOT_LIZARD_BATCH_SIZE` | `50` | Files per lizard subprocess |
| `PALACE_HOTSPOT_LIZARD_TIMEOUT_S` | `30` | Per-batch subprocess timeout |
| `PALACE_HOTSPOT_LIZARD_TIMEOUT_BEHAVIOR` | `drop_batch` | `drop_batch` or `fail_run` |

**Trade-off — window changes break idempotency**: changing
`PALACE_HOTSPOT_CHURN_WINDOW_DAYS` between runs overwrites
`:File.churn_count`, `:File.complexity_window_days`, and
`:File.hotspot_score`. Idempotency invariant 4 (zero net writes on
re-run) holds only when window is unchanged. F-followup: multi-window
storage as a separate node type.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(GIM-195): CLAUDE.md — hotspot row + Operator workflow subsection"
```

---

## Task 16: Final pre-PR validation — full lint + tests + push + open PR

- [ ] **Step 1: Run full lint**

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors/hotspot/ src/palace_mcp/code/find_hotspots.py src/palace_mcp/code/list_functions.py
uv run ruff format --check src/palace_mcp/extractors/hotspot/ src/palace_mcp/code/find_hotspots.py src/palace_mcp/code/list_functions.py
```

Expected: all green.

- [ ] **Step 2: Run mypy**

Run: `uv run mypy src/`

Expected: `Success: no issues found`.

- [ ] **Step 3: Run all unit tests**

```bash
uv run pytest tests/extractors/unit/test_hotspot_*.py tests/extractors/unit/test_cross_extractor_file_isolation.py tests/extractors/unit/test_registry.py tests/unit/test_settings_foundation.py -v
```

Expected: all green.

- [ ] **Step 4: Run integration tests**

```bash
docker compose --profile review up -d --wait
uv run pytest tests/extractors/integration/test_hotspot_integration.py tests/integration/test_find_hotspots_tool.py tests/integration/test_list_functions_tool.py -v
```

Expected: all green.

- [ ] **Step 5: Push branch + open PR**

```bash
git push -u origin feature/GIM-195-hotspot-extractor
gh pr create --title "feat(GIM-195): hotspot extractor — Tornhill score + per-function complexity" --body "$(cat <<'EOF'
## Summary

Implements Roadmap #44 — Code Complexity × Churn Hotspot extractor.

- New `hotspot` extractor with 5-phase Cypher pipeline
- Two MCP query tools: `palace.code.find_hotspots`, `palace.code.list_functions`
- Cross-extractor `:File` write isolation enforced by source-grep test
- Lizard timeout policy: `drop_batch` default

Spec: `docs/superpowers/specs/2026-05-04-hotspot-extractor-design.md` (rev2)
Plan: `docs/superpowers/plans/2026-05-04-GIM-195-hotspot-extractor.md`

## QA Evidence

(Populated by QAEngineer in Phase 4.1; see plan Task 16 step 4 for the
required smoke set.)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Verify CI checks**

Run: `gh pr checks`

Expected: lint / typecheck / test / docker-build all green; `qa-evidence-present` becomes green when QAEngineer fills the Evidence section.

---

## Self-review pass (paste into Phase 3.1 CR APPROVE comment)

1. **Spec coverage** — every §2 IN item maps to a Task above:
   - lizard dep + env vars → Task 1
   - models → Task 2
   - file walk + parts-based fixture stop → Task 3
   - lizard subprocess + timeout policy → Task 4
   - 5-phase Cypher writer → Tasks 5, 7
   - churn query → Task 6
   - cross-extractor isolation guard → Task 8 (acceptance #11)
   - extractor.run() orchestrator (no broad try/except) → Task 9
   - registry → Task 10
   - mini-fixture → Task 11
   - integration test (idempotency, eviction) → Task 12
   - find_hotspots MCP tool + 4-row wire contract → Task 13
   - list_functions MCP tool + 4-row wire contract → Task 14
   - CLAUDE.md update → Task 15
2. **Acceptance #1–#11** all covered by Tasks 1–14.
3. **Invariants 1–7** covered:
   - 1: Task 8 (source-grep test) + writer code in Tasks 5/7
   - 2: Task 5 schema constraint + Task 10 registration
   - 3: every Cypher filters on project_id (Tasks 5, 6, 7)
   - 4: Task 12 second integration test
   - 5: Task 12 third integration test (eviction)
   - 6: window stored on :File in Task 7
   - 7: Task 9 source-grep on extractor.run() body
4. **Phase 4.1 smoke set** in spec §9.4 — QAEngineer follows it
   verbatim. uw-android repo is at `/Users/Shared/Android/unstoppable-wallet-android`
   (HEAD `c0489d5a3`) — DO NOT skip with "scope OUT" claim.
