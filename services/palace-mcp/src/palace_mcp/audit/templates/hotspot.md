## Code Hotspots

{% if findings %}
*{{ findings | length }} file{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Severity | Path | Hotspot Score | CCN | Churn |
|----------|------|--------------|-----|-------|
{% for f in findings %}
| {{ f._severity | upper }} | `{{ f.path }}` | {{ "%.2f" | format(f.hotspot_score | float) }} | {{ f.ccn_total }} | {{ f.churn_count }} |
{% endfor %}

**Summary:** {{ summary_stats.file_count }} file{{ 's' if summary_stats.file_count != 1 else '' }} analysed,
max hotspot score {{ "%.2f" | format(summary_stats.max_score | float) }},
window {{ summary_stats.window_days }} days.
{% else %}
No findings — extractor `hotspot` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
scanned {{ summary_stats.get('file_count', 0) }} files, found 0 issues.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
