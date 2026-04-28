# GIM-113 — Extend ts-mini-project + py-mini-project fixture coverage

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close silent scope reduction from GIM-104: PE shipped 2+3 fixture files instead of planned 6+5. Add missing edge-case fixture files (JSX, generics, default export, JS interop, @dataclass, decorators) and extend test assertions to cover them.

**Predecessor SHA:** `54691a7` (GIM-104 merge — TS extractor + 2-file ts-mini-project + 3-file py-mini-project)

**Spec:** Issue body GIM-113 (Board-authored, grounded in post-merge diff of PR #57)

**Root path prefix:** `services/palace-mcp/` — all paths below are relative to repo root.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/Cache.ts` | Create | Generic class `Cache<K, V>` with `put`/`get` methods |
| `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/Logger.ts` | Create | `export default class Logger` (default-export edge case) |
| `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/Button.tsx` | Create | React functional component with props interface (JSX namespace) |
| `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/legacy.js` | Create | CommonJS `module.exports = function helper()` (JS interop) |
| `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/index.ts` | Modify | Add re-exports for Cache, Logger (Button/legacy import may differ) |
| `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/tsconfig.json` | Modify | Add `"jsx": "react"`, `"allowJs": true` |
| `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/package.json` | Modify | Add `"@types/react"` dev dependency |
| `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/index.scip` | Regenerate | `npx @sourcegraph/scip-typescript index --output index.scip` |
| `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/cache.py` | Create | `class Cache(Generic[K, V])` via TypeVar |
| `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/logger.py` | Create | `@functools.lru_cache` decorated method |
| `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/legacy.py` | Create | `@dataclass class Config` |
| `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/main.py` | Modify | Import + use Cache, Logger, Config from new modules |
| `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/__init__.py` | Modify | Re-export new symbols |
| `services/palace-mcp/tests/extractors/fixtures/py-mini-project/index.scip` | Regenerate | `npx @sourcegraph/scip-python index --project-name pymini` |
| `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py` | Modify | Add edge-case assertions per coverage matrix |
| `services/palace-mcp/tests/extractors/unit/test_scip_parser.py` | Modify | Add unit tests for `_extract_qualified_name()` edge cases |

---

## Task 1: Add TS fixture source files (Cache.ts, Logger.ts, Button.tsx, legacy.js)

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/Cache.ts`
- Create: `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/Logger.ts`
- Create: `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/Button.tsx`
- Create: `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/legacy.js`

**Steps:**
- [ ] Create `Cache.ts`: generic class `Cache<K, V>` with `private store: Map<K, V>`, `put(key: K, value: V): void`, `get(key: K): V | undefined`. Export named.
- [ ] Create `Logger.ts`: `export default class Logger` with `log(message: string): void` method. Must use `export default` syntax (not named export) to produce the SCIP default-export descriptor.
- [ ] Create `Button.tsx`: `interface ButtonProps { label: string; onClick: () => void }` + `export const Button: React.FC<ButtonProps> = (props) => <button onClick={props.onClick}>{props.label}</button>`. Import React.
- [ ] Create `legacy.js`: CommonJS module — `function helper(x) { return x + 1; } module.exports = { helper };`. No TypeScript, no ES6 export.

**Acceptance criteria:**
- 4 new files exist under `ts-mini-project/src/`.
- Each file is minimal (10–25 lines) but exercises the specific SCIP edge case it targets.
- `Cache.ts` compiles with `tsc` (generics must be syntactically valid).
- `Button.tsx` compiles with `"jsx": "react"` in tsconfig.
- `legacy.js` is valid CommonJS.

---

## Task 2: Update TS fixture config files (tsconfig.json, package.json, index.ts)

**Files:**
- Modify: `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/tsconfig.json`
- Modify: `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/package.json`
- Modify: `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/index.ts`

**Steps:**
- [ ] `tsconfig.json`: add `"jsx": "react"` and `"allowJs": true` to `compilerOptions`. Keep existing options intact.
- [ ] `package.json`: add `"@types/react": "^18.0.0"` to `devDependencies`. Run `npm install` in the fixture directory to update `package-lock.json`.
- [ ] `index.ts`: add `export { Cache } from './Cache';` and `import Logger from './Logger'; export { Logger };`. For Button: `export { Button } from './Button';`. For legacy.js: `export { helper } from './legacy';` (may need `// @ts-ignore` or allowJs handles it).

**Acceptance criteria:**
- `tsc --noEmit` in `ts-mini-project/` succeeds (no compile errors).
- `index.ts` re-exports at least Cache, Logger, Button, helper.

---

## Task 3: Regenerate TS index.scip

**Files:**
- Regenerate: `services/palace-mcp/tests/extractors/fixtures/ts-mini-project/index.scip`

**Steps:**
- [ ] `cd services/palace-mcp/tests/extractors/fixtures/ts-mini-project/`
- [ ] `npm install` (if not done in Task 2)
- [ ] `npx @sourcegraph/scip-typescript index --output index.scip`
- [ ] Verify: parse the new `index.scip` with `scip print --json index.scip | head -50` or Python: `parse_scip_file(path)` returns documents for all 6 source files.
- [ ] Commit the binary.

**Acceptance criteria:**
- `index.scip` parses without error.
- Contains documents for: `greeter.ts`, `index.ts`, `Cache.ts`, `Logger.ts`, `Button.tsx`, `legacy.js`.
- File size reasonable (10–20 KB).

**IMPORTANT — SCIP toolchain prerequisite:** `@sourcegraph/scip-typescript` must be available. If not installed globally, use `npx`. Verify with `npx @sourcegraph/scip-typescript --version` before running. If unavailable on CI, mark the `.scip` as a vendored binary (already the pattern from GIM-104).

---

## Task 4: Add Python fixture source files (cache.py, logger.py, legacy.py)

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/cache.py`
- Create: `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/logger.py`
- Create: `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/legacy.py`

**Steps:**
- [ ] Create `cache.py`: `from typing import TypeVar, Generic` + `K = TypeVar('K')` + `V = TypeVar('V')` + `class Cache(Generic[K, V]):` with `__init__(self)`, `put(self, key: K, value: V) -> None`, `get(self, key: K) -> V | None`.
- [ ] Create `logger.py`: `import functools` + `class Logger:` with `@functools.lru_cache(maxsize=128)` on a `get_logger(cls, name: str) -> "Logger"` classmethod.
- [ ] Create `legacy.py`: `from dataclasses import dataclass` + `@dataclass class Config:` with `name: str`, `debug: bool = False`, `max_retries: int = 3`.

**Acceptance criteria:**
- 3 new files exist under `py-mini-project/src/pymini/`.
- Each file is minimal (10–20 lines), syntactically valid Python 3.11+.
- `cache.py` uses `Generic[K, V]` (produces generic type-param descriptors in SCIP).
- `legacy.py` uses `@dataclass` (produces `__init__` in SCIP).

---

## Task 5: Update Python fixture wiring (main.py, __init__.py)

**Files:**
- Modify: `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/__init__.py`
- Modify: `services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/main.py`

**Steps:**
- [ ] `__init__.py`: add `from .cache import Cache`, `from .logger import Logger`, `from .legacy import Config` to existing exports.
- [ ] `main.py`: add imports from `pymini` for Cache, Logger, Config. Add usage: `cache = Cache[str, int]()`, `config = Config(name="test")`, etc.

**Acceptance criteria:**
- `python -c "from pymini import Cache, Logger, Config"` succeeds (from `src/` directory).
- `main.py` references all new symbols (produces USE occurrences in SCIP).

---

## Task 6: Regenerate Python index.scip

**Files:**
- Regenerate: `services/palace-mcp/tests/extractors/fixtures/py-mini-project/index.scip`

**Steps:**
- [ ] `cd services/palace-mcp/tests/extractors/fixtures/py-mini-project/`
- [ ] `npx @sourcegraph/scip-python index --project-name pymini --output index.scip`
- [ ] Verify: parse produces documents for all source files including new ones.
- [ ] Commit the binary.

**Acceptance criteria:**
- `index.scip` parses without error.
- Contains documents for: `__init__.py`, `greeter.py`, `main.py`, `cache.py`, `logger.py`, `legacy.py`.

**SCIP toolchain prerequisite:** `@sourcegraph/scip-python` must be available. Same pattern as Task 3.

---

## Task 7: Extend test assertions in test_real_scip_fixtures.py

**Files:**
- Modify: `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py`

**Steps:**
- [ ] **TS — generic class:** Add test `test_cache_generic_class_present` — parse TS SCIP, assert a DEF occurrence with `"Cache"` in qualified_name exists.
- [ ] **TS — default export:** Add test `test_logger_default_export_present` — assert a DEF occurrence for Logger exists. Verify the SCIP symbol string contains a default-export marker (the exact format depends on scip-typescript output — inspect the regenerated index.scip first, then assert).
- [ ] **TS — JSX namespace:** Add test `test_button_tsx_jsx_component` — assert `Button.tsx` appears as a document in the index. Assert at least one occurrence from that document has TYPESCRIPT language.
- [ ] **TS — JS interop:** Add test `test_legacy_js_javascript_language` — assert `legacy.js` document exists and its occurrences have `Language.JAVASCRIPT` (not TYPESCRIPT).
- [ ] **Python — generic class:** Add test `test_cache_generic_class_present` — assert a DEF for Cache exists in Python occurrences.
- [ ] **Python — dataclass:** Add test `test_config_dataclass_present` — assert a DEF for Config exists. Optionally check for `__init__` generated symbol.
- [ ] **Python — decorated method:** Add test `test_logger_decorated_method` — assert Logger class DEF exists.

**Acceptance criteria:**
- All new test methods in `TestTsMiniProjectFixture` and `TestPyMiniProjectFixture` pass.
- Tests use existing `requires_scip_typescript` / `requires_scip_python` markers.
- No regression in existing tests.

**NOTE on symbol format:** The exact SCIP symbol strings for generics, default exports, JSX are tool-version-dependent. PE MUST inspect the actual regenerated `.scip` output before writing assertions. Write assertions grounded in observed output, not spec assumptions. If the observed SCIP output differs from spec expectations (e.g., no `[T]` in generic descriptors), document the delta and adjust assertions.

---

## Task 8: Add _extract_qualified_name() edge-case unit tests

**Files:**
- Modify: `services/palace-mcp/tests/extractors/unit/test_scip_parser.py`

**Steps:**
- [ ] Add parametrized test for `_extract_qualified_name()` with inputs:
  - Standard: `"scip-typescript npm ts-mini-project 1.0.0 src/Cache.ts Cache#"` → `"ts-mini-project src/Cache.ts Cache#"`
  - Generic descriptor: whatever form scip-typescript emits for `Cache<K,V>.put` (inspect from Task 3 output).
  - Default export: whatever form scip-typescript emits for `export default class Logger`.
  - JSX namespace: if scip-typescript emits `<react>/...` references.
  - Short symbol (< 5 parts): verify passthrough behavior.
- [ ] Verify edge cases don't crash or produce empty strings.

**Acceptance criteria:**
- Parametrized test covers at least 5 input variants.
- All pass.

**Depends on:** Task 3 (need actual SCIP output to know real symbol formats).

---

## Task 9: CI verification + commit

**Steps:**
- [ ] Run `uv run ruff check services/palace-mcp/` — no lint errors.
- [ ] Run `uv run mypy services/palace-mcp/src/` — no type errors.
- [ ] Run `uv run pytest services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py -v` — all pass.
- [ ] Run `uv run pytest services/palace-mcp/tests/ -m "not slow"` — no regressions.
- [ ] Verify file counts:
  - `git ls-tree HEAD services/palace-mcp/tests/extractors/fixtures/ts-mini-project/src/ | wc -l` → 6 (greeter.ts, index.ts, Cache.ts, Logger.ts, Button.tsx, legacy.js)
  - `git ls-tree HEAD services/palace-mcp/tests/extractors/fixtures/py-mini-project/src/pymini/ | wc -l` → 5 (\_\_init\_\_.py, greeter.py, cache.py, logger.py, legacy.py)
  - `py-mini-project/src/main.py` also present (total 6 Python source files across both dirs).
- [ ] Push feature branch. Open PR into `develop`.

**Acceptance criteria:**
- CI green.
- File counts match.
- PR description references GIM-113 and predecessor `54691a7`.

---

## Phase chain (from spec)

| Phase | Owner | Gate |
|-------|-------|------|
| 1.1 Formalize | CTO | Plan file exists, GIM-NN swapped |
| 1.2 Plan-first review | CodeReviewer | Every task has test+impl+commit; flag gaps |
| 2 Implement | PythonEngineer | TDD: failing assertions → fixture files → regen .scip → green |
| 3.1 Mechanical review | CodeReviewer | `uv run ruff check && uv run mypy src/ && uv run pytest` output + **file count verification via `ls`** (post-GIM-104 lesson) |
| 3.2 Adversarial review | OpusArchitectReviewer | Coverage matrix audit |
| 4.1 QA (light) | QAEngineer | CI green + drift check + file count |
| 4.2 Merge | CTO | GIM-108 merge-readiness discipline |

## Coverage matrix (reference for Phase 3.2 audit)

| Edge case | Fixture file | SCIP feature | Test assertion |
|-----------|-------------|--------------|----------------|
| TS generics | Cache.ts | Type-param descriptors in symbol string | `test_cache_generic_class_present` |
| TS default export | Logger.ts | Default-export SCIP marker | `test_logger_default_export_present` |
| TS JSX namespace | Button.tsx | JSX/React namespace in symbols | `test_button_tsx_jsx_component` |
| TS JS interop | legacy.js | `Document.language="javascript"` | `test_legacy_js_javascript_language` |
| Py generics | cache.py | Generic[K,V] type-param descriptor | `test_cache_generic_class_present` |
| Py dataclass | legacy.py | `@dataclass`-generated `__init__` | `test_config_dataclass_present` |
| Py decorator | logger.py | `@lru_cache` decorated method | `test_logger_decorated_method` |

## Spec clarification: file count discrepancy

Board spec mentions 7 TS files including `User.ts` — but `User.ts` is not in the scope-in file list and was likely a leftover from an earlier draft. Actual TS files = 6: `greeter.ts`, `index.ts`, `Cache.ts`, `Logger.ts`, `Button.tsx`, `legacy.js`. This plan uses 6.

Board spec's Python file count (6) is correct: `__init__.py`, `greeter.py`, `main.py`, `cache.py`, `logger.py`, `legacy.py`. Note: `main.py` is at `src/main.py`, not `src/pymini/main.py`.
