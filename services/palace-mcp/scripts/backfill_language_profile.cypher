// Backfill language_profile on existing :Project nodes (GIM-283-1 Task 2.0).
//
// Run once after deploying the Slice 2 branch. Idempotent: CASE preserves
// any existing value via coalesce, so re-running does not overwrite manual
// overrides set after this migration.
//
// Excluded: uw-android-mini — test fixture only, not mounted in docker-compose.yml.
//
// Usage (from cypher-shell or neo4j browser):
//   :source backfill_language_profile.cypher
//
// Or via bolt driver:
//   cat scripts/backfill_language_profile.cypher | cypher-shell -u neo4j -p <pass>

MATCH (p:Project)
WHERE p.slug IN [
    'gimle',
    'tron-kit',
    'uw-android',
    'uw-ios',
    'uw-ios-mini',
    'oz-v5-mini'
]
  AND p.language_profile IS NULL
SET p.language_profile = CASE p.slug
    WHEN 'gimle'       THEN 'python_service'
    WHEN 'tron-kit'    THEN 'swift_kit'
    WHEN 'uw-ios'      THEN 'swift_kit'
    WHEN 'uw-ios-mini' THEN 'swift_kit'
    WHEN 'uw-android'  THEN 'android_kit'
    WHEN 'oz-v5-mini'  THEN 'python_service'
    ELSE p.language_profile
END
RETURN p.slug AS slug, p.language_profile AS language_profile
ORDER BY slug;
