<section class="unavailable-page">

# Artículo no disponible

No se puede mostrar esta página.

Puede que la dirección sea incorrecta o que el artículo tenga acceso limitado.
{% if user.is_authenticated %}
Si necesita acceso, pídalo a un administrador de Athena.
{% else %}
Si tiene una cuenta, ingrese: puede que con ella tenga acceso.
{% endif %}
<p class="post-actions">{% if not user.is_authenticated %}<a class="download-link" href="/accounts/login/">Ingresar</a>{% endif %}<a class="post-link" href="#/search">Buscar en Athena</a><a class="post-link" href="#/">Ir al inicio</a></p>
</section>
