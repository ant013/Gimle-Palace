## Crypto domain findings{% if summary_stats.get('kit_name') %} ({{ summary_stats.kit_name }}){% endif %}

{% set critical_high = (findings | selectattr('_severity', 'equalto', 'critical') | list) + (findings | selectattr('_severity', 'equalto', 'high') | list) %}
{% set medium_low = (findings | selectattr('_severity', 'equalto', 'medium') | list) + (findings | selectattr('_severity', 'equalto', 'low') | list) %}
{% if findings %}
### Critical / high
{% if critical_high %}
{% for f in critical_high %}
- **{{ f.severity | upper }}** [{{ f.kind }}] `{{ f.file }}:{{ f.start_line }}` — {{ f.message }}
{% endfor %}
{% else %}
*No critical or high severity findings.*
{% endif %}

### Medium / low
{% if medium_low %}
{% for f in medium_low %}
- {{ f.severity }} [{{ f.kind }}] `{{ f.file }}:{{ f.start_line }}` — {{ f.message }}
{% endfor %}
{% else %}
*No medium or low severity findings.*
{% endif %}

**Provenance**: run_id `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.

{% else %}
No findings — extractor `crypto_domain_model` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
scanned `{{ files_scanned | default(0) }}` files against `{{ rules_active | default(0) }}` rules, found 0 issues.
{% endif %}
