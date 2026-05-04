#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$ROOT/scip/index.scip"

mkdir -p "$ROOT/build" "$ROOT/scip"

cat > "$ROOT/compile_commands.json" <<JSON
[
  {
    "directory": "$ROOT",
    "command": "clang -c Sources/UwMiniApp/main.c -I Sources/UwMiniCore/Math -o build/main.o",
    "file": "Sources/UwMiniApp/main.c"
  },
  {
    "directory": "$ROOT",
    "command": "clang++ -std=c++17 -c Sources/UwMiniCore/Math/Vector.cpp -I Sources/UwMiniCore/Math -o build/Vector.o",
    "file": "Sources/UwMiniCore/Math/Vector.cpp"
  },
  {
    "directory": "$ROOT",
    "command": "clang -c Pods/Foo/Foo.c -I Sources/UwMiniCore/Math -o build/Foo.o",
    "file": "Pods/Foo/Foo.c"
  }
]
JSON

scip-clang --compdb-path="$ROOT/compile_commands.json" --index-file="$OUT"
test -s "$OUT"
echo "Wrote $OUT"
