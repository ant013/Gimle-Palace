## Dead Symbols & Binary Surface

{% if findings %}
*{{ findings | length }} candidate{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Severity | Display Name | Kind | Module | Language | State |
|----------|-------------|------|--------|----------|-------|
{% for f in findings %}
| {{ f._severity | upper }} | `{{ f.display_name }}` | {{ f.kind }} | {{ f.module_name }} | {{ f.language }} | {{ f.candidate_state }} |
{% endfor %}

**Summary:** {{ summary_stats.total }} candidate{{ 's' if summary_stats.total != 1 else '' }}
({{ summary_stats.confirmed_dead }} confirmed dead,
{{ summary_stats.unused_candidate }} unused candidates,
{{ summary_stats.skipped }} skipped).
{% else %}
No findings — extractor `dead_symbol_binary_surface` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found 0 dead symbol candidates.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
