# GIM-184 - iOS C/C++/Obj-C extractor via scip-clang - Plan

**Статус:** Phase 1.1 CTO formalization, rev2, 2026-05-03.
**Issue:** GIM-184 (`e92ed4c3-6b7f-4d72-ab1c-c16bc70ae89e`).
**Ветка:** `feature/GIM-184-ios-clang-extractor`.
**Base из issue:** `develop@365c9c42233ad125728f27048101a01e4899d2cf`.
**Спека:** `docs/superpowers/specs/2026-05-03-GIM-184-ios-clang-extractor.md`.
**Предшественник:** GIM-128 Swift extractor закрыт и смержен.

## Намерение

Поставить `symbol_index_clang`: palace-mcp extractor для iOS native C/C++ и, только если это доказано smoke-тестом, Objective-C символов из заранее сгенерированных `scip-clang` SCIP indexes.

Первый gate - не реализация. Первый gate - iMac smoke, который доказывает, что установленный `scip-clang` генерирует пригодный `.scip` для `.c`, `.cpp` и `.m` через ручной мини `compile_commands.json`. Если Objective-C smoke падает или даёт низкое качество, v1 явно сужается до C/C++, а Obj-C становится follow-up.

## Upstream Truth, Проверенный В Phase 1.1

- README Sourcegraph `scip-clang` сейчас заявляет поддержку C, C++ и CUDA, arm64 macOS binary releases, JSON compilation database input и запуск из project root через `scip-clang --compdb-path=path/to/compile_commands.json`.
- Тот же README рекомендует для больших codebase сначала запускать diagnostics на урезанном compdb через `--show-compiler-diagnostics`.
- Sourcegraph indexer docs перечисляют C/C++ через `scip-clang`; Objective-C там не указан как поддерживаемый язык.
- Существующий repo research `docs/research/2026-04-27-q1-fqn-cross-language-rev2.md` уже фиксирует empty-manager форму `scip-clang` symbols и риски backtick/operator descriptors. Это полезный prior art, но не замена GIM-184 iMac smoke.

## Scope

### In

- Parser support для `scip-clang` symbols с empty manager fields, package/version placeholders и backtick-safe descriptors.
- Language support для C, C++ и Objective-C только после smoke-подтверждения safe detection.
- `symbol_index_clang.py`, зарегистрированный через существующий extractor registry и `FindScipPath` / `palace_scip_index_paths` flow.
- Mixed native fixture с app-level и in-repo vendor code (`Pods/`, `Carthage/`, `SourcePackages/`, `third_party/`, `Vendor/`).
- Тесты parser, language detection, qname canonicalization, SDK exclusion, vendor routing, checkpoints и Tantivy lookup через `symbol_id_for(qname)`.

### Out

- Swift emitter changes.
- Multi-repo SPM bundle ingest из GIM-182.
- Custom clang emitter.
- Full call graph, data-flow, macro expansion semantics или Objective-C++ как v1 promise.
- Production deploy automation changes.

## Final v1 Language Gate

До implementation assignment Phase 1.1b должен зафиксировать один из исходов:

- **C/C++/Obj-C v1:** C, C++ и `.m` smoke все эмитят usable DEF/DECL plus USE occurrences, parser role/language counts стабильны, и Tantivy lookup по `symbol_id_for(symbol_qualified_name)` работает.
- **C/C++ v1:** C и C++ проходят, но `.m` output отсутствует, нестабилен или недостаточно различим. Спека должна оставить Objective-C как follow-up до начала реализации.
- **Stop/revise:** C падает, или C++ падает без явного operator acceptance для C-only v1.

`.mm` - только optional interop probe. Его провал не влияет на v1.

## Phase Steps

