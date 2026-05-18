## Cross-Module Contract Drift

{% if findings %}
*{{ findings | length }} contract delta{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Severity | Consumer | Producer | Removed | Changed | Added | Affected Uses |
|----------|----------|----------|---------|---------|-------|--------------|
{% for f in findings %}
| {{ f._severity | upper }} | {{ f.consumer_module }} | {{ f.producer_module }} | {{ f.removed_count }} | {{ f.signature_changed_count }} | {{ f.added_count }} | {{ f.affected_use_count }} |
{% endfor %}

**Summary:** {{ summary_stats.total }} delta{{ 's' if summary_stats.total != 1 else '' }}
({{ summary_stats.breaking }} breaking removals,
{{ summary_stats.signature_changes }} signature changes).
{% else %}
No findings — extractor `cross_module_contract` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found 0 cross-module contract deltas.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
