"""One-shot Neo4j migration modules.

Each module is runnable as `python -m palace_mcp.migrations.<name>` and
exposes an async `run_migration(driver) -> int` returning the row count migrated.
All migrations are idempotent (safe to re-run).
"""
