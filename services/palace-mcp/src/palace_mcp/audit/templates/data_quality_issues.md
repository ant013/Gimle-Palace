## Data-Quality Issues

The following extractors ran successfully but their audit data could not be fetched (Cypher query error). Re-running the extractor or checking Neo4j connectivity may resolve this.

| Extractor | Last Run ID | Suggestion |
|-----------|-------------|------------|
{% for name, status in fetch_failed.items() %}
| `{{ name }}` | `{{ status.last_run_id or "—" }}` | Check Neo4j logs; re-run `palace.ingest.run_extractor(name="{{ name }}", project="{{ project }}")` |
{% endfor %}
