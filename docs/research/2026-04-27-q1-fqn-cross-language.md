# Q1 Research: Cross-language FQN format decision

> **⚠ Scope-limited revision (rev1).** This document covers Q1 for **Python + TypeScript only** (the GIM-104 context). It is preserved for historical and rationale purposes — Variant A/B/C/D analysis here is the source for the Variant B decision still in effect.
>
> **For the full 10-language scope** (adds Java/Kotlin, Swift, C++, Rust+Anchor, Solidity, FunC, Tolk, Move) **and the canonical 12 minimum invariants** every extractor must honor, see **[`2026-04-27-q1-fqn-cross-language-rev2.md`](./2026-04-27-q1-fqn-cross-language-rev2.md)** (GIM-105). Treat rev2 as the active contract; this rev1 file as the deeper rationale for why Variant B was chosen for Python+TS.

**Consumer:** CTO (architectural decision) + MCPEngineer (extractor implementation)
**Decision context:** GIM-104 добавляет `symbol_index_typescript` — второй extractor поверх foundation substrate. Нужно зафиксировать формат `:Symbol.qualified_name` в Neo4j до того, как два языка начнут сосуществовать в графе.
**Recency window:** апрель 2026; SCIP spec и snapshot'ы проверены 2026-04-27.
**Grounded in:** develop @ `1f7c8f2`, feature branches `101b-symbol-index-python`, `extractor-symbol-index-foundation`.

---

## 1. SCIP symbol string format: Python vs TypeScript

### 1.1 Formal grammar (из `scip.proto`)

```
<symbol>    ::= <scheme> ' ' <package> ' ' (<descriptor>)+
<package>   ::= <manager> ' ' <package-name> ' ' <version>
<descriptor> ::= <namespace>  (name '/')
              |  <type>       (name '#')
              |  <term>       (name '.')
              |  <method>     (name '(' [disambiguator] ').')
              |  <type-param> ('[' name ']')
              |  <parameter>  ('(' name ')')
              |  <meta>       (name ':')
              |  <macro>      (name '!')
```

