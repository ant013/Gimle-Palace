#!/bin/sh
# Startup ownership check for Tantivy data volume (GIM-101a T10 — Architect F19).
# Fails fast if /var/lib/palace/tantivy is not writable by the current user,
# preventing silent write failures mid-ingest.

TANTIVY_DIR="${PALACE_TANTIVY_INDEX_PATH:-/var/lib/palace/tantivy}"

if [ ! -d "$TANTIVY_DIR" ]; then
    echo "ERROR: Tantivy index directory '$TANTIVY_DIR' does not exist." >&2
    echo "       Mount the 'palace-tantivy-data' volume at $TANTIVY_DIR." >&2
    exit 1
fi

if [ ! -w "$TANTIVY_DIR" ]; then
    echo "ERROR: Tantivy index directory '$TANTIVY_DIR' is not writable by UID $(id -u)." >&2
    echo "       Expected volume ownership: 1000:1000 (appuser)." >&2
    echo "       Current owner: $(stat -c '%u:%g' "$TANTIVY_DIR" 2>/dev/null || stat -f '%u:%g' "$TANTIVY_DIR")" >&2
    exit 1
fi

exec "$@"
