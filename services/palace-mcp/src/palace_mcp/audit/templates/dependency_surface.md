## Dependency Surface

{% if findings %}
*{{ findings | length }} dependenc{{ 'ies' if findings | length != 1 else 'y' }} found (capped at {{ max_findings }}).*

| PURL | Scope | Declared In | Version |
|------|-------|-------------|---------|
{% for f in findings %}
| `{{ f.purl }}` | {{ f.scope }} | `{{ f.declared_in }}` | {{ f.declared_version_constraint or '—' }} |
{% endfor %}

**Summary:** {{ summary_stats.total }} total dependencies across {{ summary_stats.scopes | join(', ') }} scopes.
{% else %}
No findings — extractor `dependency_surface` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found 0 declared dependencies.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
