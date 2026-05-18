# Audit Report — {{ project }}

**Generated at:** {{ generated_at }}
**Depth:** {{ depth }}

---

{% if library_findings_warning %}
{{ library_findings_warning }}

---

{% endif %}
## Executive Summary

{{ executive_summary }}

---

{% for section in sections %}
{{ section }}

---

{% endfor %}
{% if run_failed %}
{{ failed_extractors_section }}

---

{% endif %}
{% if fetch_failed_statuses %}
{{ data_quality_section }}

---

{% endif %}
{{ blind_spots_section }}

---

{% if profile_coverage_section %}
{{ profile_coverage_section }}

---

{% endif %}
## Provenance

| Field | Value |
|-------|-------|
| Project | `{{ project }}` |
| Generated at | `{{ generated_at }}` |
| Fetched extractors | `{{ fetched_extractors | join(", ") }}` |
| Blind spots | `{{ blind_spots | join(", ") if blind_spots else "none" }}` |
{% for run in run_provenance %}
| `{{ run.extractor_name }}` run ID | `{{ run.run_id }}` |
{% endfor %}
