## Error handling policy

{% set summary = findings[0] if findings else {} %}
{% set issue_rows = findings | selectattr("kind") | list %}

{% if issue_rows %}
### Surface summary

- Catch sites indexed: {{ summary.catch_site_count | default(0) }}
- Files scanned with catch/try? inventory: {{ summary.files_scanned | default(0) }}
- Swallowed sites: {{ summary.swallowed_count | default(0) }}
- Rethrowing sites: {{ summary.rethrows_count | default(0) }}
- Findings: {{ issue_rows | length }}

### Critical / high

{% set critical_high = issue_rows | selectattr("severity", "in", ["critical", "high"]) | list %}
{% if critical_high %}
{% for f in critical_high %}
- **{{ f.severity | upper }}** [{{ f.kind }}] `{{ f.file }}:{{ f.start_line }}` — {{ f.message }}
{% endfor %}
{% else %}
*No critical or high severity findings.*
{% endif %}

### Medium / low / informational

{% set medium_low = issue_rows | rejectattr("severity", "in", ["critical", "high"]) | list %}
{% if medium_low %}
{% for f in medium_low %}
- {{ f.severity }} [{{ f.kind }}] `{{ f.file }}:{{ f.start_line }}` — {{ f.message }}
{% endfor %}
{% else %}
*No medium / low / informational findings.*
{% endif %}

**Provenance**: run_id `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.

{% else %}
No error handling issues found.

Catch sites indexed: {{ summary.catch_site_count | default(0) }}
Files scanned with catch/try? inventory: {{ summary.files_scanned | default(0) }}
Swallowed sites: {{ summary.swallowed_count | default(0) }}
Rethrowing sites: {{ summary.rethrows_count | default(0) }}

**Provenance**: run_id `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.
{% endif %}
