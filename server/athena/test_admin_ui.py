from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

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
