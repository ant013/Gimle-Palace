"""Neo4j schema bootstrap with drift detection (GIM-101a, T6).

Python-pro Finding F-G: ensure_custom_schema called from extract() top before
any Cypher reads/writes.

Architect Finding F4: pre-flight SHOW CONSTRAINTS / SHOW INDEXES diff;
raises schema_drift_detected on conflicting prior schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from neo4j import AsyncDriver, AsyncSession


@dataclass(frozen=True)
class ConstraintSpec:
    name: str
    label: str
    properties: tuple[str, ...]
    type: str = "UNIQUE"


@dataclass(frozen=True)
class IndexSpec:
    name: str
    label: str
    properties: tuple[str, ...]


@dataclass(frozen=True)
class FulltextSpec:
    name: str
    label: str
    properties: tuple[str, ...]


@dataclass(frozen=True)
class SchemaDefinition:
    constraints: list[ConstraintSpec] = field(default_factory=list)
    indexes: list[IndexSpec] = field(default_factory=list)
    fulltext_indexes: list[FulltextSpec] = field(default_factory=list)

    def all_names(self) -> frozenset[str]:
        return frozenset(
            [c.name for c in self.constraints]
            + [i.name for i in self.indexes]
            + [f.name for f in self.fulltext_indexes]
        )


class SchemaDriftError(Exception):
    """Raised when existing Neo4j schema conflicts with expected definition."""


EXPECTED_SCHEMA = SchemaDefinition(
    constraints=[
        ConstraintSpec(
            name="ext_dep_purl_unique",
            label="ExternalDependency",
            properties=("purl",),
            type="UNIQUE",
        ),
        ConstraintSpec(
            name="eviction_record_unique",
            label="EvictionRecord",
            properties=("symbol_qualified_name", "project"),
            type="UNIQUE",
        ),
        ConstraintSpec(
            name="ingest_checkpoint_unique",
            label="IngestCheckpoint",
            properties=("run_id", "phase", "project"),
            type="UNIQUE",
        ),
    ],
    indexes=[
        IndexSpec(
            name="shadow_evict_r1",
            label="SymbolOccurrenceShadow",
            properties=("group_id", "kind", "importance", "tier_weight"),
        ),
        IndexSpec(
            name="shadow_evict_r2",
            label="SymbolOccurrenceShadow",
            properties=("group_id", "kind", "importance", "last_seen_at"),
        ),
        IndexSpec(
            name="shadow_count_by_group",
            label="SymbolOccurrenceShadow",
            properties=("group_id",),
        ),
        IndexSpec(
            name="symbol_qn_suffix",
            label="Symbol",
            properties=("qn_suffix",),
        ),
        IndexSpec(
            name="ingest_run_lookup",
            label="IngestRun",
            properties=("project", "extractor_name", "success"),
        ),
    ],
    fulltext_indexes=[
        FulltextSpec(
            name="symbol_qn_fulltext",
            label="Symbol",
            properties=("qualified_name",),
        ),
    ],
)

# ---------------------------------------------------------------------------
# Cypher templates
# ---------------------------------------------------------------------------

_CONSTRAINT_TEMPLATES: dict[str, str] = {
    "UNIQUE": (
        "CREATE CONSTRAINT {name} IF NOT EXISTS "
        "FOR (n:{label}) REQUIRE ({props}) IS UNIQUE"
    ),
}

_INDEX_TEMPLATE = (
    "CREATE INDEX {name} IF NOT EXISTS "
    "FOR (n:{label}) ON ({props})"
)

_FULLTEXT_TEMPLATE = (
    "CREATE FULLTEXT INDEX {name} IF NOT EXISTS "
    "FOR (n:{label}) ON EACH [{props}]"
)


def _constraint_cypher(c: ConstraintSpec) -> str:
    props = ", ".join(f"n.{p}" for p in c.properties)
    return _CONSTRAINT_TEMPLATES[c.type].format(
        name=c.name, label=c.label, props=props
    )


def _index_cypher(i: IndexSpec) -> str:
    props = ", ".join(f"n.{p}" for p in i.properties)
    return _INDEX_TEMPLATE.format(name=i.name, label=i.label, props=props)


def _fulltext_cypher(f: FulltextSpec) -> str:
    props = ", ".join(f"n.{p}" for p in f.properties)
    return _FULLTEXT_TEMPLATE.format(name=f.name, label=f.label, props=props)


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

async def ensure_custom_schema(driver: AsyncDriver) -> None:
    """Idempotent schema bootstrap with drift detection (F-G + Architect F4).

    Raises:
        SchemaDriftError: if an existing constraint/index conflicts with
            expected schema by name but different properties (drift).
    """
    async with driver.session() as session:
        await _detect_drift(session)
        await _create_schema(session)


async def _detect_drift(session: AsyncSession) -> None:
    """Pre-flight: raise SchemaDriftError when name matches but properties differ."""
    # Build lookup maps: name -> frozenset of expected properties
    expected_constraint_props: dict[str, frozenset[str]] = {
        c.name: frozenset(c.properties) for c in EXPECTED_SCHEMA.constraints
    }
    all_index_specs: list[IndexSpec | FulltextSpec] = [
        *EXPECTED_SCHEMA.indexes,
        *EXPECTED_SCHEMA.fulltext_indexes,
    ]
    expected_index_props: dict[str, frozenset[str]] = {
        i.name: frozenset(i.properties) for i in all_index_specs
    }

    try:
        result = await session.run(
            "SHOW CONSTRAINTS YIELD name, properties, labelsOrTypes"
        )
        async for record in result:
            name = record["name"]
            if name not in expected_constraint_props:
                continue
            existing_props = frozenset(record["properties"] or [])
            if existing_props != expected_constraint_props[name]:
                raise SchemaDriftError(
                    f"Constraint '{name}' exists with properties {set(existing_props)} "
                    f"but expected {set(expected_constraint_props[name])}"
                )

        result = await session.run(
            "SHOW INDEXES YIELD name, properties, labelsOrTypes, type"
        )
        async for record in result:
            name = record["name"]
            if name not in expected_index_props:
                continue
            existing_props = frozenset(record["properties"] or [])
            if existing_props != expected_index_props[name]:
                raise SchemaDriftError(
                    f"Index '{name}' exists with properties {set(existing_props)} "
                    f"but expected {set(expected_index_props[name])}"
                )
    except SchemaDriftError:
        raise
    except Exception:
        # Older Neo4j versions may not support SHOW CONSTRAINTS YIELD ...
        # Skip drift detection — CREATE ... IF NOT EXISTS is still idempotent.
        return


async def _create_schema(session: AsyncSession) -> None:
    for c in EXPECTED_SCHEMA.constraints:
        await session.run(_constraint_cypher(c))
    for i in EXPECTED_SCHEMA.indexes:
        await session.run(_index_cypher(i))
    for f in EXPECTED_SCHEMA.fulltext_indexes:
        await session.run(_fulltext_cypher(f))
