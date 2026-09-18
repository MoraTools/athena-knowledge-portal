{% if section == 'guides' %}# Guías
{% elif section == 'tools' %}# Herramientas
{% else %}# Actualizaciones
{% endif %}

{% if section == 'guides' %}<div class="library-controls"><label>Buscar guías<input id="guide-filter" type="search" placeholder="Título, autor o tema" autocomplete="off"></label><label>Etiqueta<select id="guide-tag"><option value="">Todas</option>{% for tag in tags %}<option value="{{ tag }}">{{ tag }}</option>{% endfor %}</select></label><p id="guide-count" class="result-count" aria-live="polite"></p></div>{% endif %}
<div class="library-grid{% if section == 'guides' %} guide-library{% endif %}">
{% for article in articles %}<article class="library-card" data-search="{{ article.title }} {{ article.author }} {{ article.summary }} {{ article.tags|join:' ' }}" data-tags="{{ article.tags|join:'|' }}">
<h2><a href="#/content/{{ article.slug }}">{{ article.title }}</a></h2><p>{{ article.summary }}</p><small>{{ article.date|date:'Y-m-d' }} · {{ article.author }}</small>
{% if article.status %}<p class="status status-{{ article.status }}">{{ article.get_status_display }}</p>{% endif %}
<p class="tag-list">{% for tag in article.tags %}<span>{{ tag }}</span>{% endfor %}</p>
{% if article.pdf_name %}<p><a class="pdf-link" href="/pdf/{{ article.slug }}.pdf" target="_blank" rel="noreferrer">Abrir PDF original</a></p>{% endif %}
{% if article.url %}<p><a href="{{ article.url }}" target="_blank" rel="noreferrer">Sitio oficial</a></p>{% endif %}
{% if article.download_file %}<p><a href="#/packages">Descarga aprobada</a></p>{% endif %}
</article>{% empty %}<p>Todavía no hay artículos publicados en esta sección.</p>{% endfor %}
</div>
{% if section == 'guides' %}<p class="library-empty" hidden>No hay guías que coincidan con estos filtros.</p>{% endif %}
