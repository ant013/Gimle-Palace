## Dependency Surface

{% if summary_stats.get("missing_lockfile") %}
### ⚠ Data Quality

No `Package.resolved` (or `uv.lock` / `gradle.lockfile`) found; declared constraints only.
CVE / version-freshness checks unavailable.

{% endif %}
{% if findings %}
*{{ findings | length }} dependenc{{ 'ies' if findings | length != 1 else 'y' }} found (capped at {{ max_findings }}).*

{% if summary_stats.get("missing_lockfile") %}
| PURL | Scope | Declared In | Declared Constraint |
|------|-------|-------------|---------------------|
{% for f in findings %}
| `{{ f.purl }}` | {{ f.scope }} | `{{ f.declared_in }}` | {{ f.declared_version_constraint or '—' }} |
{% endfor %}
{% else %}
| PURL | Scope | Declared In | Resolved Version |
|------|-------|-------------|-----------------|
{% for f in findings %}
| `{{ f.purl }}` | {{ f.scope }} | `{{ f.declared_in }}` | {{ f.get('resolved_version') or f.get('declared_version_constraint') or '—' }} |
{% endfor %}
{% endif %}

**Summary:** {{ summary_stats.total }} total dependencies across {{ summary_stats.scopes | join(', ') }} scopes.
{% else %}
No findings — extractor `dependency_surface` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found 0 declared dependencies.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
