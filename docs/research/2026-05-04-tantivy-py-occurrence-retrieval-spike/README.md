# Tantivy-py occurrence retrieval spike

**Date:** 2026-05-04  
**Issue:** GIM-192  
**Library:** `tantivy` from `services/palace-mcp/.venv`

## Goal

Проверить, можно ли в GIM-192 v1 достать `commit_sha`, `phase`, `line`, `col_start`, `col_end`
из existing Tantivy docs без schema migration.

## Commands

### 1. Introspection inside service venv

```bash
cd services/palace-mcp
uv run python - <<'PY'
import tantivy
print('tantivy module', tantivy.__file__)
print('Searcher attrs:', [a for a in dir(tantivy.Searcher) if 'field' in a.lower() or 'doc' in a.lower()])
print('Document attrs:', [a for a in dir(tantivy.Document) if 'dict' in a.lower() or 'field' in a.lower()])
PY
```

Observed:

- `Searcher` exposes `doc`, `doc_freq`, `num_docs`
- `Document` exposes `to_dict`, `get_first`, `get_all`

### 2. Can `Searcher.doc()` see non-stored fast fields?

```bash
cd services/palace-mcp
uv run python - <<'PY'
from pathlib import Path
import tempfile
import tantivy

with tempfile.TemporaryDirectory() as td:
    p = Path(td)
    b = tantivy.SchemaBuilder()
    b.add_text_field('doc_key', stored=True, tokenizer_name='raw')
    b.add_integer_field('line', fast=True, indexed=True, stored=False)
    b.add_integer_field('col_end', fast=True, indexed=False, stored=False)
    s = b.build()
    idx = tantivy.Index(s, path=str(p))
    w = idx.writer()
    w.add_document(tantivy.Document.from_dict({'doc_key':'a','line':1,'col_end':7}, s))
    w.commit(); idx.reload()
    searcher = idx.searcher()
    res = searcher.search(idx.parse_query('doc_key:a'), 10)
    doc = searcher.doc(res.hits[0][1])
    print('to_dict', doc.to_dict())
    print('line first', doc.get_first('line'))
    print('col_end first', doc.get_first('col_end'))
PY
```

Observed:

- `to_dict {'doc_key': ['a']}`
- `line first None`
- `col_end first None`

Conclusion: non-stored fast fields are not retrievable through `Searcher.doc()`.

### 3. Is changing `stored=` on an existing field backward-compatible?

```bash
cd services/palace-mcp
uv run python - <<'PY'
from pathlib import Path
import tempfile
import tantivy

with tempfile.TemporaryDirectory() as td:
    p = Path(td)
    b1 = tantivy.SchemaBuilder()
    b1.add_text_field('doc_key', stored=True, tokenizer_name='raw')
    b1.add_integer_field('line', fast=True, indexed=True, stored=False)
    s1 = b1.build()
    idx1 = tantivy.Index(s1, path=str(p))
    w = idx1.writer()
    w.add_document(tantivy.Document.from_dict({'doc_key':'a','line':1}, s1))
    w.commit(); idx1.reload()

    b2 = tantivy.SchemaBuilder()
    b2.add_text_field('doc_key', stored=True, tokenizer_name='raw')
    b2.add_integer_field('line', fast=True, indexed=True, stored=True)
    s2 = b2.build()
    try:
        idx2 = tantivy.Index(s2, path=str(p))
        idx2.reload()
        print('schema change reopened ok')
    except Exception as exc:
        print(type(exc).__name__, str(exc))
PY
```

Observed:

- `ValueError Schema error: 'An index exists but the schema does not match.'`

Conclusion: changing `stored=` on an existing field is a real schema migration.

## Decision for GIM-192 v1

- Query filter stays on existing indexed fields: `symbol_id`, `commit_sha`, `phase`
- `file_path` and `commit_sha` come directly from stored fields
- `line` and `col_start` are reconstructed from `doc_key`
- `col_end` remains unavailable in persisted Tantivy evidence until a separate reviewed schema slice lands
