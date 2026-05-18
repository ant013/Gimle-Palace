## Blind Spots

The following extractors have not run for project `{{ project }}` and are excluded from this report:

{% if blind_spots %}
{% for name in blind_spots %}
- ⚠ `{{ name }}` — run `palace.ingest.run_extractor(name="{{ name }}", project="{{ project }}")` to populate
{% endfor %}
{% else %}
All registered audit extractors produced data. No blind spots.
{% endif %}
