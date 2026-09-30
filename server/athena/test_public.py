import fcntl
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings

from .forms import ArticleForm, permissions
from .models import ApiKey, Article, Download


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class PublicArticleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = User.objects.create_user('reader')
        cls.editor = User.objects.create_user('editor', is_staff=True)
        cls.editor.user_permissions.set(permissions(['athena.change_article', 'athena.add_article']))
        cls.other_admin = User.objects.create_user('download-admin', is_staff=True)
        cls.other_admin.user_permissions.set(permissions(['athena.view_article', 'athena.change_download']))
        cls.articles = {}
        for published, public in [(True, True), (True, False), (False, True), (False, False)]:
            slug = f'article-{int(published)}-{int(public)}'
            cls.articles[published, public] = Article.objects.create(
                title=slug, slug=slug, summary='Summary ' + slug, author='Author ' + slug,
                body='# ' + slug + '\n\n## Unique section\n\nText ' + slug,
                tags=[slug], published=published, is_public=public, pdf=b'%PDF-1.4\n%%EOF', pdf_name=slug + '.pdf')

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(DATA_DIR=self.root, MEDIA_ROOT=self.root / 'media'))

    def key(self, user, scope):
        key = ApiKey(user=user, scope=scope, name='test')
        raw = key.issue()
        key.save()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + raw}

    @staticmethod
    def render_pdf(command, **kwargs):
        Path(command[-1]).write_bytes(b'%PDF-1.4\n%%EOF')

    def test_access_matrix_for_markdown_attachment_and_export(self):
        for user in [None, self.reader, self.editor, self.other_admin]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            for (published, public), article in self.articles.items():
                allowed = user == self.editor or (published and (public or user is not None))
                for path in [f'/content/{article.slug}.md', f'/content/{article.slug}',
                             f'/pdf/{article.slug}.pdf', f'/pdf/{article.slug}.pdf?download=1',
                             f'/content/{article.slug}.pdf']:
                    with self.subTest(user=user, path=path), patch('athena.pdf_export.subprocess.run', side_effect=self.render_pdf) as renderer:
                        response = self.client.get(path)
                        self.assertEqual(response.status_code, 200 if allowed else 404)
                        if not allowed:
                            renderer.assert_not_called()
                        if response.streaming:
                            self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))

    def test_public_search_and_libraries_never_disclose_private_metadata_or_downloads(self):
        Download.objects.create(title='Secret package', file=ContentFile(b'secret', name='secret.zip'))
        public = self.articles[True, True]
        for path in ['/search-index.json', '/guides.md', '/updates.md']:
            response = self.client.get(path)
            self.assertContains(response, public.slug)
            self.assertNotContains(response, 'Secret package')
            self.assertNotContains(response, 'secret.zip')
            for key, article in self.articles.items():
                if key != (True, True):
                    self.assertNotContains(response, article.slug)
        self.assertEqual(len(self.client.get('/search-index.json').json()), 1)
        for article in self.articles.values():
            article.kind, article.status = 'tool', 'stable'
            article.save()
        self.assertContains(self.client.get('/tools.md'), public.slug)
        self.assertNotContains(self.client.get('/tools.md'), self.articles[True, False].slug)
        self.client.force_login(self.reader)
        self.assertEqual(len(self.client.get('/search-index.json').json()), 3)  # Two articles plus the protected download.

    def test_public_shell_navigation_and_unavailable_page(self):
        for path in ['/', '/README.md', '/_sidebar.md', '/search.md', '/not-found.md']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow, noarchive')
            self.assertIn('no-store', response['Cache-Control'])
            self.assertIn('Cookie', response['Vary'])
        sidebar = self.client.get('/_sidebar.md')
        self.assertContains(sidebar, '[Ingresar](/accounts/login/)')
        for label in ['Descargas', 'Mi cuenta', 'Administración', 'Contribuir']:
            self.assertNotContains(sidebar, label)
        self.assertNotContains(self.client.get('/README.md'), '#/downloads')
        self.assertNotContains(self.client.get('/search.md'), 'value="download"')
        self.assertContains(self.client.get('/not-found.md'), 'Ingresar')
        for path in ['/account.md', '/downloads.md', '/api.md']:
            self.assertEqual(self.client.get(path).status_code, 404)
        for path in ['/downloads/framework/latest', '/downloads/missing', '/admin/']:
            self.assertEqual(self.client.get(path).status_code, 302)
        Article.objects.update(is_public=False)
        self.assertContains(self.client.get('/README.md'), 'Todavía no hay artículos públicos')
        self.assertEqual(self.client.get('/search-index.json').json(), [])

    def test_admin_controls_follow_existing_edit_permissions(self):
        article = self.articles[True, False]
        url = f'/admin/athena/article/{article.pk}/change/'
        self.client.force_login(self.other_admin)
        self.assertNotContains(self.client.get(url), 'name="is_public"')
        self.assertEqual(self.client.post(url, {'is_public': 'True'}).status_code, 403)
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(url), 'name="is_public"')
        self.assertContains(self.client.get(url), 'Con cuenta')
        self.assertContains(self.client.get(url), 'Público')
        self.assertContains(self.client.get('/admin/athena/article/'), 'Acceso')
        for value, expected in [('True', True), ('False', False)]:
            form = ArticleForm({'title': article.title, 'slug': article.slug, 'kind': article.kind,
                                'summary': article.summary, 'author': article.author, 'date': article.date,
                                'body': article.body, 'published': 'on', 'is_public': value}, instance=article)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.save().is_public, expected)

    def test_api_visibility_defaults_scopes_and_etags(self):
        editor = self.key(self.editor, 'articles')
        data = {'slug': 'created', 'title': 'Created', 'summary': 'Summary', 'author': 'Author', 'body': '# Body', 'published': True}
        response = self.client.post('/api/v1/articles/', json.dumps(data), content_type='application/json', **editor)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.json()['is_public'])
        url = '/api/v1/articles/created/'
        self.assertEqual(self.client.patch(url, '{"is_public":true}', content_type='application/json', **editor).status_code, 412)
        response = self.client.patch(url, '{"is_public":true}', content_type='application/json', HTTP_IF_MATCH=response['ETag'], **editor)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(self.client.get('/content/created.md'), '# Body')
        self.assertEqual(self.client.get(url).status_code, 401)
        read = self.key(self.editor, 'read')  # Editor ownership must not bypass a read-only key's scope.
        self.assertEqual(self.client.get('/api/v1/articles/' + self.articles[False, True].slug + '/', **read).status_code, 404)
        self.assertEqual(self.client.patch(url, '{"is_public":false}', content_type='application/json', HTTP_IF_MATCH=response['ETag'], **read).status_code, 403)
        other = self.key(self.other_admin, 'articles')
        self.assertEqual(self.client.patch(url, '{"is_public":true}', content_type='application/json', HTTP_IF_MATCH=response['ETag'], **other).status_code, 403)
        self.assertEqual(self.client.patch(url, '{"is_public":"true"}', content_type='application/json', HTTP_IF_MATCH=response['ETag'], **editor).status_code, 400)

    def test_cached_pdf_is_reused_invalidated_and_rechecked_for_access(self):
        article = self.articles[True, True]
        url = f'/content/{article.slug}.pdf'
        with patch('athena.pdf_export.subprocess.run', side_effect=self.render_pdf) as renderer:
            for _ in range(2):
                self.assertTrue(b''.join(self.client.get(url).streaming_content).startswith(b'%PDF'))
            self.assertEqual(renderer.call_count, 1)
            self.assertEqual(renderer.call_args.kwargs['timeout'], 30)
            article.body += '\nNew text'
            article.save()
            self.client.get(url).close()
            self.assertEqual(renderer.call_count, 2)
            self.assertEqual(len(list((self.root / 'pdf-cache').glob('*.pdf'))), 1)
            article.is_public = False
            article.save()
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(renderer.call_count, 2)
            self.assertNotContains(self.client.get('/search-index.json'), article.slug)
            self.assertEqual(self.client.get(f'/pdf/{article.slug}.pdf').status_code, 404)

    def test_render_limits_and_revocation_during_render(self):
        article = self.articles[True, True]
        url = f'/content/{article.slug}.pdf'
        root = self.root / 'pdf-cache'
        root.mkdir()
        with (root / 'render.lock').open('a') as lock, patch('athena.pdf_export.subprocess.run') as renderer:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response['Retry-After'], '10')
            renderer.assert_not_called()
        with patch('athena.pdf_export.subprocess.run', side_effect=subprocess.TimeoutExpired('renderer', 30)):
            self.assertEqual(self.client.get(url).status_code, 503)
            self.assertEqual(list(root.glob('*.pdf')), [])
        def withdraw(command, **kwargs):
            self.render_pdf(command, **kwargs)
            Article.objects.filter(pk=article.pk).update(is_public=False)
        with patch('athena.pdf_export.subprocess.run', side_effect=withdraw):
            self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(ALLOWED_HOSTS=['athena.moratechnology.com'],
                       PUBLIC_ORIGIN='https://athena.moratechnology.com')
    def test_pdf_cache_and_links_ignore_host_variants(self):
        article = self.articles[True, True]
        article.body += '\n\n[Tools](#/tools)'
        article.save()
        url = f'/content/{article.slug}.pdf'
        with patch('athena.pdf_export.subprocess.run', side_effect=self.render_pdf) as renderer:
            for host in ['athena.moratechnology.com', 'athena.moratechnology.com:4444',
                         'ATHENA.MORATECHNOLOGY.COM', 'athena.moratechnology.com.:443',
                         'athena.moratechnology.com']:
                with self.subTest(host=host):
                    response = self.client.get(url, secure=True, HTTP_HOST=host)
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))
            self.assertEqual(renderer.call_count, 1)
            source = json.loads(renderer.call_args.kwargs['input'])
            self.assertEqual(source['base_url'], 'https://athena.moratechnology.com' + url)
            self.assertIn('href="https://athena.moratechnology.com/#/tools"', source['html'])
            self.assertEqual(len(list((self.root / 'pdf-cache').glob('*.pdf'))), 1)

    def test_sign_in_return_path_and_logout_remove_private_access(self):
        self.reader.set_password('Public-Test-Reader-493!')
        self.reader.save()
        target = '/#/content/' + self.articles[True, False].slug
        response = self.client.post('/accounts/login/', {'username': 'reader', 'password': 'Public-Test-Reader-493!', 'next': target})
        self.assertEqual(response['Location'], target)
        self.assertEqual(len(self.client.get('/search-index.json').json()), 2)
        self.client.post('/accounts/logout/')
        self.assertEqual(len(self.client.get('/search-index.json').json()), 1)
        self.assertEqual(self.client.get('/content/' + self.articles[True, False].slug + '.md').status_code, 404)
        response = self.client.post('/accounts/login/', {'username': 'reader', 'password': 'Public-Test-Reader-493!', 'next': '//evil.example/'})
        self.assertEqual(response['Location'], '/')
