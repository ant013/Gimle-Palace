# Audit Report — {{ project }}

**Generated at:** {{ generated_at }}
**Depth:** {{ depth }}

---

## Executive Summary

{{ executive_summary }}

---

{% for section in sections %}
{{ section }}

---

{% endfor %}
## Blind Spots

{% if blind_spots %}
The following extractors have not run for project `{{ project }}` and are excluded from this report:

{% for name in blind_spots %}
- ⚠ `{{ name }}` — run `palace.ingest.run_extractor(name="{{ name }}", project="{{ project }}")` to populate
{% endfor %}
{% else %}
All registered audit extractors produced data. No blind spots.
{% endif %}

---

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
