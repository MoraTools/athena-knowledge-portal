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

    def test_english_keeps_numeric_dates(self):
        download = Download.objects.create(title='Plantilla', section='framework', slug='plantilla')
        moment = timezone.make_aware(timezone.datetime(2026, 11, 16, 17, 59))
        DownloadEvent.objects.create(download=download, username='luis', title='Plantilla', filename='p.zip', size=1,
                                     path='/downloads/plantilla', downloaded_at=moment)
        self.client.cookies['django_language'] = 'en'
        page = self.client.get('/admin/athena/downloadevent/').content.decode()
        self.assertIn('<td class="field-time">16/11/2026 17:59</td>', page)


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
        self.assertIn('href="/admin/athena/article/?published__exact=0"><span>Borradores:</span> 1</a>', page)
        self.assertNotIn('Modificado Contenido', page)
        self.assertIn('Revisado por el equipo.', page)
        self.client.force_login(self.viewer)
        self.assertNotIn('Borradores:', self.client.get('/admin/').content.decode())

    def test_list_filters_are_selects_with_list_filter_parameters(self):
        page = self.client.get('/admin/athena/article/?access=restricted&o=1').content.decode()
        for name in ['published__exact', 'access', 'kind__exact']:
            self.assertIn(f'<select name="{name}">', page)
        self.assertIn('<option value="restricted" selected>Restringido</option>', page)
        self.assertIn('<input type="hidden" name="o" value="1">', page)
        self.assertNotIn('<input type="hidden" name="access"', page)
        self.assertNotIn('id="changelist-filter"', page)
        for query, titles in [('access=restricted', ['Informe interno']), ('access=public', ['Guía pública']),
                              ('access=account', ['Borrador de colas']), ('published__exact=0', ['Borrador de colas']),
                              ('kind__exact=tool', ['Guía pública'])]:
            with self.subTest(query=query):
                listed = [a.title for a in self.client.get('/admin/athena/article/?' + query).context['cl'].result_list]
                self.assertEqual(listed, titles)

    def test_editor_chips_say_a_draft_is_for_editors_and_a_save_shows_its_time(self):
        page = self.client.get(f'/admin/athena/article/{self.draft.pk}/change/').content.decode()
        self.assertIn('<span class="pill off">Borrador</span><span class="pill off">Solo editores</span>'
                      '<span class="state-next"><span>al publicar:</span> <span>Con cuenta</span></span>', page)
        self.assertIn('<textarea name="title"', page)
        self.assertNotIn('Guardado', page)
        page = self.client.get(f'/admin/athena/article/{self.restricted.pk}/change/').content.decode()
        self.assertIn('<span class="pill gold">Publicado</span><span class="pill">Restringido</span>', page)
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
        self.assertIn('<span class="pill gold">Publicado</span><span class="pill gold">Público</span>', page)
        self.assertIn('Esta acción no se puede deshacer.', page)
        self.assertIn('<input type="submit" value="Eliminar artículo">', page)
        self.assertIn('class="button cancel-link">Cancelar</a>', page)
        self.assertNotIn('deleted-objects', page)
        self.client.post(f'/admin/athena/article/{self.public.pk}/delete/', {'post': 'yes'})
        self.assertFalse(Article.objects.filter(pk=self.public.pk).exists())

    def test_api_key_expiry_names_the_site_time_zone(self):
        self.assertContains(self.client.get('/admin/athena/apikey/add/'), 'Zona horaria: America/Lima.')
