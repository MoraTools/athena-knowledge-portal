import re
import shutil
import subprocess
import unittest

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from .forms import permissions
from .models import Article, Download, DownloadEvent


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class AdminFormatTests(TestCase):
    """One format in the admin: plain labels, one crumb model, and Django's strings in the suite language."""

    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser('root')
        cls.article = Article.objects.create(title='Guía de colas', slug='guia-de-colas', body='Texto')

    def setUp(self):
        self.client.force_login(self.root)

    def test_form_labels_have_no_trailing_colon(self):
        for url, label in [('/admin/athena/apikey/add/', 'Nombre'), ('/admin/athena/article/add/', 'Título'),
                           ('/admin/athena/download/add/', 'Título'),
                           (f'/admin/auth/user/{self.root.pk}/password/', 'Contraseña')]:
            with self.subTest(url=url):
                page = self.client.get(url).content.decode()
                self.assertRegex(page, rf'<label[^>]*>{label}</label>')
                self.assertNotRegex(page, r'<label[^>]*>[^<]*:</label>')
        # Read-only fields take the label from the form too.
        page = self.client.get(f'/admin/athena/article/{self.article.pk}/change/').content.decode()
        self.assertRegex(page, r'<label>Última modificación</label>')

    def test_crumbs_start_at_administracion_without_the_app_level(self):
        for url, trail in [('/admin/athena/article/', 'Artículos'), ('/admin/athena/apikey/add/', 'Nueva clave de API'),
                           (f'/admin/athena/article/{self.article.pk}/delete/', 'Guía de colas'),
                           (f'/admin/athena/article/{self.article.pk}/history/', 'Guía de colas'),
                           ('/admin/auth/user/', 'Usuarios')]:
            with self.subTest(url=url):
                page = self.client.get(url).content.decode()
                crumbs = page.split('<div class="breadcrumbs">', 1)[1].split('</div>', 1)[0]
                self.assertIn('>Administración</a>', crumbs)
                self.assertIn(trail, crumbs)
                self.assertNotIn('/admin/athena/"', crumbs)
                self.assertNotIn('/admin/auth/"', crumbs)
        page = self.client.get('/admin/').content.decode()
        self.assertIn('<div class="breadcrumbs">Administración</div>', page)
        self.assertIn('<h1>Administración</h1>', page)

    def test_django_strings_follow_the_language_cookie_and_spanish_stays_the_default(self):
        page = self.client.get('/admin/').content.decode()
        self.assertIn('Añadir', page)
        self.assertIn('data-lang="es"', page)
        self.client.cookies['django_language'] = 'en'
        page = self.client.get('/admin/').content.decode()
        self.assertIn('>Add</a>', page)
        self.assertNotIn('Añadir', page)
        self.assertIn('data-lang="en"', page)
        # The portal's own Spanish text stays for suite-i18n.js to translate in the browser.
        self.assertIn('Última actividad', page)
        del self.client.cookies['django_language']
        self.assertIn('>Add</a>', self.client.get('/admin/', HTTP_ACCEPT_LANGUAGE='en-GB,en;q=0.8').content.decode())
        self.assertIn('Añadir', self.client.get('/admin/', HTTP_ACCEPT_LANGUAGE='fr,pt;q=0.8').content.decode())

    def test_reader_paths_keep_spanish_and_no_language_vary(self):
        self.client.logout()
        self.client.cookies['django_language'] = 'en'
        response = self.client.get('/accounts/login/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertNotIn('Accept-Language', response.get('Vary', ''))
        self.assertNotIn('Content-Language', response)
        self.assertIn('lang="es"', response.content.decode())

    def test_list_dates_are_time_elements_for_the_interface_language(self):
        # suite-i18n.js shows each <time> as one medium date and time in the interface language; the text is the fallback.
        download = Download.objects.create(title='Plantilla', section='framework', slug='plantilla')
        moment = timezone.make_aware(timezone.datetime(2026, 11, 16, 17, 59))
        DownloadEvent.objects.create(download=download, username='luis', title='Plantilla', filename='p.zip', size=1,
                                     path='/downloads/plantilla', downloaded_at=moment)
        cell = '<td class="field-time"><time datetime="2026-11-16T17:59-05:00">16/11/2026 17:59</time></td>'
        self.assertIn(cell, self.client.get('/admin/athena/downloadevent/').content.decode())
        self.client.cookies['django_language'] = 'en'
        self.assertIn(cell, self.client.get('/admin/athena/downloadevent/').content.decode())
        del self.client.cookies['django_language']
        Article.objects.filter(pk=self.article.pk).update(date=timezone.datetime(2026, 11, 12).date())
        page = self.client.get('/admin/athena/article/').content.decode()
        self.assertIn('<td class="field-article_date"><time datetime="2026-11-12">12/11/2026</time></td>', page)
        self.assertRegex(page, r'<td class="field-last_updated"><time datetime="\d{4}-\d\d-\d\dT\d\d:\d\d-05:00">')
        self.assertRegex(self.client.get('/admin/athena/download/').content.decode(),
                         r'<td class="field-created"><time datetime="[^"]+T[^"]+">')


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class AdminEditorTests(TestCase):
    """Editor and admin: draft entry point, list filters, status chips, save state and the delete page."""

    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser('root')
        cls.viewer = User.objects.create_user('viewer', is_staff=True)
        cls.viewer.user_permissions.set(permissions(['athena.view_article']))
        cls.draft = Article.objects.create(title='Borrador de colas', slug='borrador-de-colas', body='Texto', author='Ana')
        cls.public = Article.objects.create(title='Guía pública', slug='guia-publica', body='Texto', published=True,
                                            is_public=True, kind='tool')
        cls.restricted = Article.objects.create(title='Informe interno', slug='informe-interno', body='Texto',
                                                published=True, is_restricted=True)

    def setUp(self):
        self.client.force_login(self.root)

    def test_dashboard_links_drafts_and_hides_field_list_change_messages(self):
        from django.contrib.admin.models import CHANGE, LogEntry
        from django.contrib.contenttypes.models import ContentType
        kind = ContentType.objects.get_for_model(Article)
        LogEntry.objects.create(user=self.root, content_type=kind, object_id=str(self.public.pk), object_repr='Guía pública',
                                action_flag=CHANGE, change_message='[{"changed": {"fields": ["Contenido"]}}]')
        LogEntry.objects.create(user=self.root, content_type=kind, object_id=str(self.public.pk), object_repr='Guía pública',
                                action_flag=CHANGE, change_message='Revisado por el equipo.')
        page = self.client.get('/admin/').content.decode()
        self.assertIn('href="/admin/athena/article/?published__exact=0"><span>Borradores</span> 1</a>', page)
        self.assertNotIn('Modificado Contenido', page)
        self.assertIn('Revisado por el equipo.', page)
        self.client.force_login(self.viewer)
        self.assertNotIn('<span>Borradores</span>', self.client.get('/admin/').content.decode())

    def test_list_filters_are_selects_with_list_filter_parameters(self):
        page = self.client.get('/admin/athena/article/?access=restricted&o=1').content.decode()
        for name in ['published__exact', 'access', 'kind__exact']:
            self.assertIn(f'<select name="{name}">', page)
        self.assertIn('<option value="restricted" selected>Restringido</option>', page)
        self.assertIn('<input type="hidden" name="o" value="1">', page)
        self.assertNotIn('<input type="hidden" name="access"', page)
        self.assertNotIn('id="changelist-filter"', page)
        # A select change does not reload the list (keyboard users keep their place); the Filtrar button applies the choices.
        self.assertRegex(page, r'(?s)<div class="list-filters">.*<input type="submit" value="Filtrar">\s*</div>')
        script = (settings.BASE_DIR / 'server/athena/static/athena/admin-list.js').read_text()
        self.assertNotIn('requestSubmit', script)
        self.assertNotIn('.list-filters', script)
        for query, titles in [('access=restricted', ['Informe interno']), ('access=public', ['Guía pública']),
                              ('access=account', ['Borrador de colas']), ('published__exact=0', ['Borrador de colas']),
                              ('kind__exact=tool', ['Guía pública'])]:
            with self.subTest(query=query):
                listed = [a.title for a in self.client.get('/admin/athena/article/?' + query).context['cl'].result_list]
                self.assertEqual(listed, titles)

    def test_editor_chips_say_a_draft_is_for_editors_and_a_save_shows_its_time(self):
        page = self.client.get(f'/admin/athena/article/{self.draft.pk}/change/').content.decode()
        self.assertIn('<span class="pill warn">Borrador</span><span class="pill off">Solo editores</span>'
                      '<span class="state-next"><span>al publicar:</span> <span>Con cuenta</span></span>', page)
        self.assertIn('<textarea name="title"', page)
        self.assertNotIn('Guardado', page)
        # The preview drops placement tags from its chips; the list comes from models.PLACEMENT_TAGS, not a copy in the script.
        for url in [f'/admin/athena/article/{self.draft.pk}/change/', '/admin/athena/article/add/']:
            self.assertIn('data-placement-tags="primeros-pasos"', self.client.get(url).content.decode())
        page = self.client.get(f'/admin/athena/article/{self.restricted.pk}/change/').content.decode()
        self.assertIn('<span class="pill">Publicado</span><span class="pill warn">Restringido</span>', page)
        data = {'title': 'Borrador\r\nde  colas', 'slug': self.draft.slug, 'kind': 'guide', 'summary': 'Resumen', 'author': 'Ana', 'format': 'markdown',
                'date': self.draft.date.isoformat(), 'tags': '', 'body': 'Texto', 'access': 'account',
                'loaded_revision': self.draft.updated_at.isoformat(), '_continue': '1'}
        response = self.client.post(f'/admin/athena/article/{self.draft.pk}/change/', data, follow=True)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, 'Borrador de colas')
        saved = timezone.localtime(self.draft.updated_at).strftime('%H:%M')
        self.assertContains(response, f'<span>Guardado</span> {saved}')

    def test_delete_page_shows_state_and_final_warning(self):
        page = self.client.get(f'/admin/athena/article/{self.public.pk}/delete/').content.decode()
        self.assertIn('<span class="pill">Publicado</span><span class="pill">Público</span>', page)
        self.assertIn('<p>El enlace para compartir del artículo deja de funcionar.</p>', page)  # No images, no PDF.
        self.assertIn('Esta acción no se puede deshacer.', page)
        self.assertIn('<input type="submit" value="Eliminar artículo">', page)
        # Cancelar has a destination without script (Django's cancel.js still goes back when it runs).
        self.assertIn(f'<a href="/admin/athena/article/{self.public.pk}/change/" class="button cancel-link">Cancelar</a>', page)
        self.assertNotIn('deleted-objects', page)
        self.client.post(f'/admin/athena/article/{self.public.pk}/delete/', {'post': 'yes'})
        self.assertFalse(Article.objects.filter(pk=self.public.pk).exists())

    def test_delete_page_names_only_what_the_article_has(self):
        page = self.client.get(f'/admin/athena/article/{self.draft.pk}/delete/').content.decode()
        self.assertNotIn('de funcionar', page)  # A draft with no images and no PDF: only the final warning.
        self.assertIn('Esta acción no se puede deshacer.', page)
        # update() skips the reference check that save() runs; the page reads the body only.
        Article.objects.filter(pk=self.draft.pk).update(
            body='![x](/article-images/00000000-0000-4000-8000-000000000001/)', pdf_name='plan.pdf')
        page = self.client.get(f'/admin/athena/article/{self.draft.pk}/delete/').content.decode()
        self.assertIn('<p>Las imágenes y el PDF del artículo dejan de funcionar.</p>', page)
        Article.objects.filter(pk=self.public.pk).update(pdf_name='plan.pdf')
        page = self.client.get(f'/admin/athena/article/{self.public.pk}/delete/').content.decode()
        self.assertIn('<p>El enlace para compartir y el PDF del artículo dejan de funcionar.</p>', page)

    def test_editor_h1_is_the_first_heading(self):
        for url in [f'/admin/athena/article/{self.public.pk}/change/', '/admin/athena/article/add/']:
            with self.subTest(url=url):
                main = self.client.get(url).content.decode().split('<div id="content-main">', 1)[1]
                self.assertRegex(main, r'^\s*<h1 class="visually-hidden">')

    def test_one_create_verb_and_ver_for_the_read_only_log(self):
        page = self.client.get('/admin/athena/article/').content.decode()
        self.assertIn('class="button default">Nuevo artículo</a>', page)
        self.assertNotIn('Añadir artículo', page)
        page = self.client.get('/admin/').content.decode()
        self.assertRegex(page, r'href="/admin/athena/downloadevent/" class="viewlink"[^>]*>Ver</a>')
        self.assertNotIn('>Vista</a>', page)

    def test_each_list_create_button_matches_its_add_page_title(self):
        from django.contrib import admin
        from django.urls import reverse
        from .admin import RowControlsAdmin
        checked = []
        for model, model_admin in admin.site._registry.items():
            base = f'admin:{model._meta.app_label}_{model._meta.model_name}'
            if not isinstance(model_admin, RowControlsAdmin) or not model_admin.has_add_permission(type('R', (), {'user': self.root})()):
                continue
            with self.subTest(model=model.__name__):
                page = self.client.get(reverse(base + '_changelist') + '?o=1').content.decode()
                add = self.client.get(reverse(base + '_add')).content.decode()
                title = re.search(r'<title>(.+?) · Athena</title>', add)[1]
                # One slot: the button in the title row, no Django object tools.
                self.assertRegex(page, rf'<div class="page-head"><h1>[^<]+</h1>\s*<a href="{reverse(base + "_add")}'
                                       rf'\?_changelist_filters=o%3D1" class="button default">{title}</a></div>')
                self.assertNotIn('class="object-tools"', page)
                checked.append(title)
        self.assertEqual(sorted(checked), ['Nueva clave de API', 'Nueva descarga', 'Nuevo artículo'])

    def test_app_list_is_django_s_with_only_the_ver_link_changed(self):
        # A copy of Django's template: a Django update that changes the original must fail here, so the copy follows it.
        from pathlib import Path
        import django
        ours = (settings.BASE_DIR / 'server/athena/templates/admin/app_list.html').read_text().splitlines()
        theirs = (Path(django.__file__).parent / 'contrib/admin/templates/admin/app_list.html').read_text().splitlines()
        self.assertTrue(ours[0].startswith('{#') and ours[0].endswith('#}'), ours[0])
        self.assertEqual(len(ours[1:]), len(theirs))
        changed = [(a, b) for a, b in zip(ours[1:], theirs) if a != b]
        self.assertEqual(changed, [(theirs_line.replace("{% translate 'View' %}", 'Ver'), theirs_line)
                                   for theirs_line in theirs if "{% translate 'View' %}" in theirs_line])
        self.assertEqual(len(changed), 1)

    def test_directory_create_button_is_in_the_title_row(self):
        page = self.client.get('/admin/auth/user/').content.decode()
        self.assertRegex(page, r'<div class="page-head"><h1 id="directory-title">Usuarios</h1>\s*<a class="button ghost directory-add"')

    def test_new_article_fields_have_placeholders(self):
        page = self.client.get('/admin/athena/article/add/').content.decode()
        self.assertRegex(page, r'<textarea name="title"[^>]*placeholder="Título del artículo"')
        self.assertRegex(page, r'<textarea name="body"[^>]*placeholder="Escriba el artículo aquí. Tipo, resumen y acceso están en Detalles."')

    def test_tags_help_counts_the_published_first_steps_articles(self):
        Article.objects.create(title='Inicio', slug='inicio', body='Texto', published=True, tags=['Primeros-Pasos'])
        Article.objects.create(title='Borrador', slug='borrador-inicio', body='Texto', tags=['primeros-pasos'])
        Article.objects.create(title='Otro', slug='otro', body='Texto', published=True, tags=['primeros-pasos-extra'])
        for url in [f'/admin/athena/article/{self.draft.pk}/change/', '/admin/athena/article/add/']:
            with self.subTest(url=url):
                self.assertIn('el artículo aparece en Primeros pasos en el inicio.<br>Artículos publicados con primeros-pasos: 1. '
                              'El inicio muestra los 5 de fecha más antigua.</div>', self.client.get(url).content.decode())

    def test_lists_mark_the_exceptions_not_the_normal_state(self):
        page = self.client.get('/admin/athena/article/').content.decode()
        self.assertIn('<td class="field-state"><span class="pill warn">Borrador</span></td>', page)
        self.assertIn('<td class="field-state"><span class="pill">Publicado</span></td>', page)
        self.assertIn('<td class="field-access"><span class="pill">Público</span></td>', page)
        # A draft is for editors only, with the access it gets on publishing, as in the editor head and the delete page.
        self.assertIn('<td class="field-access"><span class="pill off">Solo editores</span><span class="state-next">'
                      '<span>al publicar:</span> <span>Con cuenta</span></span></td>', page)
        self.assertIn('<td class="field-access"><span class="pill warn">Restringido (0)</span></td>', page)
        self.assertNotIn('pill gold', page)

    def test_download_lists_name_what_they_search(self):
        for url, text in [('/admin/athena/download/', 'Buscar archivos de descarga'),
                          ('/admin/athena/downloadevent/', 'Buscar en el registro')]:
            with self.subTest(url=url):
                page = self.client.get(url + '?q=plan&o=1').content.decode()
                self.assertIn(f'<label class="visually-hidden" for="searchbar">{text}</label>', page)
                self.assertIn(f'<input type="search" name="q" value="plan" id="searchbar" placeholder="{text}">', page)
                self.assertIn('<input type="hidden" name="o" value="1">', page)
                self.assertNotIn('<input type="hidden" name="q"', page)

    def test_rail_names_each_entry_once(self):
        page = self.client.get('/admin/').content.decode()
        labels = re.findall(r'<span class="rail-label">([^<]+)</span></a>', page)
        self.assertEqual(len(labels), len(set(labels)), labels)
        self.assertIn('Archivos de descarga', labels)

    def test_directory_names_editors_and_administrators(self):
        editor = User.objects.create_user('editora', is_staff=True)
        reader = User.objects.create_user('lectora')
        page = self.client.get(f'/admin/auth/user/?user={editor.pk}').content.decode()
        for user, role in [(self.root, 'Administrador'), (editor, 'Editor'), (reader, 'Lector')]:
            with self.subTest(user=user.username):
                row = re.search(rf'<tr[^>]*data-search="{user.username} .*?</tr>', page, re.S).group()
                self.assertIn(f'">{role}</span></td>', row)
        # The inspector shows the selected account's role; its access choice names editors, as the roster does.
        self.assertIn('<p class="mono"><span class="pill">Editor</span> alta', page)
        self.assertRegex(page, r'<label class="directory-choice"><input[^>]*value="admin"[^>]*>Editor</label>')
        users = self.client.get('/admin/auth/user/?sort=role').context['users']
        self.assertEqual([row[2] for row in users], ['Administrador', 'Editor', 'Editor', 'Lector'])

    def test_api_key_expiry_names_the_site_time_zone(self):
        self.assertContains(self.client.get('/admin/athena/apikey/add/'), 'Zona horaria: America/Lima.')

    def test_api_key_form_explains_owner_scope_and_the_one_time_key(self):
        page = self.client.get('/admin/athena/apikey/add/').content.decode()
        self.assertIn('<h2>La clave se muestra una sola vez, después de guardar.</h2>', page)
        self.assertIn('La clave actúa con los permisos de este usuario.', page)
        self.assertIn('Lectura: leer los artículos publicados, sus PDF y las descargas.<br>', page)

    def test_every_save_button_shows_the_new_key_once(self):
        # Django's extra save buttons stay: response_add shows the key page for each of them.
        for button in ['_save', '_addanother', '_continue']:
            with self.subTest(button=button):
                response = self.client.post('/admin/athena/apikey/add/', {
                    'name': button, 'user': self.root.pk, 'scope': 'read', 'expires_at': '2099-01-01T00:00', button: '1'})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<code class="secret" id="raw-key">athena_')

    def test_api_key_list_marks_expired_and_expiring_keys(self):
        from datetime import timedelta
        from .models import ApiKey
        now = timezone.now()
        for name, days in [('vieja', -1), ('pronto', 5), ('larga', 60)]:
            key = ApiKey(name=name, user=self.root, expires_at=now + timedelta(days=days))
            key.issue()
            key.save()
        page = self.client.get('/admin/athena/apikey/').content.decode()
        for name, chip in [('vieja', '<span class="pill warn">Vencida</span>'), ('pronto', '<span class="pill warn">Vence pronto</span>'),
                           ('larga', '<span class="pill">Activa</span>')]:
            with self.subTest(name=name):
                row = re.search(rf'<tr>.*?>{name}</a>.*?</tr>', page, re.S).group()
                self.assertIn(f'<td class="field-status">{chip}</td>', row)


