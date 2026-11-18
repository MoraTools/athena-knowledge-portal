# {{ user.get_username }}

<p class="item-meta"><span>{{ role }}</span><span>Última sesión {% if user.last_login %}<time datetime="{{ user.last_login|date:'c' }}">{{ user.last_login|date:'d/m/Y H:i' }}</time>{% else %}nunca{% endif %}</span></p>

<div class="account-grid{% if not keys and not perms.athena.add_apikey %} no-keys{% endif %}">
<section class="account-panel">
<h2>Sesión</h2>
<p>Cambie su contraseña o cierre la sesión en este navegador. Cambiar la contraseña cierra sus otras sesiones y revoca sus claves de API.</p>
<div class="account-actions"><a class="account-button" href="/accounts/password_change/">Cambiar contraseña</a><form method="post" action="/accounts/logout/">{% csrf_token %}<button class="account-button" type="submit">Cerrar sesión</button></form></div>
</section>
<section class="account-panel">
<h2>Mis claves de API</h2>
{% if not keys and not perms.athena.add_apikey %}<p>Una clave de API permite que un script o un agente use Athena con su cuenta; la entrega un administrador.</p>
{% else %}<p>Una clave de API permite que un script o un agente use Athena con su cuenta. No la necesita para leer guías ni descargar archivos.</p>
{% if keys %}<table><thead><tr><th>Nombre</th><th>Permiso</th><th>Vence</th></tr></thead><tbody>{% for key in keys %}<tr><td>{{ key.name }}</td><td>{{ key.get_scope_display }}</td><td data-sort-value="{{ key.expires_at|date:'c' }}">{{ key.expires_at|date:'d/m/Y' }}</td></tr>{% endfor %}</tbody></table>{% else %}<p>Todavía no tiene claves de API.</p>{% endif %}
{% if perms.athena.add_apikey %}<div class="account-actions"><a class="account-button" href="/admin/athena/apikey/add/">Nueva clave de API</a><a href="/#/api">API para agentes</a></div>{% else %}<p>Pida una clave a un administrador.</p>{% endif %}{% endif %}
</section>
</div>