| Step | Description | Acceptance Criteria | Suggested Owner | Affected Files / Paths | Dependencies |
|---|---|---|---|---|---|
| 1.1a | CTO формализует существующие spec/plan и проверяет duplicate/prior-art state. | Plan rev2 существует; upstream `scip-clang` truth зафиксирован; code files не изменены; GIM-184 не duplicate GIM-128/GIM-182. | CXCTO | `docs/superpowers/plans/2026-05-03-GIM-184-ios-clang-extractor.md`; существующая спека только если smoke меняет scope. | Operator-approved Phase 1.0 artefacts. |
| 1.1b | Запустить iMac smoke до implementation assignment. | Evidence comment включает `xcodebuild -version`, `clang --version`, `scip-clang --version`, ручной mini `compile_commands.json`, команду/output `scip-clang`, role/language/path counts для `.c`, `.cpp`, `.m`, хотя бы один `symbol_id_for(qname)` value и Tantivy lookup по symbol id. | CXQAEngineer | Smoke workspace на iMac; будущий fixture path `services/palace-mcp/tests/extractors/fixtures/uw-ios-clang-mini-project/` при реализации. | Step 1.1a. |
| 1.1c | CTO фиксирует final language scope по smoke evidence. | Issue comment явно говорит `v1 = C/C++/Obj-C` или `v1 = C/C++ only`; если Obj-C сужен, spec/plan упоминают follow-up до implementation. | CXCTO | `docs/superpowers/specs/2026-05-03-GIM-184-ios-clang-extractor.md`; этот план, если scope меняется. | Step 1.1b. |
| 1.2 | Review plan/spec до engineering. | CXCodeReviewer approves architecture, scope, handoff, verification gates, `palace_scip_index_paths` wiring и no runner `scip_path` override. | CXCodeReviewer | `docs/superpowers/specs/2026-05-03-GIM-184-ios-clang-extractor.md`; этот план. | Step 1.1c. |
| 2.1 | Реализовать parser/language foundations для native SCIP. | `Language.C`, `Language.CPP` и, если gated, `Language.OBJECTIVE_C` добавлены; `_SCIP_LANGUAGE_MAP` и extension fallback соответствуют спеке; headers остаются UNKNOWN без document language или доказанного TU context; qname parser покрывает empty manager и backticks. | CXPythonEngineer | `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`; `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`; parser unit tests. | Step 1.2. |
| 2.2 | Реализовать `symbol_index_clang` extractor и registry wiring. | Extractor resolves `.scip` через `FindScipPath.resolve(project_slug, settings)` и `palace_scip_index_paths`; runtime runner `scip_path` override не добавлен; system SDK/toolchain paths исключаются до phase selection; in-repo vendor paths идут в vendor handling. | CXPythonEngineer | `services/palace-mcp/src/palace_mcp/extractors/symbol_index_clang.py`; `services/palace-mcp/src/palace_mcp/extractors/registry.py`; extractor unit tests. | Step 2.1. |
| 2.3 | Добавить committed mini fixture и regeneration notes. | Fixture включает app-level C/C++ и final-scope Obj-C если gated, плюс in-repo vendor native files; `REGEN.md` документирует точные scip-clang, clang/Xcode, compdb command, SCIP command, counts и scope result. | CXPythonEngineer with CXQAEngineer evidence input | `services/palace-mcp/tests/extractors/fixtures/uw-ios-clang-mini-project/`; `REGEN.md`; generated `scip/index.scip`. | Step 1.1b and Step 2.1. |
| 2.4 | Добавить integration coverage для checkpoints и Tantivy search. | Tests доказывают enabled phase checkpoints, app/vendor representation и `search_by_symbol_id_async(symbol_id_for(qname))` находит хотя бы один native definition и один reference. | CXPythonEngineer | `services/palace-mcp/tests/extractors/integration/test_symbol_index_clang_integration.py`; related test fixtures. | Steps 2.2 and 2.3. |
| 3.1 | Mechanical code review. | CXCodeReviewer approves code, tests, scope adherence и подтверждает, что каждый изменённый code/test file находится в declared GIM-184 scope. | CXCodeReviewer | PR diff. | Step 2.x pushed. |
| 3.2 | Adversarial architecture review. | CodexArchitectReviewer approves no hidden runner API expansion, no SDK/header phase explosion, no unsupported Obj-C promise, and no cross-branch carry-over. | CodexArchitectReviewer | PR diff and evidence comments. | Step 3.1. |
| 4.1 | QA live smoke and integration evidence. | CXQAEngineer runs targeted tests plus real runtime smoke with palace-mcp, records commit SHA, health/tool call, checkpoint evidence, Tantivy symbol lookup, and checkout restoration. | CXQAEngineer | Runtime environment and evidence comment. | Step 3.2. |
| 4.2 | Merge-readiness and close. | CXCTO runs mandatory `gh pr view` merge-state evidence, merges only after required gates pass, verifies Phase 4.1 evidence is authored by CXQAEngineer, and closes the issue after deploy/merge evidence. | CXCTO | PR into `develop`; issue thread. | Step 4.1. |