Источник: [sourcegraph/scip/scip.proto](https://github.com/sourcegraph/scip/blob/main/scip.proto) `[HIGH]`

### 1.2 Конкретные примеры

**Python** (scip-python, scheme `scip-python`, manager `python`):

| Конструкция | SCIP symbol string |
|---|---|
| Module init | `scip-python python requests 2.0.0 requests/__init__:` |
| Function | `scip-python python requests 2.0.0 \`requests.api\`/get().` |
| Class | `scip-python python snapshot-util 0.1 class_nohint/Example#` |
| Method | `scip-python python snapshot-util 0.1 class_nohint/Example#something().` |
| Field | `scip-python python snapshot-util 0.1 class_nohint/Example#y.` |
| Parameter | `scip-python python snapshot-util 0.1 class_nohint/Example#__init__().(in_val)` |
| Stdlib | `scip-python python python-stdlib 3.11 builtins/int#` |

Источник: snapshot'ы в [sourcegraph/scip-python](https://github.com/sourcegraph/scip-python/tree/scip/packages/pyright-scip/snapshots/output) `[HIGH]`

**TypeScript** (scip-typescript, scheme `scip-typescript`, manager `npm`):

| Конструкция | SCIP symbol string |
|---|---|
| File root | `scip-typescript npm syntax 1.0.0 src/\`class.ts\`/` |
| Class | `scip-typescript npm syntax 1.0.0 src/\`class.ts\`/Class#` |
| Method | `scip-typescript npm syntax 1.0.0 src/\`class.ts\`/Class#method().` |
| Constructor | `scip-typescript npm syntax 1.0.0 src/\`class.ts\`/Class#\`<constructor>\`().` |
| Interface | `scip-typescript npm syntax 1.0.0 src/\`interface.ts\`/Interface#` |
| Property | `scip-typescript npm syntax 1.0.0 src/\`interface.ts\`/Interface#property.` |
| Type param | `scip-typescript npm syntax 1.0.0 src/\`type-alias.ts\`/C#[T]` |
| Cross-pkg ref | `scip-typescript npm @example/a 1.0.0 src/\`index.ts\`/a().` |

Источник: snapshot'ы в [sourcegraph/scip-typescript](https://github.com/sourcegraph/scip-typescript/tree/main/snapshots/output) `[HIGH]`

**JavaScript** (тот же scip-typescript):

| Конструкция | SCIP symbol string |
|---|---|
| Function | `scip-typescript npm pure-js 1.0.0 src/\`main.js\`/fib().` |
| Variable | `scip-typescript npm pure-js 1.0.0 src/\`main.js\`/y.` |

JS файлы обрабатываются scip-typescript с `--infer-tsconfig` или `allowJs: true`. Формат символов идентичен TS. `[HIGH]`

### 1.3 Ключевые структурные различия

| Свойство | Python | TypeScript/JS |
|---|---|---|
| Scheme | `scip-python` | `scip-typescript` |
| Manager | `python` | `npm` |
| Namespace convention | `module/` (dotted names escaped) | `src/\`file.ts\`/` (filename escaped) |
| Constructor | `__init__().` | `\`<constructor>\`().` |
| Module init marker | `__init__:` (meta) | нет аналога |
| Descriptor grammar | **Идентична** | **Идентична** |

Дескрипторная грамматика (суффиксы `/ # . (). [] () : !`) **одна и та же** — оба индексера реализуют один и тот же `scip.proto`. Различия только в scheme prefix и tooling conventions. `[HIGH]`

---

## 2. Каноничный формат для `:Symbol.qualified_name`

### 2.1 Текущее состояние

`scip_parser.py:_extract_qualified_name()` (ветка `101b-symbol-index-python`):
```python
parts = scip_symbol.strip().split(" ")
name_parts = [p for p in parts[2:] if p and p != "."]
return ".".join(name_parts)
```

Это **отрезает scheme+manager**, берёт всё после них (package, version, descriptors) и соединяет точкой. Пример:
- Input: `scip-python python requests 2.0.0 requests/__init__:`
- Output: `requests.2.0.0.requests/__init__:`

Проблемы текущего подхода:
1. **Version в qualified_name** — `requests.2.0.0.requests/...` содержит версию, что ломает cross-version symbol matching (та же функция `get()` из `requests 2.0.0` и `requests 2.1.0` получит разные qualified_name).
2. **Descriptor suffixes сохранены** (`/`, `#`, `.`, `().`) — но точка-разделитель конфликтует с term descriptor `.`.
3. **Backtick escaping сохранён** — `` `requests.api` `` внутри qualified_name.

### 2.2 Варианты

#### Вариант A: Хранить raw SCIP symbol string as-is

```
qualified_name = "scip-python python requests 2.0.0 requests/__init__:"
```

| Pro | Con |
|---|---|
| Zero information loss | Очень длинные строки в Neo4j |
| Легко парсить обратно в компоненты | Version в строке — cross-version matching невозможен |
| Точно соответствует upstream spec | `symbol_id_for()` будет давать разные id для разных версий одного символа |

#### Вариант B: Strip scheme+manager+version, keep descriptors

```
qualified_name = "requests requests/__init__:"
# или для TS:
qualified_name = "syntax src/`class.ts`/Class#method()."
```

Формат: `<package-name> <descriptor-chain>`

| Pro | Con |
|---|---|
| Cross-version matching работает | Потеря scheme → не знаем исходный язык из строки |
| Короче, читабельнее | Package name может конфликтовать между ecosystem'ами |
| Descriptor suffixes сохранены | Нужен regex/parser для восстановления компонентов |

#### Вариант C: Нормализованный формат с language prefix

```
qualified_name = "python:requests:requests/__init__:"
# или для TS:
qualified_name = "npm:syntax:src/`class.ts`/Class#method()."
```

Формат: `<manager>:<package-name>:<descriptor-chain>`

| Pro | Con |
|---|---|
| Уникальность через manager prefix | Не стандартный формат — только наш |
| Cross-version matching | Потеря scheme (но она redundant с manager) |
| Разумная длина | Нужен parser |
| Language derivable от manager | — |

#### Вариант D (текущий, исправленный): Strip scheme+manager, keep rest

```
qualified_name = "requests.2.0.0.requests/__init__:"
```

Отброшен — version в qualified_name ломает cross-version matching.

### 2.3 Рекомендация: **Вариант B** — strip scheme+manager+version

**Обоснование:**

1. `symbol_id_for()` хеширует `qualified_name` → **critical** чтобы одна и та же функция `requests.api.get()` давала одинаковый `symbol_id` независимо от версии пакета. Иначе при обновлении `requests 2.0.0 → 2.1.0` все symbol id меняются, и Neo4j граф теряет связность.

2. Language уже хранится в поле `:SymbolOccurrence.language` (enum) — не нужно дублировать в qualified_name.

3. Package ecosystem derivable из `Language` enum: `PYTHON → pypi`, `TYPESCRIPT/JAVASCRIPT → npm`.

4. Descriptor suffixes (`/`, `#`, `.`, `().`, `[]`) сохранены — это **lossless** представление структуры символа.

**Формат:**
```
qualified_name = "<package-name> <descriptor-chain>"
```

Примеры:
```
# Python
requests requests/__init__:
requests `requests.api`/get().
snapshot-util class_nohint/Example#something().
python-stdlib builtins/int#

# TypeScript
syntax src/`class.ts`/Class#method().
@example/a src/`index.ts`/a().
pure-js src/`main.js`/fib().
```

**Нужно исправить `_extract_qualified_name()`**: текущая реализация через `split(" ")` и `join(".")` некорректна. Правильная логика:

```python
def _extract_qualified_name(scip_symbol: str) -> str:
    """Strip scheme + manager + version, keep package-name + descriptors.
    
    SCIP format: '<scheme> <manager> <package-name> <version> <descriptors...>'
    Result: '<package-name> <descriptors-joined>'
    """
    parts = scip_symbol.strip().split(" ")
    # parts[0] = scheme, parts[1] = manager
    # parts[2] = package-name, parts[3] = version
    # parts[4:] = descriptor tokens
    if len(parts) < 5:
        return scip_symbol
    package_name = parts[2]
    descriptor_chain = " ".join(p for p in parts[4:] if p)
    return f"{package_name} {descriptor_chain}"
```

**Но**: space-separated representation неудобна для Neo4j queries. Оставляем пробел, т.к. он — часть SCIP grammar (descriptors не содержат пробелов по spec, кроме escaped double-space, который экзотический edge case).

---

## 3. Generics: strip или keep в qualified_name?

### Findings

**TypeScript:** Type parameters кодируются как отдельные символы `[T]`, вложенные в parent:
```
syntax src/`type-alias.ts`/C#      ← generic class C<T>
syntax src/`type-alias.ts`/C#[T]   ← type parameter T сам по себе
```

Generic instantiations (`Map<string, number>`) **НЕ** получают собственных символов. Только uninstantiated generic (`Map#`) + отдельные type parameter symbols (`Map#[K]`, `Map#[V]`). `[HIGH]`

**Python:** scip-python **не поддерживает** type parameter descriptors. `TypeVar` и `Generic[T]` не эмитируют `[T]` символы. Generic классы индексируются как обычные. `[HIGH]`

### Decision: **Keep** type parameter descriptors as-is

1. Type parameter symbols (`C#[T]`) — это отдельные SymbolOccurrence с собственным qualified_name. Они не являются частью qualified_name класса `C#`.
2. Stripping их потребовала бы специальной логики и потеряла бы информацию.
3. Generic instantiations не генерируют символов — нет проблемы дублирования `Map<string,number>` vs `Map<K,V>`.
4. Python не эмитирует type parameters → нет cross-language consistency issue.

**Правило:** `qualified_name` хранит exactly что SCIP эмитирует (после strip scheme+manager+version). Если SCIP выдаёт `C#[T]` — храним `C#[T]`. Если не выдаёт (Python) — и не будет.

---

## 4. Language enum: TYPESCRIPT + JAVASCRIPT раздельно vs единый?

### Текущее состояние

`foundation/models.py` определяет:
```python
class Language(str, Enum):
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    ...
```

### Факты

1. scip-typescript обрабатывает и `.ts/.tsx` и `.js/.jsx` файлы **одним пакетом** с одинаковым scheme `scip-typescript`.
2. Формат символов **идентичен** для TS и JS.
3. Различие: JS файлы не имеют type parameter symbols `[T]`.
4. Из SCIP symbol string **невозможно** определить TS vs JS — нужно смотреть на `Document.relative_path` (расширение файла).

### Decision: **Оставить раздельно** TYPESCRIPT + JAVASCRIPT

**Обоснование:**

1. **Файловый контекст**: когда пользователь спрашивает "покажи символы из JS файлов" — нужна фильтрация по language. Unified enum потеряет эту возможность.
2. **Совместимость с будущими индексерами**: если появится scip-javascript (отдельный) — не нужна миграция enum.
3. **SCIP metadata**: `scip_pb2.Language` enum тоже разделяет TypeScript и JavaScript (разные числовые значения).
4. **Стоимость**: extractor просто проверяет расширение файла из `Document.relative_path`. Минимальная логика:

```python
def _language_from_path(relative_path: str) -> Language:
    if relative_path.endswith((".ts", ".tsx")):
        return Language.TYPESCRIPT
    if relative_path.endswith((".js", ".jsx")):
        return Language.JAVASCRIPT
    return Language.UNKNOWN
```

5. **Для Neo4j запросов**: `WHERE s.language IN ["typescript", "javascript"]` — тривиально если нужна группировка.

---

## 5. Decision summary

| Вопрос | Решение | Уверенность |
|---|---|---|
| **qualified_name формат** | Strip scheme+manager+version, keep `<package-name> <descriptor-chain>` | `[HIGH]` — based on cross-version matching requirement + SCIP spec |
| **Generics в qualified_name** | Keep as-is (type param symbols — отдельные occurrences) | `[HIGH]` — follows SCIP spec design |
| **Language enum** | TYPESCRIPT + JAVASCRIPT раздельно (derive from file extension) | `[HIGH]` — matches SCIP proto enum + enables file-type filtering |
| **`_extract_qualified_name` fix** | Нужна переработка: текущая реализация включает version в qname | `[HIGH]` — bug в существующем коде |

### Что откладываем на N+3+ языки

1. **Cross-language symbol dedup** — один и тот же symbol может существовать в TS `.d.ts` файле и Python type stub. Пока храним оба с разными qualified_name (разный package-name). Dedup стратегия — followup.
2. **Ecosystem-qualified uniqueness** — если npm пакет `foo` и pypi пакет `foo` оба в графе, их символы будут иметь одинаковый package-name в qualified_name. Пока это acceptable: `symbol_id` будет разным т.к. descriptor chain различается. Если коллизии станут проблемой — добавим ecosystem prefix (Вариант C).
3. **Non-SCIP indexers** (Kotlin, Swift, Rust, Solidity, FunC) — формат qualified_name будет зависеть от инструментов. SCIP имеет индексеры для Rust (`scip-rust` = rust-analyzer) и Kotlin (`scip-java` + Kotlin support). Если они следуют той же грамматике — формат qualified_name автоматически совместим. Для Solidity/FunC/Anchor нужны custom extractors с synthetic symbol strings.

### Action items для GIM-104

1. **Fix `_extract_qualified_name()`** в `scip_parser.py` — убрать version из qualified_name.
2. **Добавить `_language_from_path()`** для определения TYPESCRIPT vs JAVASCRIPT.
3. **Не хардкодить `language=Language.PYTHON`** в `iter_scip_occurrences()` — сделать параметром.
4. **Обновить `symbol_id_for()` doctring** — уточнить что input = version-stripped qualified_name.

---

## Источники

| Источник | Тип | Дата | Tier |
|---|---|---|---|
| [sourcegraph/scip — scip.proto](https://github.com/sourcegraph/scip/blob/main/scip.proto) | Official spec | 2026-04-27 | 1 |
| [sourcegraph/scip-python snapshots](https://github.com/sourcegraph/scip-python/tree/scip/packages/pyright-scip/snapshots/output) | Source code | 2026-04-27 | 1 |
| [sourcegraph/scip-typescript snapshots](https://github.com/sourcegraph/scip-typescript/tree/main/snapshots/output) | Source code | 2026-04-27 | 1 |
| [scip-typescript ScipSymbol.ts](https://github.com/sourcegraph/scip-typescript/blob/main/src/ScipSymbol.ts) | Source code | 2026-04-27 | 1 |
| [scip-python ScipSymbol.ts](https://github.com/sourcegraph/scip-python/blob/scip/packages/pyright-scip/src/ScipSymbol.ts) | Source code | 2026-04-27 | 1 |
| [npm @sourcegraph/scip-typescript](https://www.npmjs.com/package/@sourcegraph/scip-typescript) | Registry | 2026-04-27 | 1 |
| scip-typescript issue #280 (JS-only repo inference) | GitHub issue | 2026-04-27 | 2 |
| Существующий код: `scip_parser.py`, `foundation/models.py`, `identifiers.py` (ветка `101b-symbol-index-python`) | Codebase | 2026-04-27 | 1 |
