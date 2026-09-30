# Buscar en Athena

{% if not user.is_authenticated %}<p>Busque en los artículos públicos. <a href="/accounts/login/">Ingrese</a> para consultar el contenido de su equipo.</p>{% endif %}
<div class="search-page">
  <div id="search-page-slot" aria-label="Buscar en Athena"></div>
  <div class="search-toolbar">
    <label for="athena-search-type">Tipo de contenido</label>
    <select id="athena-search-type">
      <option value="">Todo</option>
      <option value="guide">Guías</option>
      <option value="tool">Herramientas</option>
      <option value="update">Actualizaciones</option>
      {% if user.is_authenticated %}<option value="download">Descargas</option>{% endif %}
      <option value="pdf">PDF</option>
    </select>
  </div>
  <p id="search-result-count" class="search-result-count" aria-live="polite"></p>
  <div id="search-results" class="search-results" aria-live="polite"></div>
</div>
