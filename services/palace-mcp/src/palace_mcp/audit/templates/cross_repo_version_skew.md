## Cross-Repo Version Skew

{% if findings %}
*{{ findings | length }} skew instance{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Severity | Package | Versions Seen | Affected Members |
|----------|---------|--------------|-----------------|
{% for f in findings %}
| {{ f._severity | upper }} | `{{ f.purl }}` | {{ f.versions | join(', ') }} | {{ f.member_count }} |
{% endfor %}

**Summary:** {{ summary_stats.total }} version skew instance{{ 's' if summary_stats.total != 1 else '' }}
({{ summary_stats.major }} major, {{ summary_stats.minor }} minor, {{ summary_stats.patch }} patch).
{% else %}
No findings — extractor `cross_repo_version_skew` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found 0 version skew instances.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