## Implementation Acceptance Criteria

- `symbol_index_clang` зарегистрирован и runnable через существующий extractor runner.
- Parser обрабатывает валидные `scip-clang` empty-manager symbols, `.` package/version placeholders и backtick/operator descriptors без qname corruption.
- Final language set следует smoke result; `.m` не включается без Gate C evidence.
- `.h`, `.hh`, `.hpp` и `.hxx` не назначаются blindly в C/C++/Obj-C только по extension.
- System SDK/toolchain headers не раздувают `phase1_defs`.
- In-repo vendor/native dependency paths покрыты и тестируются отдельно от app-level files.
- App/vendor same-descriptor collision behavior протестирован и либо предотвращён, либо задокументирован как v1 limitation до implementation handoff.
- Fixture ingest пишет ожидаемые checkpoints для enabled phases.
- Tantivy search находит хотя бы один native symbol definition и один native reference через `symbol_id_for(symbol_qualified_name)`.

## Verification Commands

Initial iMac smoke, до implementation:

```bash
xcodebuild -version
clang --version
scip-clang --version
cd <native-mini-project-root>
cat compile_commands.json
scip-clang --compdb-path=compile_commands.json --index-file=scip/index.scip
```

Parser and symbol-id evidence, run from `services/palace-mcp` after the smoke SCIP exists:

```bash
uv run python - <<'PY'
from collections import Counter
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file

idx = parse_scip_file("tests/extractors/fixtures/uw-ios-clang-mini-project/scip/index.scip")
occs = list(iter_scip_occurrences(idx, commit_sha="smoke", ingest_run_id="smoke"))
print("count", len(occs))
print("kind", Counter(o.kind.value for o in occs))
print("language", Counter(o.language.value for o in occs))
print("paths", sorted({o.file_path for o in occs})[:20])
for qname in sorted({o.symbol_qualified_name for o in occs})[:10]:
    print(symbol_id_for(qname), qname)
PY
```

Targeted tests after implementation:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_scip_parser*.py
uv run pytest tests/extractors/unit/test_symbol_index_clang.py
uv run pytest tests/extractors/integration/test_symbol_index_clang_integration.py
```

Pre-review implementation gate:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors tests/extractors
uv run mypy src
uv run pytest tests/extractors
```

## Risks

- **Objective-C может не поддерживаться scip-clang.** Mitigation: `.m` - hard smoke gate, не v1 assumption.
- **Compilation database generation может стать основной сложностью slice.** Mitigation: сначала ручной mini compdb; Bear/xcodebuild capture только после tiny smoke.
- **Headers могут дублироваться между translation units.** Mitigation: tests должны проявить duplicate behavior и задокументировать, deduplicates ли v1 или принимает output как есть.
- **System SDK symbols могут перегрузить phase1.** Mitigation: system paths исключаются до phase selection.
- **Placeholder package `.` может collide между app/vendor symbols.** Mitigation: collision test обязателен до implementation handoff.

## Open Questions

- Какой exact `scip-clang` release или distribution должен быть pinned для iMac smoke?
- Если Obj-C smoke проходит, идентифицирует ли `document.language` `.m`, или implementation должна rely on safe `.m` extension fallback?
- Vendor DEF/DECL occurrences в v1 исключать или роутить в будущую dedicated vendor-def phase?
