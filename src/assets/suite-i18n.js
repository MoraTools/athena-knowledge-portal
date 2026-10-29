(() => {
  'use strict';
  // Exact Spanish interface sources. Authored article titles, summaries and prose are not translated.
  const dictionary = {
    'Saltar al contenido': 'Skip to content', 'Navegación del portal': 'Portal navigation', 'Athena, inicio': 'Athena, home',
    'Biblioteca': 'Library', 'Participar': 'Contribute', 'Cuenta': 'Account', 'Administración': 'Administration',
    'Inicio': 'Home', 'Guías': 'Guides', 'Herramientas': 'Tools', 'Descargas': 'Downloads', 'Contribuir': 'Contribute',
    'Mi cuenta': 'My account', 'Ingresar': 'Sign in', 'Ingrese': 'Sign in', 'Administrar Athena': 'Manage Athena',
    'API para agentes': 'API for agents', 'Buscar': 'Search', 'Buscar en Athena': 'Search Athena',
    'Mostrar la navegación': 'Show navigation', 'Contraer': 'Collapse', 'Expandir': 'Expand', 'Cerrar': 'Close',
    'Contraer la navegación': 'Collapse navigation', 'Expandir la navegación': 'Expand navigation', 'Cerrar la navegación': 'Close navigation',
    'Cargando Athena…': 'Loading Athena…', 'Acceso con cuenta': 'Signed in', 'Biblioteca pública': 'Public library',
    'Centro de conocimiento, herramientas y feed de actualizaciones para desarrolladores.': 'Knowledge, tools and an update feed for developers.',
    'Guías, herramientas y conocimiento compartido por el equipo.': 'Guides, tools and knowledge shared by the team.',
    'Está viendo la biblioteca pública. Ingrese para consultar el contenido de su equipo.': 'You are viewing the public library. Sign in to read your team’s content.',
    'Está viendo artículos públicos.': 'You are viewing public articles.',
    'para consultar el contenido de su equipo.': 'to read your team’s content.',
    'Busque en los artículos públicos.': 'Search public articles.',
    'Explorar': 'Explore', 'Actualizaciones': 'Updates', 'Busque por texto o etiqueta en la biblioteca permanente.': 'Search the permanent library by text or tag.',
    'Consulte guías nuevas, versiones y anuncios.': 'See new guides, releases and announcements.', 'Revise estado, límites y documentación.': 'Check status, limits and documentation.',
    'Descargue los archivos aprobados desde Athena.': 'Download the approved files from Athena.',
    'Todavía no hay artículos publicados.': 'No articles have been published yet.',
    'Todavía no hay artículos públicos. Puede ingresar si tiene una cuenta.': 'There are no public articles yet. You can sign in if you have an account.',
    '¿Documentó una solución que el equipo puede volver a usar?': 'Did you document a fix the team can use again?', 'Cómo contribuir': 'How to contribute',
    'Nuevo artículo': 'New article', 'Buscar guías': 'Search guides', 'Título, autor, resumen o etiqueta': 'Title, author, summary or tag',
    'Etiqueta': 'Tag', 'Todas': 'All', 'Todo': 'All', 'Temas de las guías': 'Guide topics', 'Sin etiqueta': 'Untagged',
    'No hay guías que coincidan con estos filtros.': 'No guides match these filters.',
    'Novedades en orden cronológico, de la más reciente a la más antigua.': 'Updates in chronological order, newest first.',
    'Todavía no hay actualizaciones publicadas.': 'No updates have been published yet.',
    'Todavía no hay artículos publicados en esta sección.': 'No articles have been published in this section yet.',
    'Todavía no hay artículos públicos publicados en esta sección.': 'No public articles have been published in this section yet.',
    'Tipo de contenido': 'Content type', '¿Qué necesita encontrar?': 'What do you need to find?',
    'Busque una guía, herramienta, actualización, descarga o PDF.': 'Search for a guide, tool, update, download or PDF.',
    'Buscando…': 'Searching…', 'Sin resultados': 'No results', 'Pruebe menos palabras, cambie el tipo de contenido o revise la escritura.': 'Try fewer words, change the content type or check the spelling.',
    'No se pudo cargar la búsqueda': 'Search could not be loaded', 'Recargue la página para intentarlo de nuevo.': 'Reload the page to try again.',
    'resultado': 'result', 'resultados': 'results', 'archivo': 'file', 'archivos': 'files',
    'Guía': 'Guide', 'Herramienta': 'Tool', 'Anuncio': 'Announcement', 'Versión': 'Release', 'Página': 'Page', 'Descarga': 'Download',
    'título': 'title', 'resumen': 'summary', 'autor': 'author', 'etiqueta': 'tag', 'Coincidencia en:': 'Match in:', 'Ir a:': 'Go to:',
    'Ordenar': 'Sort', 'en orden': 'in', 'ascendente': 'ascending order', 'descendente': 'descending order',
    'Abrir PDF': 'Open PDF', 'Abrir PDF original': 'Open original PDF', 'Descargar PDF': 'Download PDF', 'Exportar PDF': 'Export PDF',
    'Abrir en pestaña nueva': 'Open in new tab', 'Documento PDF': 'PDF document', 'Sitio oficial': 'Official site', 'Descarga aprobada': 'Approved download',
    'Copiar página': 'Copy page', 'Copiado': 'Copied', 'No se pudo copiar': 'Could not copy', 'Editar artículo': 'Edit article',
    'Borrador.': 'Draft.', 'Solo visible para editores.': 'Visible to editors only.', 'En esta página': 'On this page',
    'Artículo no disponible': 'Article unavailable', 'No se puede mostrar esta página.': 'This page cannot be shown.',
    'Si tiene una cuenta, ingrese para consultar el contenido de su equipo.': 'If you have an account, sign in to read your team’s content.', 'Volver a las guías': 'Back to guides',
    'Leer': 'Read', 'Estable': 'Stable', 'Próximamente': 'Coming soon', 'Publicado': 'Published', 'Borrador': 'Draft',
    'Archivos aprobados. Solo para usuarios de Athena.': 'Approved files. For Athena users only.',
    'Buscar descargas': 'Search downloads', 'Buscar archivo, sección o nota': 'Search file, section or note', 'Sección': 'Section',
    'Enlace permanente a la última versión:': 'Permanent link to the latest version:', 'Versiones anteriores': 'Previous versions',
    'Descargar': 'Download', 'Todavía no hay archivos publicados.': 'No files have been published yet.', 'No hay archivos que coincidan.': 'No files match.',
    'Lector · Última sesión': 'Reader · Last sign-in', 'Administrador · Última sesión': 'Administrator · Last sign-in', 'Lectura': 'Read', 'Lectura y escritura': 'Read and write', 'Administrador': 'Administrator', 'Lector': 'Reader', 'Última sesión': 'Last sign-in', 'nunca': 'never', 'Sesión': 'Session',
    'Cambie su contraseña o cierre la sesión en este navegador. Cambiar la contraseña cierra sus otras sesiones y revoca sus claves de API.': 'Change your password or sign out of this browser. Changing your password closes your other sessions and revokes your API keys.',
    'alta': 'joined', '· sesión': '· last sign-in', '· sesión nunca': '· last sign-in never', 'Cambiar contraseña': 'Change password', 'Cerrar sesión': 'Sign out', 'Mis claves de API': 'My API keys', 'Nombre': 'Name',
    'Permiso': 'Permission', 'Vence': 'Expires', 'Todavía no tiene claves de API.': 'You do not have any API keys yet.', 'Crear clave': 'Create key',
    'Guía de la API': 'API guide', 'Pida una clave a un administrador.': 'Ask an administrator for a key.', 'Artículos': 'Articles', 'Claves de API': 'API keys', 'Usuarios': 'Users',
    'El conocimiento del equipo, en un lugar.': 'Your team’s knowledge, in one place.',
    'Ingrese con su cuenta para consultar el contenido de su equipo, sus herramientas y descargas.': 'Sign in to read your team’s content, tools and downloads.',
    'Usuario': 'Username', 'Contraseña': 'Password', 'Ingresar a Athena': 'Sign in to Athena',
    'Si necesita una cuenta o perdió su contraseña, solicite ayuda al administrador de Athena.': 'If you need an account or have lost your password, ask your Athena administrator for help.',
    'Explorar la biblioteca pública': 'Explore the public library', 'Guardar contraseña': 'Save password', 'Volver a mi cuenta': 'Back to my account',
    'Contraseña antigua:': 'Old password:', 'Contraseña nueva:': 'New password:', 'Contraseña nueva (confirmación):': 'New password (confirmation):',
    'Su contraseña no puede asemejarse tanto a su otra información personal.': 'Your password cannot be too similar to your other personal information.',
    'Su contraseña debe contener al menos 12 caracteres.': 'Your password must contain at least 12 characters.',
    'Su contraseña no puede ser una clave utilizada comúnmente.': 'Your password cannot be a commonly used password.',
    'Su contraseña no puede ser completamente numérica.': 'Your password cannot be entirely numeric.',
    'Introduzca la misma contraseña nuevamente para poder verificar la misma.': 'Enter the same password again for verification.',
    'Introduzca la misma contraseña nuevamente para verificar.': 'Enter the same password again for verification.',
    'Para verificar, introduzca la misma contraseña anterior.': 'To verify, enter the same password again.',
    'Este campo es obligatorio.': 'This field is required.', 'Su contraseña antigua es incorrecta. Por favor, vuelva a introducirla.': 'Your old password is incorrect. Please enter it again.',
    'Los dos campos de contraseña no coinciden.': 'The two password fields do not match.',
    'Por favor, introduzca un nombre de usuario y clave correctos. Observe que ambos campos pueden ser sensibles a mayúsculas.': 'Please enter a correct username and password. Both fields may be case-sensitive.',
    'Esta cuenta está inactiva.': 'This account is inactive.',
    'Solicitar acceso a Athena': 'Request access to Athena', 'ATHENA · ACCESO INTERNO': 'ATHENA · INTERNAL ACCESS', 'Solicite acceso': 'Request access',
    'Athena permite únicamente direcciones IP públicas aprobadas.': 'Athena allows only approved public IP addresses.', 'Qué debe enviar': 'What to send',
    'Abra': 'Open', 'Copie los valores de IPv4 pública e IPv6 pública que aparecen en la página.': 'Copy the public IPv4 and public IPv6 values shown on the page.',
    'Envíe ambos valores a Jeiser Vargas. También puede escribirle mediante su conversación existente de WhatsApp.': 'Send both values to Jeiser Vargas. You can also use your existing WhatsApp conversation.',
    'Preparar correo': 'Prepare email', 'Importante': 'Important',
    'Una VPN, una red móvil o un cambio del proveedor de internet puede modificar su dirección pública. Si ocurre, solicite acceso otra vez.': 'A VPN, mobile network or internet provider change can change your public address. If this happens, request access again.',
    'Athena usa la dirección IP solo para controlar la lista de acceso. Esta página no publica el número de WhatsApp ni crea un enlace hacia ese servicio.': 'Athena uses the IP address only to control the access list. This page does not publish the WhatsApp number or link to that service.',
    // Administration: Athena's own templates, scripts, model and form texts. Django's built-in strings stay Spanish.
    'Administrar conocimiento y acceso': 'Manage knowledge and access', 'Última actividad': 'Recent activity', 'Todavía no hay actividad.': 'No activity yet.',
    'creó': 'created', 'editó': 'edited', 'eliminó': 'deleted', 'un elemento': 'an item', 'artículo': 'article', 'clave de API': 'API key', 'descarga': 'download', 'usuario': 'user',
    'ahora': 'now', 'ayer': 'yesterday', 'Título': 'Title', 'Tipo': 'Type', 'Estado': 'Status', 'Acceso': 'Access', 'Autor': 'Author', 'Fecha': 'Date',
    'Última modificación': 'Last modified', 'Público': 'Public', 'Con cuenta': 'Account only', 'Ver': 'View', 'Editar': 'Edit', 'Eliminar': 'Delete', 'Alfa': 'Alpha',
    'Sección': 'Section', 'Tamaño': 'Size', 'Creado': 'Created', 'Creada': 'Created', 'Paquetes': 'Packages', 'Ejercicios': 'Exercises', 'Nota': 'Note', 'Archivo': 'File',
    'Sin publicar: no se puede descargar': 'Unpublished: cannot be downloaded', 'Se calcula al guardar': 'Calculated on save', 'Sin guardar': 'Not saved',
    'Nueva descarga': 'New download', 'Editar descarga': 'Edit download', 'Nueva clave de API': 'New API key', 'Editar clave de API': 'Edit API key', 'Clave creada': 'Key created',
    'Administrar artículos': 'Manage articles', 'Administrar usuarios y artículos': 'Manage users and articles',
    'Documentación:': 'Documentation:', '· Verifique una clave con': '· Check a key with',
    'Selección': 'Selection', 'Eliminar seleccionados': 'Delete selected', 'Cancelar': 'Cancel',
    'Detalles': 'Details', 'Más opciones': 'More options', 'Guardar y continuar editando': 'Save and continue editing', 'Guardar y añadir otro': 'Save and add another',
    'Guardar como nuevo': 'Save as new', 'Historial': 'History', 'Ver artículo': 'View article', 'Eliminar artículo': 'Delete article', 'Importar Markdown': 'Import Markdown',
    'Archivos y publicación': 'Files and publishing', 'Ver el sitio': 'View site', 'Guardar': 'Save', 'Guardar cambios': 'Save changes',
    'Corrija los campos indicados.': 'Correct the marked fields.', 'Revisar detalles': 'Review details', 'Contenido del artículo': 'Article content',
    'Contenido Markdown': 'Markdown content', 'Vista previa': 'Preview', 'en vivo': 'live', 'La vista previa aparece al escribir Markdown.': 'The preview appears as you write Markdown.',
    'Pegue una imagen o use Insertar imagen. PNG, JPEG, WebP o GIF, hasta 10 MiB y 20 millones de píxeles. Se conserva el texto seleccionado.': 'Paste an image or use Insert image. PNG, JPEG, WebP or GIF, up to 10 MiB and 20 million pixels. Selected text is kept.',
    'Detalles del artículo': 'Article details', 'Información': 'Information', 'Publicación': 'Publishing', 'Archivos': 'Files',
    'Cerrar conserva los cambios pendientes.': 'Closing keeps pending changes.', 'Resumen': 'Summary', 'Etiquetas': 'Tags', 'Dirección': 'Address',
    'Separe las etiquetas con comas.': 'Separate tags with commas.', 'Se conserva después de crear el artículo para mantener sus enlaces.': 'Kept after the article is created, so its links keep working.',
    'Campos de herramienta': 'Tool fields', 'Estado de herramienta': 'Tool status', 'Acceso público': 'Public access',
    'Si está publicado, cualquier persona puede leer el artículo, sus imágenes y sus PDF sin una cuenta. Los borradores siguen restringidos.': 'When published, anyone can read the article, its images and its PDF files without an account. Drafts stay restricted.',
    'Subir Markdown': 'Upload Markdown', 'Opcional. Reemplaza el contenido. Máximo 1 MiB.': 'Optional. Replaces the content. Up to 1 MiB.', 'Adjuntar PDF': 'Attach PDF',
    'Opcional. Máximo 25 MiB.': 'Optional. Up to 25 MiB.', 'PDF actual': 'Current PDF', 'Sin PDF adjunto.': 'No PDF attached.', 'Quitar PDF actual': 'Remove current PDF', 'Solo PDF': 'PDF only',
    'El PDF adjunto es el contenido del artículo. El lector no ofrece «Exportar PDF».': 'The attached PDF is the article content. The reader does not offer “Export PDF”.',
    'No se pudo cargar la vista previa. Puede editar y guardar Markdown.': 'The preview could not be loaded. You can still edit and save Markdown.',
    'Espere a que terminen las imágenes antes de importar Markdown.': 'Wait for the images to finish before you import Markdown.', 'Leyendo Markdown. Espere para guardar.': 'Reading Markdown. Wait before you save.',
    'Use un archivo .md de hasta 1 MiB.': 'Use a .md file of up to 1 MiB.', 'No se pudo leer el archivo. Use Markdown UTF-8.': 'The file could not be read. Use UTF-8 Markdown.',
    'Insertar imagen': 'Insert image', 'Imagen insertada. Puede guardar el artículo.': 'Image inserted. You can save the article.', 'Use PNG, JPEG, WebP o GIF de hasta 10 MiB.': 'Use PNG, JPEG, WebP or GIF of up to 10 MiB.',
    'No se pudo conectar con el servidor. Vuelva a insertar la imagen.': 'Could not connect to the server. Insert the image again.', 'El servidor no respondió. Vuelva a insertar la imagen.': 'The server did not respond. Insert the image again.',
    'No se pudo subir la imagen. Intente de nuevo.': 'The image could not be uploaded. Try again.', 'La dirección de la imagen no es válida. Intente de nuevo.': 'The image address is not valid. Try again.', 'No se pudo subir la imagen.': 'The image could not be uploaded.',
    'Buscar usuario': 'Search users', 'Buscar usuario…': 'Search users…', 'Buscar por nombre de usuario, nombre o correo electrónico.': 'Search by username, name or email.',
    'Nuevo usuario': 'New user', 'Desplace la tabla para ver Estado y Sesión.': 'Scroll the table to see Status and Session.', 'Directorio de usuarios': 'User directory',
    'Seleccione un usuario para editar su perfil y acceso.': 'Select a user to edit their profile and access.', 'Activa': 'Active', 'Inactiva': 'Inactive',
    'No hay usuarios que coincidan con la búsqueda. Pruebe otro nombre.': 'No users match the search. Try another name.', 'Nombre de usuario': 'Username', 'Opcional': 'Optional',
    'Apellidos': 'Last name', 'Correo electrónico': 'Email', 'Correo electrónico no disponible': 'Email not available', 'No disponible': 'Not available',
    'El servicio de correo de Athena aún no está configurado. Por ahora no se pueden ingresar ni guardar correos. Para recuperar su contraseña, contacte al administrador.': 'Athena’s email service is not configured yet. For now, email addresses cannot be entered or saved. To recover your password, contact the administrator.',
    'Servicio de correo no configurado.': 'Email service not configured.', 'Usuario activo': 'Active user', 'Permisos de edición': 'Edit permissions', 'Usuarios y claves de API': 'Users and API keys',
    'Sin marcar, el administrador solo consulta.': 'Unchecked, the administrator can only view.', 'Restablecer contraseña': 'Reset password', 'Confirmar contraseña': 'Confirm password',
    'No puedes eliminar tu propia cuenta': 'You cannot delete your own account', 'Solo un administrador con todos los permisos puede editar esta cuenta.': 'Only an administrator with all permissions can edit this account.',
    'Copie la clave ahora. Athena guarda solo su hash y': 'Copy the key now. Athena stores only its hash and', 'no volverá a mostrarla': 'will not show it again',
    'Configurar en la terminal': 'Set up in the terminal', 'Comprobar acceso': 'Check access', 'Ya la copié': 'I copied it', 'Documentación de la API': 'API documentation'
  };
  const sourceText = new WeakMap();
  const sourceAttributes = new WeakMap();
  const content = '.guide-title,.guide-summary,.guide-author,.guide-topic-meta>span,.guide-topic h2,.guide-topic-jumps a,.tag-list,.search-result__body h2,.search-result__summary,.search-result__excerpt,.library-card>h2,.library-card>p:not([class]),.post-summary,.catalog-item>div';
  const articleUI = '.article-actions,.article-tools,.pdf-viewer__actions,.page-tree summary,.pagination-item,.unavailable-page';
  // Admin user content: titles, names, authors, usernames, the Markdown source and the raw key.
  const adminContent = '#result_list tbody :is(.field-title,.field-name,.field-author,.field-user),.actionlist a,.actionlist strong,.directory-table tbody th,.directory-panel header h2,.desk-user,.key-created code,textarea,.readonly a';
  const drafts = new WeakSet();
  const articleRoute = () => /^#\/content\//.test(location.hash);
  function eligible(element, attributes = false) {
    if (!element || element.closest('script,style,template,[data-suite-toggle],' + (attributes ? '' : 'time,') + content + ',' + adminContent)) return false;
    if (element.closest('.page-tree a')) return false;
    if (element.closest('.desk-preview-content') || articleRoute() && element.closest('.markdown-section') && !element.closest(articleUI)) {
      // Only the generated draft notice, not an authored blockquote, is interface text.
      const draft = element.closest('.markdown-section>blockquote:first-of-type,.desk-preview-content>blockquote:first-of-type');
      if (draft && draft.textContent.trim() === 'Borrador. Solo visible para editores.') drafts.add(draft);
      return Boolean(draft && drafts.has(draft));
    }
    return true;
  }
  // Server-rendered counts; the number stays as rendered.
  const plural = (n, word) => `${n} ${word}${n === '1' ? '' : 's'}`;
  const nouns = { 'artículo': 'article', 'clave de API': 'API key', 'claves de API': 'API key', 'descarga': 'download', 'usuario': 'user', 'archivo': 'file', 'palabra': 'word', 'imagen': 'image', 'imágenes': 'image' };
  const patterns = [[/^Mostrar (\d+) archivos?$/, (n) => `Show ${plural(n, 'file')}`], [/^(\d+) resultados?$/, (n) => plural(n, 'result')],
    [/^(\d+) (artículos?|claves? de API|descargas?|usuarios?|palabras?)$/, (n, noun) => plural(n, nouns[noun.replace(/s$/, '')] || nouns[noun])],
    [/^(\d+) seleccionados?$/, (n) => `${n} selected`], [/^hace (\d+) (min|h)$/, (n, unit) => `${n} ${unit} ago`], [/^hace (\d+) días$/, (n) => `${n} days ago`],
    [/^(Ver|Editar|Eliminar|Descargar): (.+)$/s, (verb, name) => `${english(verb)}: ${name}`],
    [/^(creó|editó|eliminó) (.+?) · (.+)$/, (verb, noun, when) => `${english(verb)} ${english(noun)} · ${english(when)}`],
    [/^Ordenar (.+) en orden (ascendente|descendente)$/, (label, order) => `Sort ${english(label)} in ${english(order)}`],
    [/^Clave de API · (.+) · (.+) · vence$/s, (name, scope) => `API key · ${name} · ${english(scope)} · expires`],
    [/^› (.+)$/s, (rest) => `› ${english(rest)}`],
    [/^Subiendo (\d+) imág?(?:en|enes)\. Puede seguir escribiendo; espere para guardar\.$/, (n) => `Uploading ${plural(n, 'image')}. You can keep writing; wait before you save.`],
    [/^(.+) importado\. Puede editar el Markdown antes de guardar\.$/s, (name) => `${name} imported. You can edit the Markdown before you save.`],
    [/^(.+?): (.+) Su texto se conservó\.$/s, (name, error) => `${name}: ${english(error)} Your text was kept.`]];
  function english(text) {
    if (dictionary[text]) return dictionary[text];
    for (const [pattern, format] of patterns) {
      const match = text.match(pattern);
      if (match) return format(...match.slice(1));
    }
    // Django label suffixes ("Título:") and joined state lines ("Publicado · Público") translate when every part does.
    if (text.endsWith(':') && dictionary[text.slice(0, -1)]) return dictionary[text.slice(0, -1)] + ':';
    const parts = text.split(' · ');
    if (parts.length > 1 && parts.every((part) => dictionary[part])) return parts.map((part) => dictionary[part]).join(' · ');
    return text;
  }
  const t = (text) => document.documentElement.lang === 'en' ? english(text) : text;
  function translateValue(source) {
    const trimmed = source.trim();
    return trimmed ? source.replace(trimmed, t(trimmed)) : source;
  }
  function translateNode(node) {
    if (!eligible(node.parentElement)) return;
    let record = sourceText.get(node);
    if (!record || record.rendered !== node.nodeValue) record = { source: node.nodeValue };
    record.rendered = translateValue(record.source);
    if (node.nodeValue !== record.rendered) node.nodeValue = record.rendered;
    sourceText.set(node, record);
  }
  function translateAttributes(element) {
    if (!eligible(element, true)) return;
    let records = sourceAttributes.get(element);
    if (!records) { records = {}; sourceAttributes.set(element, records); }
    for (const name of ['placeholder', 'aria-label', 'title', ...(element.matches('input[type=submit]') ? ['value'] : [])]) {
      const value = element.getAttribute(name);
      if (value === null) continue;
      let record = records[name];
      if (!record || record.rendered !== value) record = { source: value };
      record.rendered = translateValue(record.source);
      if (value !== record.rendered) element.setAttribute(name, record.rendered);
      records[name] = record;
    }
  }
  function formatDates() {
    const lang = document.documentElement.lang;
    for (const time of document.querySelectorAll('time[datetime],td[data-sort-value]')) {
      if (articleRoute() && time.closest('.markdown-section')) continue;
      const value = time.getAttribute('datetime') || time.dataset.sortValue;
      const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? value + 'T12:00:00' : value);
      if (!Number.isFinite(date.getTime())) continue;
      const day = time.querySelector('.day');
      const month = time.querySelector('.mon');
      if (day && month) {
        day.textContent = new Intl.DateTimeFormat(lang, { day: '2-digit' }).format(date);
        month.textContent = new Intl.DateTimeFormat(lang, { month: 'short' }).format(date);
      } else {
        const text = new Intl.DateTimeFormat(lang, { dateStyle: 'medium', ...(value.includes('T') ? { timeStyle: 'short' } : {}) }).format(date);
        if (time.textContent !== text) time.textContent = text;
      }
    }
    for (const month of document.querySelectorAll('.timeline-month')) {
      const value = month.querySelector('time')?.getAttribute('datetime');
      const heading = month.querySelector('h2');
      if (value && heading) heading.textContent = new Intl.DateTimeFormat(lang, { month: 'long', year: 'numeric' }).format(new Date(value + 'T12:00:00'));
    }
  }
  let queued = false;
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    queueMicrotask(() => { queued = false; translate(); });
  });
  function translate() {
    observer.disconnect();
    try {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) translateNode(walker.currentNode);
      document.querySelectorAll('[placeholder],[aria-label],[title],input[type=submit]').forEach(translateAttributes);
      formatDates();
    } finally {
      document.documentElement.classList.remove('suite-translating');
      // Observe the shell and current interface only, never authored article prose.
      const selectors = '.rail,.reader-command,.account-command,.account-header,.account-main,.request-main,.rail-tip,#container,' +
        (articleRoute() ? articleUI : '.markdown-section');
      document.querySelectorAll(selectors).forEach((element) => observer.observe(element, {
        childList: true, subtree: true, characterData: true, attributes: true,
        attributeFilter: ['placeholder', 'aria-label', 'title', 'value']
      }));
    }
  }
  window.AthenaI18n = { t, translate, dictionary, eligible };
  document.addEventListener('suite:lang', translate);
  translate();
})();
