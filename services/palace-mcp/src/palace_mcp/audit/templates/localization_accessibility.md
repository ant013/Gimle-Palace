## Localization & Accessibility

{% set data = findings[0] if findings else {} %}
{% set locales = data.get("locales", []) if data else [] %}
{% set hardcoded = data.get("hardcoded", []) if data else [] %}
{% set a11y_missing = data.get("a11y_missing", []) if data else [] %}

### Locale Coverage

{% if locales %}
| Surface | Locale | Keys | Coverage |
|---------|--------|------|----------|
{% for lr in locales | sort(attribute="coverage_pct") %}
| {{ lr.surface }} | `{{ lr.locale }}` | {{ lr.key_count }} | {{ "%.1f" | format(lr.coverage_pct | float) }}% |
{% endfor %}

{% set low_coverage = locales | selectattr("coverage_pct", "lt", 80.0) | list %}
{% if low_coverage %}
⚠ Locales below 80 % coverage: {% for lr in low_coverage %}`{{ lr.locale }}` ({{ "%.0f" | format(lr.coverage_pct | float) }}%){% if not loop.last %}, {% endif %}{% endfor %}.
{% endif %}
{% else %}
*No locale resource data found — run `palace.ingest.run_extractor(name="localization_accessibility", project="<slug>")` first.*
{% endif %}

### Hardcoded Strings ({{ hardcoded | length }})

{% set critical_high_h = hardcoded | selectattr("severity", "in", ["critical", "high"]) | list %}
{% set medium_low_h = hardcoded | rejectattr("severity", "in", ["critical", "high"]) | list %}

{% if hardcoded %}
{% if critical_high_h %}
#### Critical / High

| File | Context | Severity |
|------|---------|----------|
{% for h in critical_high_h %}
| `{{ h.file }}:{{ h.start_line }}` | {{ h.context }} | {{ h.severity | upper }} |
{% endfor %}
{% endif %}
{% if medium_low_h %}
#### Medium / Low

{% for h in medium_low_h[:20] %}
- `{{ h.file }}:{{ h.start_line }}` [{{ h.context }}] — {{ h.message }}
{% endfor %}
{% if medium_low_h | length > 20 %}
*… and {{ medium_low_h | length - 20 }} more.*
{% endif %}
{% endif %}
{% else %}
*No hardcoded string findings.*
{% endif %}

### Accessibility Gaps ({{ a11y_missing | length }})

{% if a11y_missing %}
{% set critical_high_a = a11y_missing | selectattr("severity", "in", ["critical", "high"]) | list %}
{% set medium_low_a = a11y_missing | rejectattr("severity", "in", ["critical", "high"]) | list %}
{% if critical_high_a %}
{% for a in critical_high_a %}
- **{{ a.severity | upper }}** [{{ a.surface }}] `{{ a.file }}:{{ a.start_line }}` — {{ a.message }}
{% endfor %}
{% endif %}
{% for a in medium_low_a[:20] %}
- {{ a.severity }} [{{ a.surface }}/{{ a.control_kind }}] `{{ a.file }}:{{ a.start_line }}` — {{ a.message }}
{% endfor %}
{% if medium_low_a | length > 20 %}
*… and {{ medium_low_a | length - 20 }} more.*
{% endif %}
{% else %}
*No accessibility gap findings.*
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
