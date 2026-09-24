# Descargas

Archivos aprobados. Solo para usuarios de Athena.
{% if sections %}
<div class="library-controls download-controls"><label>Buscar descargas<input id="download-filter" type="search" placeholder="Buscar archivo, sección o nota" autocomplete="off"></label><label>Sección<select id="download-section"><option value="">Todas</option>{% for key, label, items in sections %}<option value="{{ key }}">{{ label }}</option>{% endfor %}</select></label><p id="download-count" class="result-count" aria-live="polite"></p></div>
{% endif %}{% for key, label, items in sections %}
<section class="download-section" data-section="{{ key }}">

## {{ label }}

{% if key == 'previous' %}<details class="download-archive"><summary>Mostrar {{ items|length }} archivo{{ items|length|pluralize }}</summary>
{% endif %}<div class="catalog-list">
{% for item in items %}<article class="catalog-item" data-search="{{ item.title }} {{ item.filename }} {{ label }} {{ item.note }}">
<div><strong>{{ item.title }}</strong><small>{{ item.size|filesizeformat }}</small><code>{{ item.filename }}</code>{% if item.note %}<p>{{ item.note }}</p>{% endif %}</div>
<a class="download-link" href="/downloads/{{ item.slug }}" download>Descargar</a>
</article>
{% endfor %}</div>{% if key == 'previous' %}
</details>{% endif %}

</section>
{% empty %}
Todavía no hay archivos publicados.
{% endfor %}{% if sections %}
<p class="library-empty download-empty" hidden>No hay archivos que coincidan.</p>{% endif %}
