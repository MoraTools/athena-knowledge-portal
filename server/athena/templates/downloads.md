# Descargas

Archivos aprobados. Solo para usuarios de Athena.
{% for key, label, items in sections %}
<section class="download-section">

## {{ label }}

{% if key == 'previous' %}<details class="download-archive"><summary>Mostrar {{ items|length }} archivo{{ items|length|pluralize }}</summary>
{% endif %}<div class="catalog-list">
{% for item in items %}<article class="catalog-item">
<div><strong>{{ item.title }}</strong><small>{{ item.size|filesizeformat }}</small><code>{{ item.filename }}</code>{% if item.note %}<p>{{ item.note }}</p>{% endif %}</div>
<a class="download-link" href="/downloads/{{ item.slug }}" download>Descargar</a>
</article>
{% endfor %}</div>{% if key == 'previous' %}
</details>{% endif %}

</section>
{% empty %}
Todavía no hay archivos publicados.
{% endfor %}
