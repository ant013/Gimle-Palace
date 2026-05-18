## Code Ownership

{% if findings %}
*{{ findings | length }} file{{ 's' if findings | length != 1 else '' }} with diffuse ownership (capped at {{ max_findings }}).*

| Severity | Path | Top Owner | Weight | Total Authors | Source |
|----------|------|-----------|--------|--------------|--------|
{% for f in findings %}
| {{ f._severity | upper }} | `{{ f.path }}` | {{ f.top_owner_email or '—' }} | {{ "%.2f" | format(f.top_owner_weight | float) if f.top_owner_weight is not none else '—' }} | {{ f.total_authors }} | {{ f.source_context | default('other') }} |
{% endfor %}

**Summary:** {{ summary_stats.files_analysed }} file{{ 's' if summary_stats.files_analysed != 1 else '' }} analysed,
{{ summary_stats.diffuse_ownership_count }} with diffuse ownership (top owner weight < 0.2).
{% else %}
No findings — extractor `code_ownership` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found no files with diffuse ownership.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