class TagTests(TestCase):
    """Tags: a native list of the tags in use, and one spelling per tag on save."""

    @classmethod
    def setUpTestData(cls):
        cls.editor = User.objects.create_user('editor', is_staff=True)
        cls.editor.user_permissions.set(permissions(['athena.view_article', 'athena.change_article']))
        Article.objects.create(title='Uno', slug='uno', body='x', tags=['Excel', 'Plantilla base'])
        Article.objects.create(title='Dos', slug='dos', body='x', tags=['Excel', 'excel tips'])
        Article.objects.create(title='Interno', slug='interno', body='x', tags=['Cliente secreto'], is_restricted=True)
        cls.own = Article.objects.create(title='Tres', slug='tres', body='x', tags=['Demos'])

    def form(self, instance=None, tags=''):
        from .forms import ArticleForm
        return ArticleForm({'tags': tags}, instance=instance or Article(), actor=self.editor)

    def test_list_offers_readable_tags_once(self):
        html = str(self.form()['tags'])
        self.assertIn('list="id_tags-options"', html)
        options = re.findall(r'<option value="([^"]*)">', html)
        self.assertEqual(options, ['Demos', 'Excel', 'excel tips', 'Plantilla base'])

    def test_save_trims_and_keeps_the_spelling_in_use(self):
        form = self.form(tags='  excel ,Plantilla   base, EXCEL, Nuevo ,, ')
        form.is_valid()
        self.assertEqual(form.cleaned_data['tags'], ['Excel', 'Plantilla base', 'Nuevo'])
        # An unreadable article's spelling is neither offered nor applied.
        form = self.form(tags='cliente secreto')
        form.is_valid()
        self.assertEqual(form.cleaned_data['tags'], ['cliente secreto'])
        # An article may change the case of a tag only it uses.
        form = self.form(self.own, tags='DEMOS')
        form.is_valid()
        self.assertEqual(form.cleaned_data['tags'], ['DEMOS'])


