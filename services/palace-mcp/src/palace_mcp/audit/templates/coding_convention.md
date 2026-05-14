## Coding Conventions

{% if findings %}
*{{ findings | length }} convention{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Severity | Module | Rule | Dominant Choice | Confidence | Samples | Outliers | Source |
|----------|--------|------|-----------------|------------|---------|----------|--------|
{% for f in findings %}
| {{ f._severity | upper }} | {{ f.module }} | `{{ f.kind }}` | `{{ f.dominant_choice }}` | {{ f.confidence }} | {{ f.sample_count }} | {{ f.outliers }} | {{ f.source_context | default('other') }} |
{% endfor %}

{% for f in findings if f.violations %}
### {{ f.module }} · `{{ f.kind }}` violations

| Severity | File | Line | Message |
|----------|------|------|---------|
{% for violation in f.violations %}
| {{ violation.severity | upper }} | `{{ violation.file }}` | {{ violation.start_line }} | {{ violation.message }} |
{% endfor %}

{% endfor %}
**Summary:** {{ summary_stats.total }} convention{{ 's' if summary_stats.total != 1 else '' }} surfaced by the audit query.
{% else %}
No findings — extractor `coding_convention` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found 0 coding convention summaries.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
