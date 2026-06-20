"""Unit tests for ensure_custom_schema (GIM-101a, T6) — mocked Neo4j driver."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.foundation.schema import (
    EXPECTED_SCHEMA,
    SchemaDriftError,
    _constraint_cypher,
    _fulltext_cypher,
    _index_cypher,
    ensure_custom_schema,
)


class TestSchemaDefinition:
    def test_has_nine_constraints(self) -> None:
        # 3 original + 6 git_history + 2 dead_symbol_binary_surface + 1 symbol_unique
        assert len(EXPECTED_SCHEMA.constraints) == 12

    def test_has_nine_indexes(self) -> None:
        # symbol_qname_group_lookup dropped (superseded by symbol_unique constraint)
        # and symbol_group_run_lookup was added for incremental liveness bumps.
        assert len(EXPECTED_SCHEMA.indexes) == 9

    def test_has_one_fulltext(self) -> None:
        assert len(EXPECTED_SCHEMA.fulltext_indexes) == 1

    def test_total_twenty_one_objects(self) -> None:
        # 12 constraints + 9 indexes + 1 fulltext
        total = (
            len(EXPECTED_SCHEMA.constraints)
            + len(EXPECTED_SCHEMA.indexes)
            + len(EXPECTED_SCHEMA.fulltext_indexes)
        )
        assert total == 22

    def test_all_names_unique(self) -> None:
        names = EXPECTED_SCHEMA.all_names()
        assert len(names) == 22

    def test_expected_names_present(self) -> None:
        names = EXPECTED_SCHEMA.all_names()
        assert "ext_dep_purl_unique" in names
        assert "eviction_record_unique" in names
        assert "ingest_checkpoint_unique" in names
        assert "dead_symbol_candidate_id_unique" in names
        assert "binary_surface_record_id_unique" in names
        assert "shadow_evict_r1" in names
        assert "shadow_count_by_group" in names
        assert "dead_symbol_candidate_lookup" in names
        assert "binary_surface_record_lookup" in names
        assert "symbol_embedding_idx" in names
        assert "symbol_group_run_lookup" in names
        assert "symbol_qn_fulltext" in names

    def test_symbol_embedding_idx_present(self) -> None:
        names = EXPECTED_SCHEMA.all_names()
        assert "symbol_embedding_idx" in names

    def test_symbol_embedding_idx_config(self) -> None:
        idx = next(
            i for i in EXPECTED_SCHEMA.indexes if i.name == "symbol_embedding_idx"
        )
        assert idx.label == "Symbol"
        assert idx.properties == ("embedding",)
        assert idx.type == "VECTOR"
        assert idx.vector_dimensions == 1536
        assert idx.vector_similarity_function == "cosine"


class TestCypherGeneration:
    def test_constraint_cypher_unique(self) -> None:
        c = EXPECTED_SCHEMA.constraints[0]
        stmt = _constraint_cypher(c)
        assert "CREATE CONSTRAINT" in stmt
        assert c.name in stmt
        assert "IF NOT EXISTS" in stmt

    def test_index_cypher(self) -> None:
        i = EXPECTED_SCHEMA.indexes[0]
        stmt = _index_cypher(i)
        assert "CREATE INDEX" in stmt
        assert i.name in stmt
        assert "IF NOT EXISTS" in stmt

    def test_vector_index_cypher(self) -> None:
        i = next(
            index
            for index in EXPECTED_SCHEMA.indexes
            if index.name == "symbol_embedding_idx"
        )
        stmt = _index_cypher(i)
        assert "CREATE VECTOR INDEX" in stmt

    def test_vector_index_cypher_symbol_embedding(self) -> None:
        idx = next(
            i for i in EXPECTED_SCHEMA.indexes if i.name == "symbol_embedding_idx"
        )
        stmt = _index_cypher(idx)
        assert "CREATE VECTOR INDEX symbol_embedding_idx IF NOT EXISTS" in stmt
        assert "FOR (n:Symbol) ON (n.embedding)" in stmt
        assert "`vector.dimensions`: 1536" in stmt
        assert "`vector.similarity_function`: 'cosine'" in stmt

    def test_fulltext_cypher(self) -> None:
        f = EXPECTED_SCHEMA.fulltext_indexes[0]
        stmt = _fulltext_cypher(f)
        assert "CREATE FULLTEXT INDEX" in stmt
        assert f.name in stmt
        assert "IF NOT EXISTS" in stmt


async def _async_records(
    records: Sequence[Mapping[str, object]],
) -> AsyncIterator[Mapping[str, object]]:
    for r in records:
        yield r


class TestEnsureCustomSchema:
    def _make_driver(
        self,
        constraint_records: Sequence[Mapping[str, object]] | None = None,
        index_records: Sequence[Mapping[str, object]] | None = None,
    ) -> MagicMock:
        """Build a mocked AsyncDriver whose session runs queries cleanly."""
        if constraint_records is None:
            constraint_records = []
        if index_records is None:
            index_records = []

        async def run_side_effect(
            query: str, *args: object, **kwargs: object
        ) -> object:
            if "SHOW CONSTRAINTS" in query:
                return _async_records(constraint_records)
            if "SHOW INDEXES" in query:
                return _async_records(index_records)
            return _async_records([])

        session = AsyncMock()
        session.run = AsyncMock(side_effect=run_side_effect)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        driver = MagicMock()
        driver.session = MagicMock(return_value=session)
        return driver

    @pytest.mark.asyncio
    async def test_cold_neo4j_runs_all_statements(self) -> None:
        driver = self._make_driver()
        await ensure_custom_schema(driver)
        expected_calls = (
            2  # SHOW CONSTRAINTS + SHOW INDEXES (drift detection)
            + 1  # DROP INDEX symbol_qname_group_lookup IF EXISTS
            + len(EXPECTED_SCHEMA.constraints)
            + len(EXPECTED_SCHEMA.indexes)
            + len(EXPECTED_SCHEMA.fulltext_indexes)
        )
        call_count = driver.session.return_value.run.call_count
        assert call_count == expected_calls

    @pytest.mark.asyncio
    async def test_cold_neo4j_creates_vector_index(self) -> None:
        driver = self._make_driver()
        await ensure_custom_schema(driver)
        queries = [
            call.args[0] for call in driver.session.return_value.run.await_args_list
        ]
        assert any(
            "CREATE VECTOR INDEX symbol_embedding_idx IF NOT EXISTS" in query
            and "FOR (n:Symbol) ON (n.embedding)" in query
            and "`vector.dimensions`: 1536" in query
            and "`vector.similarity_function`: 'cosine'" in query
            for query in queries
        )

    @pytest.mark.asyncio
    async def test_idempotent_second_call_no_error(self) -> None:
        driver = self._make_driver()
        await ensure_custom_schema(driver)
        await ensure_custom_schema(driver)  # must not raise

    @pytest.mark.asyncio
    async def test_show_constraints_error_does_not_propagate(self) -> None:
        """If SHOW CONSTRAINTS fails (older Neo4j), drift detection is skipped gracefully."""

        async def run_side_effect(
            query: str, *args: object, **kwargs: object
        ) -> object:
            if "SHOW" in query:
                raise Exception("SHOW not supported")
            return _async_records([])

        session = AsyncMock()
        session.run = AsyncMock(side_effect=run_side_effect)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        driver = MagicMock()
        driver.session = MagicMock(return_value=session)
        # Should not raise
        await ensure_custom_schema(driver)

    @pytest.mark.asyncio
    async def test_conflicting_constraint_raises_schema_drift_error(self) -> None:
        """Constraint with same name but different properties → SchemaDriftError."""
        conflicting = [
            {
                "name": "ext_dep_purl_unique",
                "properties": ["wrong_prop"],
                "labelsOrTypes": ["ExternalDependency"],
            }
        ]
        driver = self._make_driver(constraint_records=conflicting)
        with pytest.raises(SchemaDriftError, match="ext_dep_purl_unique"):
            await ensure_custom_schema(driver)

    @pytest.mark.asyncio
    async def test_conflicting_index_raises_schema_drift_error(self) -> None:
        """Index with same name but different properties → SchemaDriftError."""
        conflicting_indexes = [
            {
                "name": "shadow_evict_r1",
                "properties": ["wrong_field"],
                "labelsOrTypes": ["SymbolOccurrenceShadow"],
                "type": "BTREE",
            }
        ]
        driver = self._make_driver(index_records=conflicting_indexes)
        with pytest.raises(SchemaDriftError, match="shadow_evict_r1"):
            await ensure_custom_schema(driver)

    @pytest.mark.asyncio
    async def test_matching_constraint_no_drift(self) -> None:
        """Existing constraint with correct properties → no error."""
        matching = [
            {
                "name": "ext_dep_purl_unique",
                "properties": ["purl"],
                "labelsOrTypes": ["ExternalDependency"],
            }
        ]
        driver = self._make_driver(constraint_records=matching)
        await ensure_custom_schema(driver)  # must not raise

    @pytest.mark.asyncio
    async def test_legacy_git_commit_constraint_is_migrated(self) -> None:
        legacy = [
            {
                "name": "git_commit_sha",
                "properties": ["sha"],
                "labelsOrTypes": ["Commit"],
            }
        ]
        driver = self._make_driver(constraint_records=legacy)

        await ensure_custom_schema(driver)

        queries = [
            call.args[0] for call in driver.session.return_value.run.await_args_list
        ]
        assert "DROP CONSTRAINT git_commit_sha IF EXISTS" in queries
        assert any("DETACH DELETE n" in query for query in queries)

    @pytest.mark.asyncio
    async def test_unknown_constraint_name_ignored(self) -> None:
        """Constraint not in expected schema → no drift raised (not our schema object)."""
        unrelated = [
            {
                "name": "some_other_constraint",
                "properties": ["anything"],
                "labelsOrTypes": ["AnyLabel"],
            }
        ]
        driver = self._make_driver(constraint_records=unrelated)
        await ensure_custom_schema(driver)  # must not raise
