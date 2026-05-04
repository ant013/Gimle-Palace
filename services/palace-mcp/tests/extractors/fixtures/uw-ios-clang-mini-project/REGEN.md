# uw-ios-clang-mini-project Fixture Regeneration

Коммитнутый fixture фиксирует минимальный native C/C++ slice для GIM-184:
app-level `C` + app-level `C++` + in-repo vendor `Pods/` + один system SDK
document для проверки раннего отсева.

## Зафиксированный источник истины

- Принятый smoke для GIM-184 Phase 1.1b выполнен на arm64 macOS хосте.
- В текущем workspace `scip-clang` отсутствует, поэтому локальная регенерация в этом запуске не выполнялась; ниже зафиксированы принятые smoke facts и команды для повторяемой регенерации на подходящем macOS host.

### Принятые tool/version facts

```text
$ xcode-select -p
/Applications/Xcode.app/Contents/Developer

$ xcodebuild -version
Xcode 26.3
Build version 17C529

$ clang --version
Apple clang version 17.0.0 (clang-1700.6.4.2)
Target: arm64-apple-darwin25.4.0
Thread model: posix

$ scip-clang --version
scip-clang 0.4.0
```

### Принятые SDK paths

```text
/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator26.2.sdk
/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS26.2.sdk
```

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

`regen.sh` пишет `compile_commands.json` со следующими compile commands:

```bash
clang -c Sources/UwMiniApp/main.c -I Sources/UwMiniCore/Math -o build/main.o
clang++ -std=c++17 -c Sources/UwMiniCore/Math/Vector.cpp -I Sources/UwMiniCore/Math -o build/Vector.o
clang -c Pods/Foo/Foo.c -I Sources/UwMiniCore/Math -o build/Foo.o
```

SCIP generation command:

```bash
scip-clang --compdb-path="$ROOT/compile_commands.json" --index-file="$OUT"
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

## Scope Result

- Принятый итог smoke и fixture scope для GIM-184 v1: `C/C++ only`.
- Objective-C `.m` и Objective-C++ `.mm` не входят в expectations этого fixture.

## Known v1 Limitation

- Placeholder package `.` в `scip-clang` может давать одинаковый `symbol_qualified_name`/`symbol_id` для app symbol и vendor USE symbol с одинаковым descriptor.
- Это поведение зафиксировано unit-тестом `test_same_descriptor_app_vendor_collision_is_documented_v1_limitation`; в GIM-184 v1 collision не предотвращается namespace-prefixing'ом, а только документируется.
