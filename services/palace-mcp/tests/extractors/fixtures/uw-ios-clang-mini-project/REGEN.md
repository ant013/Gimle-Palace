# uw-ios-clang-mini-project Fixture Regeneration

Коммитнутый fixture фиксирует минимальный native C/C++ slice для GIM-184:
app-level `C` + app-level `C++` + in-repo vendor `Pods/` + один system SDK
document для проверки раннего отсева.

## Зафиксированный источник истины

- Принятый smoke для GIM-184 Phase 1.1b выполнен на arm64 macOS хосте.
- Подтверждённые инструменты smoke:
  - `scip-clang 0.4.0`
  - Xcode toolchain / iPhoneSimulator SDK
  - `clang`
- В текущем workspace `scip-clang` отсутствует, поэтому локальная регенерация в этом запуске не выполнялась; ниже зафиксированы команды для повторяемой регенерации на подходящем macOS host.

## Oracle Counts

### Raw SCIP fixture

| Metric | Value |
|---|---:|
| N_DOCUMENTS_TOTAL | 4 |
| N_DEFS_TOTAL | 4 |
| N_USES_TOTAL | 3 |
| N_OCCURRENCES_TOTAL | 7 |

### Post-filter extractor counts

| Phase | Value |
|---|---:|
| phase1_defs | 2 |
| phase2_user_uses | 2 |
| phase3_vendor_uses | 1 |

`Pods/Foo/Foo.c` DEF excluded from v1. System SDK `stdio.h` excluded до phase selection.

## Fixture Layout

- `Sources/UwMiniApp/main.c`
- `Sources/UwMiniCore/Math/Vector.cpp`
- `Sources/UwMiniCore/Math/Vector.h`
- `Pods/Foo/Foo.c`
- `scip/index.scip`

## Regeneration

```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-ios-clang-mini-project
./regen.sh
```

Ожидаемый индексатор:

```bash
scip-clang --version
# scip-clang 0.4.0
```

После регенерации проверьте parser/extractor oracle:

```bash
cd ../../../../..
uv run python - <<'PY'
from collections import Counter
from pathlib import Path

from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file

fixture = Path("tests/extractors/fixtures/uw-ios-clang-mini-project/scip/index.scip")
index = parse_scip_file(fixture)
occs = list(iter_scip_occurrences(index, commit_sha="regen"))
print("documents", len(index.documents))
print("kinds", Counter(o.kind.value for o in occs))
print("languages", Counter(o.language.value for o in occs))
print("paths", sorted({o.file_path for o in occs}))
PY
```

