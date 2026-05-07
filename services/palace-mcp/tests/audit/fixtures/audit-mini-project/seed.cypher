// audit-mini-project/seed.cypher
// Seeds 7 successful :IngestRun rows + minimal sample data per extractor.
// Used by the S1.10 smoke harness.
//
// Run via:
//   cypher-shell -u neo4j -p changeme < seed.cypher
// or:
//   cat seed.cypher | docker exec -i <container> cypher-shell -u neo4j -p changeme

// ---------------------------------------------------------------------------
// Project node
// ---------------------------------------------------------------------------
MERGE (proj:Project {slug: "audit-mini"})
SET proj.group_id = "project/audit-mini";

// ---------------------------------------------------------------------------
// IngestRun rows (7 extractors — unified S0.1 schema)
// ---------------------------------------------------------------------------
CREATE (:IngestRun {
    run_id: "run-hotspot-001",
    extractor_name: "hotspot",
    project: "audit-mini",
    group_id: "project/audit-mini",
    success: true,
    started_at: datetime("2026-05-01T10:00:00Z"),
    completed_at: datetime("2026-05-01T10:00:05Z")
});

CREATE (:IngestRun {
    run_id: "run-dead-symbol-001",
    extractor_name: "dead_symbol_binary_surface",
    project: "audit-mini",
    group_id: "project/audit-mini",
    success: true,
    started_at: datetime("2026-05-01T10:01:00Z"),
    completed_at: datetime("2026-05-01T10:01:10Z")
});

CREATE (:IngestRun {
    run_id: "run-dep-surface-001",
    extractor_name: "dependency_surface",
    project: "audit-mini",
    group_id: "project/audit-mini",
    success: true,
    started_at: datetime("2026-05-01T10:02:00Z"),
    completed_at: datetime("2026-05-01T10:02:30Z")
});

CREATE (:IngestRun {
    run_id: "run-code-ownership-001",
    extractor_name: "code_ownership",
    project: "audit-mini",
    group_id: "project/audit-mini",
    success: true,
    started_at: datetime("2026-05-01T10:03:00Z"),
    completed_at: datetime("2026-05-01T10:03:15Z")
});

CREATE (:IngestRun {
    run_id: "run-version-skew-001",
    extractor_name: "cross_repo_version_skew",
    project: "audit-mini",
    group_id: "project/audit-mini",
    success: true,
    started_at: datetime("2026-05-01T10:04:00Z"),
    completed_at: datetime("2026-05-01T10:04:02Z")
});

CREATE (:IngestRun {
    run_id: "run-public-api-001",
    extractor_name: "public_api_surface",
    project: "audit-mini",
    group_id: "project/audit-mini",
    success: true,
    started_at: datetime("2026-05-01T10:05:00Z"),
    completed_at: datetime("2026-05-01T10:05:08Z")
});

CREATE (:IngestRun {
    run_id: "run-cross-module-001",
    extractor_name: "cross_module_contract",
    project: "audit-mini",
    group_id: "project/audit-mini",
    success: true,
    started_at: datetime("2026-05-01T10:06:00Z"),
    completed_at: datetime("2026-05-01T10:06:12Z")
});

// ---------------------------------------------------------------------------
// Sample finding nodes — one per extractor type
// ---------------------------------------------------------------------------

// hotspot
CREATE (:File {
    path: "src/AppDelegate.swift",
    project_id: "project/audit-mini",
    hotspot_score: 4.2,
    ccn_total: 28,
    churn_count: 42,
    complexity_status: "fresh"
});

// dead_symbol_binary_surface
CREATE (:DeadSymbolCandidate {
    id: "ds-mini-001",
    project: "audit-mini",
    group_id: "project/audit-mini",
    module_name: "AppModule",
    language: "swift",
    display_name: "OldHelper",
    kind: "class",
    candidate_state: "unused_candidate",
    confidence: "high",
    evidence_source: "periphery",
    evidence_mode: "static",
    commit_sha: "abc123",
    symbol_key: "AppModule.OldHelper",
    schema_version: 1
});

// dependency_surface — Project node already created above
MATCH (p:Project {slug: "audit-mini"})
CREATE (d:ExternalDependency {
    purl: "pkg:swift/github.com/Alamofire/Alamofire@5.6.0",
    name: "Alamofire",
    resolved_version: "5.6.0",
    ecosystem: "swift"
})
CREATE (p)-[:DEPENDS_ON {
    scope: "spm",
    declared_in: "Package.resolved",
    resolved_version: "5.6.0"
}]->(d);

// code_ownership
MATCH (f:File {path: "src/AppDelegate.swift", project_id: "project/audit-mini"})
MERGE (a:Author {email: "dev@example.com", name: "Dev Example"})
MERGE (f)-[:OWNED_BY {weight: 0.85, blame_share: 0.9, recency_churn_share: 0.7}]->(a);
