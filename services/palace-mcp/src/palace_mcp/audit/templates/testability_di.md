## Testability / DI patterns

{% if findings %}
*{{ findings | length }} finding{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Severity | Module | Language | Style | Framework | Samples | Outliers | Confidence |
|----------|--------|----------|-------|-----------|---------|----------|------------|
{% for finding in findings %}
| {{ finding._severity | upper }} | {{ finding.module }} | {{ finding.language }} | `{{ finding.style | upper }}` | {{ finding.framework or "-" }} | {{ finding.sample_count }} | {{ finding.outliers }} | {{ finding.confidence }} |
{% endfor %}

{% for finding in findings %}
### {{ finding.module }} · `{{ finding.style | upper }}` · {{ finding._severity | upper }}

{% if finding.test_doubles %}
Test doubles:
{% for double in finding.test_doubles %}
- `{{ double.kind }}` in `{{ double.test_file }}`{% if double.target_symbol %} targeting `{{ double.target_symbol }}`{% endif %}
{% endfor %}
{% else %}
Test doubles: none linked for this module/style.
{% endif %}

{% if finding.untestable_sites %}
Untestable sites:
{% for site in finding.untestable_sites %}
- **{{ site.severity | upper }}** `{{ site.file }}:{{ site.start_line }}` `{{ site.category }}` via `{{ site.symbol_referenced }}` — {{ site.message }}
{% endfor %}
{% else %}
Untestable sites: none linked for this module/style.
{% endif %}

{% endfor %}
**Summary:** {{ summary_stats.patterns | default(findings | length) }} pattern{{ 's' if (summary_stats.patterns | default(findings | length)) != 1 else '' }},
{{ summary_stats.test_doubles | default(0) }} test double{{ 's' if (summary_stats.test_doubles | default(0)) != 1 else '' }},
{{ summary_stats.untestable_sites | default(0) }} untestable site{{ 's' if (summary_stats.untestable_sites | default(0)) != 1 else '' }}.
{% else %}
No findings — extractor `testability_di` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
found 0 DI/testability summaries.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
