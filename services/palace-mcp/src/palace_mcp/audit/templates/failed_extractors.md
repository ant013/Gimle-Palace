## Failed Extractors

The following extractors completed their last run with `success=False`. Their data is excluded from this report.

| Extractor | Run ID | Error Code | Message | Next Action |
|-----------|--------|------------|---------|-------------|
{% for name, status in run_failed.items() %}
| `{{ name }}` | `{{ status.last_run_id or "—" }}` | `{{ status.error_code or "—" }}` | {{ (status.error_message or "")[:80] }} | `palace.ingest.run_extractor(name="{{ name }}", project="{{ project }}")` |
{% endfor %}
