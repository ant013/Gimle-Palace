## Public API Surface

{% if findings %}
*{{ findings | length }} public symbol{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Module | FQN | Kind | Language | Visibility |
|--------|-----|------|----------|-----------|
{% for f in findings %}
| {{ f.module_name }} | `{{ f.fqn }}` | {{ f.kind }} | {{ f.language }} | {{ f.visibility }} |
{% endfor %}

**Summary:** {{ summary_stats.total }} public symbol{{ 's' if summary_stats.total != 1 else '' }}
across {{ summary_stats.module_count }} module{{ 's' if summary_stats.module_count != 1 else '' }}.
{% else %}
No findings — extractor `public_api_surface` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found 0 public API symbols.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
