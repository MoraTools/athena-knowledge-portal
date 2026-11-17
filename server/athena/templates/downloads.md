# Descargas

Archivos aprobados. Solo para usuarios de Athena.
{% if sections %}
<div class="download-controls"><p id="download-count" class="result-count" role="status" aria-live="polite" aria-atomic="true"></p><nav class="download-jumps" aria-label="Secciones de Descargas">{% for key, label, items in sections %}<a href="#/downloads?id=download-{{ key }}" data-download-jump="{{ key }}"><span>{{ label }}</span> <span class="topic-count">{{ items|length }}</span></a>{% endfor %}</nav></div>
{% endif %}{% for key, label, items in sections %}
<section class="download-section" id="download-{{ key }}" data-section="{{ key }}">

## {{ label }}

{% if key == 'framework' %}<p class="download-permalink">Enlace permanente a la última versión: <a href="{{ latest_url }}" download>{{ latest_url }}</a></p>

{% endif %}{% if key == 'previous' %}<details class="download-archive"><summary><span class="archive-closed">Mostrar {{ items|length }} archivo{{ items|length|pluralize }}</span><span class="archive-open">Ocultar archivos</span></summary>
{% endif %}<div class="catalog-list">
{% for item in items %}<article class="catalog-item" data-search="{{ item.title }} {{ item.filename }} {{ label }} {{ item.note }}">
<div><strong>{{ item.title }}</strong><small>{{ item.size|filesizeformat }} · <time datetime="{{ item.created_at|date:'Y-m-d' }}">{{ item.created_at|date:'Y-m-d' }}</time></small><code>{{ item.filename }}</code>{% if item.note %}<p>{{ item.note }}</p>{% endif %}</div>
{% if item.pk == current_pk %}<p class="post-actions"><span class="status">Versión actual</span><a class="download-link" href="/downloads/{{ item.slug }}" download>Descargar<span class="visually-hidden" lang="es"> {{ item.title }}</span></a></p>{% else %}<a class="account-button" href="/downloads/{{ item.slug }}" download>Descargar<span class="visually-hidden" lang="es"> {{ item.title }}</span></a>{% endif %}
</article>
{% endfor %}</div>{% if key == 'previous' %}
</details>{% endif %}

</section>
{% empty %}
Todavía no hay archivos publicados.
{% endfor %}{% if sections %}
<p class="library-empty download-empty" hidden>No hay archivos que coincidan.</p>{% endif %}
