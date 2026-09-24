{% if section == 'guides' %}# Guías
{% elif section == 'tools' %}# Herramientas
{% else %}# Actualizaciones
{% endif %}

{% if section == 'guides' %}<div class="library-controls"><label>Buscar guías<input id="guide-filter" type="search" placeholder="Título, autor o tema" autocomplete="off"></label><label>Etiqueta<select id="guide-tag"><option value="">Todas</option>{% for tag in tags %}<option value="{{ tag }}">{{ tag }}</option>{% endfor %}</select></label><p id="guide-count" class="result-count" aria-live="polite"></p></div>{% endif %}
{% if section == 'updates' %}<p class="timeline-intro">Novedades en orden cronológico, de la más reciente a la más antigua.</p>
<ol class="timeline">
{% regroup articles by date|date:'F Y' as months %}{% for month in months %}<li class="timeline-month"><h2>{{ month.grouper|capfirst }}</h2>
<ol>{% for article in month.list %}<li class="timeline-post">
<time datetime="{{ article.date|date:'Y-m-d' }}"><span class="day">{{ article.date|date:'d' }}</span><span class="mon">{{ article.date|date:'M' }}</span></time>
<article class="library-card timeline-card">
<small class="post-meta">{{ article.get_kind_display }} · {{ article.author }} · {{ article.date|date:'d/m/Y' }}</small>
<h2><a href="#/content/{{ article.slug }}">{{ article.title }}</a></h2><p>{{ article.summary }}</p>
{% if article.status %}<p class="status status-{{ article.status }}">{{ article.get_status_display }}</p>{% endif %}
<p class="tag-list">{% for tag in article.tags %}<span>{{ tag }}</span>{% endfor %}</p>
<p class="post-actions"><a class="post-link" href="#/content/{{ article.slug }}">Leer</a>{% if article.pdf_name %}<a class="pdf-link" href="/pdf/{{ article.slug }}.pdf" target="_blank" rel="noreferrer">Abrir PDF original</a>{% endif %}{% if article.url %}<a class="post-link" href="{{ article.url }}" target="_blank" rel="noreferrer">Sitio oficial</a>{% endif %}{% if article.download_file %}<a class="post-link" href="#/downloads">Descarga aprobada</a>{% endif %}</p>
</article></li>{% endfor %}</ol></li>{% empty %}<li><p>Todavía no hay actualizaciones publicadas.</p></li>{% endfor %}
</ol>
{% else %}<div class="library-grid{% if section == 'guides' %} guide-library{% endif %}">
{% for article in articles %}<article class="library-card" data-search="{{ article.title }} {{ article.author }} {{ article.summary }} {{ article.tags|join:' ' }}" data-tags="{{ article.tags|join:'|' }}">
<h2><a href="#/content/{{ article.slug }}">{{ article.title }}</a></h2><p>{{ article.summary }}</p><small>{{ article.date|date:'Y-m-d' }} · {{ article.author }}</small>
{% if article.status %}<p class="status status-{{ article.status }}">{{ article.get_status_display }}</p>{% endif %}
<p class="tag-list">{% for tag in article.tags %}<span>{{ tag }}</span>{% endfor %}</p>
{% if article.pdf_name %}<p><a class="pdf-link" href="/pdf/{{ article.slug }}.pdf" target="_blank" rel="noreferrer">Abrir PDF original</a></p>{% endif %}
{% if article.url %}<p><a href="{{ article.url }}" target="_blank" rel="noreferrer">Sitio oficial</a></p>{% endif %}
{% if article.download_file %}<p><a href="#/downloads">Descarga aprobada</a></p>{% endif %}
</article>{% empty %}<p>Todavía no hay artículos publicados en esta sección.</p>{% endfor %}
</div>{% endif %}
{% if section == 'guides' %}<p class="library-empty" hidden>No hay guías que coincidan con estos filtros.</p>{% endif %}
