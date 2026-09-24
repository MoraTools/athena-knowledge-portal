# {{ user.get_username }}

<p class="account-meta">{% if is_admin %}Administrador{% else %}Lector{% endif %} · Última sesión {% if user.last_login %}{{ user.last_login|date:'d/m/Y H:i' }}{% else %}nunca{% endif %}</p>

<div class="account-grid">
<section class="account-panel">
<h2>Sesión</h2>
<p>Cambie su contraseña o cierre la sesión en este navegador. Cambiar la contraseña cierra sus otras sesiones y revoca sus claves de API.</p>
<div class="account-actions"><a class="account-button" href="/accounts/password_change/">Cambiar contraseña</a><form method="post" action="/accounts/logout/">{% csrf_token %}<button class="account-button danger" type="submit">Cerrar sesión</button></form></div>
</section>
<section class="account-panel">
<h2>Mis claves de API</h2>
{% if keys %}<table><thead><tr><th>Nombre</th><th>Permiso</th><th>Vence</th></tr></thead><tbody>{% for key in keys %}<tr><td>{{ key.name }}</td><td>{{ key.get_scope_display }}</td><td>{{ key.expires_at|date:'d/m/Y' }}</td></tr>{% endfor %}</tbody></table>{% else %}<p>Todavía no tiene claves de API.</p>{% endif %}
{% if is_admin %}<div class="account-actions"><a class="account-button" href="/admin/athena/apikey/add/">Crear clave</a><a class="account-button" href="/#/api">Guía de la API</a></div>{% else %}<p>Pida una clave a un administrador.</p>{% endif %}
</section>
</div>
{% if is_admin %}
<section class="account-admin">
<h2>Administración</h2>
<div class="account-actions"><a class="account-button" href="/admin/athena/article/">Artículos</a><a class="account-button" href="/admin/athena/apikey/">Claves de API</a><a class="account-button" href="/admin/athena/download/">Descargas</a><a class="account-button" href="/admin/auth/user/">Usuarios</a></div>
</section>
{% endif %}
