<section class="hero">
  <div class="hero-copy">
    <p class="eyebrow">Automation Anywhere</p>
    <h1>Athena</h1>
    <p>{% if user.is_authenticated %}Centro de conocimiento, herramientas y feed de actualizaciones para desarrolladores.{% else %}Guías, herramientas y conocimiento compartido por el equipo.{% endif %}</p>
    <div id="home-search-slot" aria-label="Buscar en Athena"></div>
  </div>
  <img src="/assets/athena-dither-2.webp" alt="" width="900" height="900">
</section>

{% if not user.is_authenticated %}<div class="visitor-note"><p>Está viendo la biblioteca pública. Ingrese para consultar el contenido de su equipo.</p><a class="post-link" href="/accounts/login/">Ingresar</a></div>{% endif %}

## Explorar

<div class="portal-grid">
  <a class="portal-card" href="#/guides"><span>Guías</span><p>Busque por texto o etiqueta en la biblioteca permanente.</p></a>
  <a class="portal-card" href="#/updates"><span>Actualizaciones</span><p>Consulte guías nuevas, versiones y anuncios.</p></a>
  <a class="portal-card" href="#/tools"><span>Herramientas</span><p>Revise estado, límites y documentación.</p></a>
  {% if user.is_authenticated %}<a class="portal-card" href="#/downloads"><span>Descargas</span><p>Descargue los archivos aprobados desde Athena.</p></a>{% endif %}
</div>

{% if not has_articles %}<p class="library-empty">{% if user.is_authenticated %}Todavía no hay artículos publicados.{% else %}Todavía no hay artículos públicos. Puede ingresar si tiene una cuenta.{% endif %}</p>{% endif %}
{% if show_contribute %}<div class="contribute-note"><p>¿Documentó una solución que el equipo puede volver a usar?</p><a href="#/content/contributing">Cómo contribuir</a></div>{% endif %}
