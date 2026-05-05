# Hotspot mini-fixture regeneration

Used by: `tests/extractors/integration/test_hotspot_integration.py`

## Reset and regenerate

Delete `.git` and `src` and re-run plan Task 11 steps 1+2 (or run `bash regen.sh`).

## Source file CCN (verified via `uv run lizard src/ -E NS` on 2026-05-05)

| File | Function | CCN | CCN total |
|------|----------|-----|-----------|
| src/python_simple.py | add | 1 | 3 |
| src/python_simple.py | safe_div | 2 | |
| src/python_complex.py | classify | 6 | 6 |
| src/main.kt | route | 4 | 4 |
| src/util.ts | pickLabel | 3 | 3 |

## Expected metrics (after regen, all commits fresh within 90 days)

| File | CCN total | Commits in last 90d |
|------|-----------|---------------------|
| src/python_simple.py | 3 | 2 |
| src/python_complex.py | 6 | 4 |
| src/main.kt | 4 | 1 |
| src/util.ts | 3 | 1 |

## Git history

8 commits, single branch (main):

1. init python_simple
2. tweak python_simple
3. init python_complex
4. tweak python_complex 1
5. tweak python_complex 2
6. tweak python_complex 3
7. init kotlin
8. init ts