def run_node(script):
    """Runs a check script with node from the repository root (where node_modules is); returns its stdout."""
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=settings.BASE_DIR, capture_output=True,
                            text=True, timeout=60)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class AdminScriptTests(TestCase):
    """admin-list.js and the editor preview, run in node with a minimal DOM."""

    def test_selection_bar_reserves_its_height_for_focus_scrolling(self):
        out = run_node(r"""
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const handlers = {}, html = { style: {} }, observed = [];
const el = (extra = {}) => ({ setAttribute() {}, addEventListener(type, fn) { handlers[type] = fn; }, ...extra });
const bar = el({ hidden: false, offsetHeight: 46, querySelector: () => el({ textContent: '' }) });
const boxes = [el({ checked: false, dispatchEvent() {} }), el({ checked: false, dispatchEvent() {} })];
const form = el({
  querySelector: (s) => s.startsWith('.bulk-source select') ? { options: [{ value: 'delete_selected' }], value: '' } : el({ after() {}, before() {} }),
  querySelectorAll: () => boxes });
vm.runInNewContext(readFileSync('server/athena/static/athena/admin-list.js', 'utf8'), {
  document: { getElementById: () => form, createElement: () => bar, documentElement: html },
  window: { addEventListener() {} }, Event: class {},
  ResizeObserver: class { constructor(fn) { this.fn = fn; } observe(node) { observed.push(node); } } });
const states = [html.style.scrollPaddingBottom || ''];
boxes[0].checked = true; handlers.change(); states.push(html.style.scrollPaddingBottom);
boxes[0].checked = false; handlers.change(); states.push(html.style.scrollPaddingBottom || '');
console.log(JSON.stringify({ states, observed: observed.includes(bar) }));
""")
        self.assertEqual(out.strip(), '{"states":["","62px",""],"observed":true}')

    def test_preview_title_is_a_level_two_heading(self):
        out = run_node(r"""
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import * as marked from 'marked';
const window = {};
vm.runInNewContext(readFileSync('server/athena/static/athena/article-editor.js', 'utf8'), {
  window, document: { addEventListener() {} }, marked, URL, location: { origin: 'https://athena.test' },
  DOMPurify: { sanitize: (html) => html } });
console.log(window.athenaRenderMarkdown('Texto\n\n## Parte', { title: 'Guía', published: true }));
""")
        self.assertIn('<h1 aria-level="2">Guía</h1>', out)
        self.assertIn('<h2>Parte</h2>', out)
