import hashlib
import io
import json
import re
import tempfile
import zlib
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .admin import since
from .forms import ArticleForm, DirectoryUserForm
from .models import ApiKey, Article, Download, LoginAttempt
from .views import article_html, pdf_fetcher, sidebar_links


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class PortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('administrator', password='Correct-Horse-Example-483!')
        cls.reader = User.objects.create_user('reader', password='Reader-Example-9348!')
        cls.article = Article.objects.create(title='First guide', slug='first-guide', summary='Find this guide',
                                            author='Author', body='# First guide\n\n## Section\n\nSearchable text.', published=True)

    def key(self, user, scope):
        key = ApiKey(user=user, scope=scope, name='test')
        raw = key.issue()
        key.save()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + raw}, key

    def test_protected_content_and_removed_routes(self):
        for path in ['/', '/README.md', '/content/first-guide.md', '/search-index.json', '/catalog.json', '/pdf/first-guide.pdf']:
            self.assertEqual(self.client.get(path).status_code, 302, path)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get('/content/first-guide.md').status_code, 200)
        self.article.delete()
        self.assertEqual(self.client.get('/content/first-guide.md').status_code, 404)
        self.assertEqual(self.client.get('/content/domxpath.md').status_code, 404)
        self.assertEqual(self.client.get('/.secrets/admin-login.txt').status_code, 404)
        self.assertEqual(self.client.get('/assets/../server/athena/settings.py').status_code, 404)

    def test_reader_drafts_and_admin(self):
        self.article.published = False
        self.article.save()
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get('/content/first-guide.md').status_code, 404)
        self.assertEqual(self.client.get('/admin/athena/article/').status_code, 302)
        self.assertNotContains(self.client.get('/guides.md'), 'First guide')
        self.assertFalse(any(x.get('title') == 'First guide' for x in self.client.get('/search-index.json').json()))
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/content/first-guide.md'), 'Borrador')
        for path in ['/admin/', '/admin/auth/user/', '/admin/auth/user/add/?_popup=1', '/admin/athena/article/add/',
                     f'/admin/athena/article/{self.article.pk}/change/', '/admin/athena/apikey/add/']:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_csrf_and_login_throttling(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post('/accounts/login/', {'username': 'reader', 'password': 'wrong'}).status_code, 403)
        LoginAttempt.objects.all().delete()
        for path in ['/accounts/login/', '/admin/login/']:
            LoginAttempt.objects.all().delete()
            for _ in range(5):
                self.assertEqual(self.client.post(path, {'username': 'missing', 'password': 'wrong'}).status_code, 200)
            response = self.client.post(path, {'username': 'missing', 'password': 'wrong'})
            self.assertContains(response, 'Demasiados intentos. Intente de nuevo en 15 minutos.', status_code=429)
            self.assertContains(response, 'name="username"', status_code=429)  # The styled login form, not bare text.
            self.assertEqual(response['Retry-After'], '900')
        # The correct password is refused while locked.
        response = self.client.post('/accounts/login/', {'username': 'reader', 'password': 'Reader-Example-9348!'})
        self.assertEqual(response.status_code, 429)
        # The next lockout for the same keys doubles.
        LoginAttempt.objects.update(locked_until=timezone.now() - timedelta(seconds=1))
        for _ in range(5):
            self.assertEqual(self.client.post('/accounts/login/', {'username': 'missing', 'password': 'wrong'}).status_code, 200)
        self.assertContains(self.client.post('/accounts/login/', {'username': 'missing', 'password': 'x'}),
                            'Intente de nuevo en 30 minutos.', status_code=429)
        self.assertEqual(LoginAttempt.objects.filter(lockouts=2).count(), 2)  # The IP and the username.
        # Success clears the count and the lock but remembers earlier lockouts; old rows expire after a day.
        LoginAttempt.objects.update(locked_until=None, count=3)
        self.assertEqual(self.client.post('/accounts/login/', {'username': 'reader', 'password': 'Reader-Example-9348!'}).status_code, 302)
        self.assertTrue(LoginAttempt.objects.filter(count=0, locked_until=None, lockouts=2).exists())
        LoginAttempt.objects.update(started_at=timezone.now() - timedelta(hours=25))
        self.client.post('/accounts/login/', {'username': 'other', 'password': 'wrong'})
        self.assertEqual(set(LoginAttempt.objects.values_list('lockouts', flat=True)), {0})

    def test_api_permissions_and_revocation(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/v1/articles/').status_code, 401)
        headers, key = self.key(self.reader, 'read')
        self.assertEqual(self.client.get('/api/v1/articles/', **headers).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/articles/', '{}', content_type='application/json', **headers).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/users/', **headers).status_code, 403)
        self.reader.set_password('New-Reader-Example-483!')
        self.reader.save()
        self.assertEqual(self.client.get('/api/v1/articles/', **headers).status_code, 401)
        headers, key = self.key(self.reader, 'read')
        key.expires_at = timezone.now() - timedelta(seconds=1)
        key.save()
        self.assertEqual(self.client.get('/api/v1/articles/', **headers).status_code, 401)
        headers, key = self.key(self.reader, 'read')
        key.delete()
        self.assertEqual(self.client.get('/api/v1/articles/', **headers).status_code, 401)

    def test_api_discovery_me_and_docs(self):
        for path in ['/api/', '/api/v1/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(response.json()['docs'], '/api/docs/')
            self.assertEqual(response.json()['endpoints']['/api/v1/me/'], ['GET'])
        for path in ['/api/nope', '/api', '/api/users/users/?limit=1']:
            response = self.client.get(path)
            self.assertEqual((response.status_code, response['Content-Type']), (404, 'application/json'), path)
            self.assertEqual(response.json(), {'error': 'Not found. See /api/docs/.'})
        self.assertEqual(self.client.post('/api/users/tokens/provision/').status_code, 404)  # JSON, not a CSRF page.
        response = self.client.get('/api/v1/me/')
        self.assertEqual((response.status_code, response['WWW-Authenticate']), (401, 'Bearer'))
        self.assertEqual(response.json()['docs'], '/api/docs/')
        headers, key = self.key(self.reader, 'read')
        response = self.client.get('/api/v1/me/', **headers).json()
        self.assertEqual((response['user']['username'], response['key']['scope']), ('reader', 'read'))
        self.assertEqual(response['can'], {'read_articles': True, 'write_articles': False, 'manage_downloads': False, 'manage_users': False})
        self.assertEqual(self.client.post('/api/v1/articles/', '{}', content_type='application/json', **headers).json()['docs'], '/api/docs/')
        headers, key = self.key(self.admin, 'admin')
        response = self.client.get('/api/v1/me/', **headers).json()
        self.assertEqual(response['key']['expires_at'], key.expires_at.isoformat())
        self.assertEqual(response['can'], {'read_articles': True, 'write_articles': True, 'manage_downloads': True, 'manage_users': True})
        response = self.client.get('/api/docs/')
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'text/markdown; charset=utf-8'))
        self.assertContains(response, '## Quick start')
        self.assertEqual(self.client.get('/api.md').status_code, 302)
        self.client.force_login(self.reader)
        self.assertContains(self.client.get('/api.md'), '## Quick start')
        self.assertNotIn('API para agentes', self.client.get('/_sidebar.md').content.decode())
        self.client.force_login(self.admin)
        self.assertIn('  - [Administrar Athena](/admin/ ":ignore")\n  - [API para agentes](/api.md)',
                      self.client.get('/_sidebar.md').content.decode())

    def test_api_key_admin_shows_setup(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/admin/athena/apikey/'), 'Verifique una clave con <code>GET /api/v1/me/</code>')
        response = self.client.post('/admin/athena/apikey/add/', {
            'name': 'agent', 'user': self.admin.pk, 'scope': 'admin', 'expires_at_0': '2099-01-01', 'expires_at_1': '00:00:00'}, follow=True)
        self.assertContains(response, 'Clave creada')
        self.assertContains(response, 'export ATHENA_API_KEY=athena_')
        self.assertContains(response, 'curl -H "Authorization: Bearer $ATHENA_API_KEY" https://testserver/api/v1/me/')

    def test_article_crud_upload_search_and_conflicts(self):
        headers, _ = self.key(self.admin, 'articles')
        data = dict(title='New guide', slug='new-guide', summary='Fresh content', author='Team', body='# New guide',
                    tags=['Automation'], published=False)
        response = self.client.post('/api/v1/articles/', json.dumps(data), content_type='application/json', **headers)
        self.assertEqual(response.status_code, 201, response.content)
        url = '/api/v1/articles/new-guide/'
        self.assertEqual(self.client.patch(url, '{"published":true}', content_type='application/json', **headers).status_code, 412)
        response = self.client.patch(url, '{"published":true}', content_type='application/json',
                                     HTTP_IF_MATCH=response['ETag'], **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()['pdf_only'])
        response = self.client.patch(url, '{"pdf_only":true}', content_type='application/json',
                                     HTTP_IF_MATCH=response['ETag'], **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['pdf_only'] and Article.objects.get(slug='new-guide').pdf_only)
        self.assertTrue(self.client.get(url, **headers).json()['published'])
        self.client.force_login(self.reader)
        self.assertContains(self.client.get('/guides.md'), 'New guide')
        self.assertTrue(any(x.get('title') == 'New guide' for x in self.client.get('/search-index.json').json()))
        response = self.client.post(url + 'markdown/', {'file': SimpleUploadedFile('article.md', b'# Imported\n\nContent')},
                                    HTTP_IF_MATCH=response['ETag'], **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('Imported', response.json()['body'])
        etag = response['ETag']
        response = self.client.post(url + 'pdf/', {'file': SimpleUploadedFile('bad.pdf', b'not a pdf')}, HTTP_IF_MATCH=etag, **headers)
        self.assertEqual(response.status_code, 400)
        response = self.client.post(url + 'pdf/', {'file': SimpleUploadedFile('guide.pdf', b'%PDF-1.4\n%%EOF')}, HTTP_IF_MATCH=etag, **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get('/pdf/new-guide.pdf').status_code, 200)
        self.assertIn('sandbox', self.client.get('/pdf/new-guide.pdf')['Content-Security-Policy'])
        self.assertEqual(self.client.get('/pdf/new-guide.pdf')['X-Frame-Options'], 'SAMEORIGIN')
        self.assertTrue(self.client.get('/pdf/new-guide.pdf')['Content-Disposition'].startswith('inline;'))
        self.assertTrue(self.client.get('/pdf/new-guide.pdf?download=1')['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(self.client.delete(url, HTTP_IF_MATCH=response['ETag'], **headers).status_code, 204)
        self.assertEqual(self.client.get('/pdf/new-guide.pdf').status_code, 404)

    def test_user_crud_password_reset_and_self_protection(self):
        headers, _ = self.key(self.admin, 'admin')
        response = self.client.post('/api/v1/users/', json.dumps({'username': 'newreader', 'password': 'A-new-Password-5193!'}),
                                    content_type='application/json', **headers)
        self.assertEqual(response.status_code, 201, response.content)
        url = f'/api/v1/users/{response.json()["id"]}/'
        response = self.client.patch(url, json.dumps({'username': 'renamed', 'password': 'Second-Password-3492!'}),
                                     content_type='application/json', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.client.login(username='renamed', password='Second-Password-3492!'))
        self.assertEqual(self.client.delete(url, **headers).status_code, 204)
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(self.client.delete(f'/api/v1/users/{self.admin.pk}/', **headers).status_code, 400)
        self.assertEqual(self.client.patch(f'/api/v1/users/{self.admin.pk}/', '{"admin":false}',
                                           content_type='application/json', **headers).status_code, 400)

    def test_upload_form_and_input_validation(self):
        form = ArticleForm({'title': 'PDF guide', 'slug': 'pdf-guide', 'kind': 'guide', 'author': 'Team',
                            'summary': 'PDF only', 'date': '2026-09-15', 'tags': 'One, Two'},
                           {'pdf_file': SimpleUploadedFile('guide.pdf', b'%PDF-1.4\n%%EOF')})
        self.assertTrue(form.is_valid(), form.errors)
        article = form.save()
        self.assertEqual(article.tags, ['One', 'Two'])
        headers, _ = self.key(self.admin, 'articles')
        for bad in ['[]', '{"published":"false"}', '{"pdf_only":"true"}', '{"tags":"wrong"}', '{"unexpected":"value"}']:
            self.assertEqual(self.client.post('/api/v1/articles/', bad, content_type='application/json', **headers).status_code, 400)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/admin/'), 'athena/admin.css')

    def test_user_directory(self):
        url = '/admin/auth/user/'
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(url).status_code, 302)
        User.objects.create_user('staff', password='Staff-Example-7215!', is_staff=True)
        self.client.force_login(User.objects.get(username='staff'))
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertContains(response, 'administrator<small>ahora</small><span class="pill gold">Admin</span>')
        self.assertContains(response, 'reader<small>ahora</small><span class="pill">Lector</span>')
        self.assertContains(response, 'title="No puedes eliminar tu propia cuenta"')
        self.assertNotContains(response, f'/admin/auth/user/{self.admin.pk}/delete/')
        self.assertRedirects(self.client.get(f'/admin/auth/user/{self.reader.pk}/change/'), f'{url}?user={self.reader.pk}')
        self.assertRedirects(self.client.get('/admin/auth/user/add/'), f'{url}?new=1')

        self.reader.email = 'reader@example.com'
        self.reader.save()
        response = self.client.get(f'{url}?user={self.reader.pk}')
        self.assertContains(response, 'value="reader@example.com"')
        self.assertContains(response, f'href="?user={self.reader.pk}" aria-current="true"')
        self.assertContains(response, f'/admin/auth/user/{self.reader.pk}/delete/')
        self.assertContains(response, f'/admin/auth/user/{self.reader.pk}/password/')
        self.assertContains(response, '0 claves de API')
        self.assertEqual(self.client.get(f'{url}?user=999').status_code, 404)

        data = {'username': 'reader2', 'first_name': 'Ana', 'last_name': '', 'email': '', 'role': 'admin',
                'edits': ['articles', 'downloads', 'users'], 'is_active': 'on'}
        response = self.client.post(f'{url}?user={self.reader.pk}', data, follow=True)
        self.assertRedirects(response, f'{url}?user={self.reader.pk}')
        self.assertContains(response, 'Usuario guardado.')
        self.reader.refresh_from_db()
        self.assertEqual((self.reader.username, self.reader.is_staff, self.reader.is_superuser), ('reader2', True, True))

        data = {'username': 'administrator', 'role': 'reader', 'is_active': 'on'}
        response = self.client.post(f'{url}?user={self.admin.pk}', data)
        self.assertContains(response, 'No puede quitar su propio acceso de administrador.')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

        data = {'username': 'nueva', 'password1': 'Fresh-Reader-Pass-8824!', 'password2': 'mismatch',
                'role': 'reader', 'is_active': 'on'}
        self.assertEqual(self.client.post(f'{url}?new=1', data).status_code, 200)
        data['password2'] = data['password1']
        response = self.client.post(f'{url}?new=1', data)
        created = User.objects.get(username='nueva')
        self.assertRedirects(response, f'{url}?user={created.pk}')
        self.assertFalse(created.is_staff or created.is_superuser)
        self.assertTrue(Client().login(username='nueva', password='Fresh-Reader-Pass-8824!'))
        self.assertEqual(self.client.get(f'/admin/athena/apikey/?user__id__exact={created.pk}').status_code, 200)

    def directory_admin(self, username, edits):
        form = DirectoryUserForm({'username': username, 'role': 'admin', 'edits': edits, 'is_active': 'on'},
                                 instance=User.objects.create_user(username, password='Staff-Example-7215!'), actor=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_new_article_button_on_guides_for_editors(self):
        self.client.force_login(self.reader)
        self.assertNotContains(self.client.get('/guides.md'), 'Nuevo artículo')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/guides.md'), '<a class="copy-page" href="/admin/athena/article/add/">')
        self.assertNotContains(self.client.get('/tools.md'), 'Nuevo artículo')

    def test_article_tools_edit_and_export_links(self):
        export = '<a class="copy-page copy-page--ghost" href="/content/first-guide.pdf" download>'
        self.client.force_login(self.reader)
        body = self.client.get('/content/first-guide.md').content.decode()
        self.assertIn(f'\n\n<div class="article-tools">{export}', body)
        self.assertNotIn('Editar artículo', body)
        self.client.force_login(self.admin)
        edit = f'<a class="copy-page copy-page--ghost" href="/admin/athena/article/{self.article.pk}/change/">'
        self.assertRegex(self.client.get('/content/first-guide.md').content.decode(),
                         rf'\n<div class="article-tools">{re.escape(edit)}.*Editar artículo</span></a>{re.escape(export)}.*</div>\n$')
        Article.objects.filter(pk=self.article.pk).update(pdf_only=True)
        body = self.client.get('/content/first-guide.md').content.decode()
        self.assertIn(edit, body)
        self.assertNotIn('Exportar PDF', body)
        self.client.force_login(self.reader)
        self.assertNotIn('article-tools', self.client.get('/content/first-guide.md').content.decode())

    def test_article_pdf_export(self):
        self.assertEqual(self.client.get('/content/first-guide.pdf').status_code, 302)
        self.client.force_login(self.reader)
        response = self.client.get('/content/first-guide.pdf')
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'application/pdf'))
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="first-guide.pdf"')
        self.assertTrue(response.content.startswith(b'%PDF'))
        # A reader route stays a web link, not an internal anchor of the PDF.
        Article.objects.filter(pk=self.article.pk).update(body='[Tools](#/tools)')
        pdf = self.client.get('/content/first-guide.pdf').content
        streams = [pdf] + [zlib.decompress(m[1]) for m in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', pdf, re.S)
                           if m[1][:1] == b'x']  # zlib streams; images may use other filters.
        self.assertTrue(any(b'/URI (http://testserver/#/tools)' in chunk for chunk in streams))
        self.assertEqual(self.client.get('/content/missing.pdf').status_code, 404)
        self.assertEqual(self.client.get('/content/first-guide.md').status_code, 200)  # The Markdown route still answers.
        Article.objects.filter(pk=self.article.pk).update(published=False, pdf_only=True)
        self.assertEqual(self.client.get('/content/first-guide.pdf').status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/content/first-guide.pdf').status_code, 200)

    def test_article_export_html(self):
        article = Article(title='T & co', slug='t', author='Ana <A>', published=True, body=(
            '# T\n\nIntro\n- one\n- two\n\n```xml\n<config href="x"/>\n```\n\n'
            '[a](#/content/x) [b](/content/x.md) [c](/content/x) [d](#/tools) [e](/pdf/x.pdf) [f](https://example.com/)'))
        html = article_html(article, 'https://athena.test')
        self.assertIn('<html lang="es">', html)
        self.assertIn('<title>T &amp; co</title><meta name="author" content="Ana &lt;A&gt;">', html)
        self.assertIn('<h1>T</h1>', html)
        self.assertIn('<p>Intro</p>\n<ul>\n<li>one</li>', html)
        self.assertIn('<pre><code class="language-xml">&lt;config href=&quot;x&quot;/&gt;', html)
        for label, href in [('a', 'https://athena.test/#/content/x'), ('b', 'https://athena.test/#/content/x'),
                            ('c', 'https://athena.test/#/content/x'), ('d', 'https://athena.test/#/tools'),
                            ('e', '/pdf/x.pdf'), ('f', 'https://example.com/')]:
            self.assertIn(f'<a href="{href}">{label}</a>', html)

    def test_pdf_fetcher_allowlist(self):
        from unittest import mock
        from weasyprint.urls import URLFetcher
        fetcher = pdf_fetcher()
        self.assertEqual(fetcher.fetch('data:text/plain,hi').read(), b'hi')
        with mock.patch.object(URLFetcher, 'fetch', return_value='fetched') as fetch:
            self.assertEqual(fetcher.fetch('https://raw.githubusercontent.com/o/r/main/a.png'), 'fetched')
            for url in ['file:///etc/passwd', 'http://169.254.169.254/', 'https://example.com/x.png',
                        'http://raw.githubusercontent.com/x', 'https://raw.githubusercontent.com.example.com/x',
                        'http://testserver/content/first-guide.md']:
                with self.assertRaises(ValueError, msg=url):
                    fetcher.fetch(url)
            fetch.assert_called_once()

    def test_admin_index_lists_last_activity(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/admin/'), 'Todavía no hay actividad')
        self.client.post('/admin/auth/user/?user=%s' % self.reader.pk,
                         {'username': 'reader', 'role': 'reader', 'edits': [], 'is_active': 'on', 'email': 'r@example.com'})
        page = self.client.get('/admin/')
        self.assertContains(page, 'Última actividad')
        self.assertContains(page, '<strong>administrator</strong> editó usuario · ahora')

    def test_partial_admin_cannot_escalate(self):
        manager = self.directory_admin('manager', ['users'])
        self.client.force_login(manager)
        directory = '/admin/auth/user/'
        self.assertEqual(self.client.get(directory).status_code, 200)
        # A superuser account is read-only for a partial administrator.
        page = self.client.get(directory + f'?user={self.admin.pk}')
        self.assertNotContains(page, 'name="_save"')
        self.assertNotContains(page, '>Guardar<')
        self.assertContains(page, 'todos los permisos')
        post = {'username': self.admin.username, 'role': 'reader', 'edits': [], 'is_active': 'on'}
        self.assertEqual(self.client.post(directory + f'?user={self.admin.pk}', post).status_code, 403)
        self.assertEqual(self.client.get(f'/admin/auth/user/{self.admin.pk}/delete/').status_code, 403)
        self.assertTrue(User.objects.get(pk=self.admin.pk).is_superuser)
        # Only the areas the actor holds can be granted, so a superuser can never be minted.
        post = {'username': 'reader', 'role': 'admin', 'edits': ['users', 'articles'], 'is_active': 'on'}
        response = self.client.post(directory + f'?user={self.reader.pk}', post)
        self.assertContains(response, 'que usted tiene')
        self.assertFalse(User.objects.get(pk=self.reader.pk).is_staff)
        post['edits'] = ['users']
        self.assertEqual(self.client.post(directory + f'?user={self.reader.pk}', post).status_code, 302)
        promoted = User.objects.get(pk=self.reader.pk)
        self.assertEqual((promoted.is_staff, promoted.is_superuser), (True, False))
        self.assertTrue(promoted.has_perm('auth.change_user'))
        self.assertFalse(promoted.has_perm('athena.change_article'))

    def test_directory_edit_permissions(self):
        self.article.published = False
        self.article.save()
        change = f'/admin/athena/article/{self.article.pk}/change/'
        data = {'title': 'Edited', 'kind': 'guide', 'summary': 'S', 'author': 'A', 'date': '2026-09-15', 'tags': '',
                'body': 'Body', 'status': '', 'url': '', 'download_file': ''}
        viewer = self.directory_admin('viewer', [])
        self.assertEqual((viewer.is_staff, viewer.is_superuser), (True, False))
        self.client.force_login(viewer)
        for path in ['/admin/', '/admin/athena/article/', change]:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertNotContains(self.client.get(change), 'name="_save"')
        page = self.client.get('/admin/athena/article/').content.decode()
        self.assertNotIn(f'{change}"', page.split('row-controls', 1)[1])
        self.assertNotIn('/delete/', page)
        self.assertEqual(self.client.post(change, data).status_code, 403)
        self.assertEqual(self.client.get('/content/first-guide.md').status_code, 404)  # No drafts.
        self.assertEqual(self.client.get('/admin/auth/user/').status_code, 403)
        self.assertIn('Administrador · Última sesión', self.client.get('/account.md').content.decode())
        self.assertIn('Administrar Athena', self.client.get('/_sidebar.md').content.decode())

        editor = self.directory_admin('editor', ['articles'])
        self.client.force_login(editor)
        self.assertEqual(self.client.post(change, data).status_code, 302)
        self.assertContains(self.client.get('/content/first-guide.md'), 'Borrador')
        self.assertContains(self.client.get('/admin/athena/article/'), f'/admin/athena/article/{self.article.pk}/delete/')
        self.assertEqual(self.client.get('/admin/athena/download/add/').status_code, 403)
        self.assertEqual(self.client.get('/admin/auth/user/').status_code, 403)
        self.assertEqual(self.client.post(f'/admin/auth/user/?user={editor.pk}',
                                          {'username': 'editor', 'role': 'admin', 'edits': ['articles', 'users'],
                                           'is_active': 'on'}).status_code, 403)

        full = self.directory_admin('full', ['articles', 'downloads', 'users'])
        self.assertTrue(full.is_superuser)
        self.assertFalse(full.user_permissions.exists())
        self.assertEqual(DirectoryUserForm(instance=full, actor=self.admin)['edits'].value(), ['articles', 'downloads', 'users'])
        form = DirectoryUserForm({'username': 'full', 'role': 'admin', 'edits': ['articles', 'users'], 'is_active': 'on'},
                                 instance=full, actor=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        full = User.objects.get(pk=form.save().pk)
        self.assertEqual((full.is_staff, full.is_superuser), (True, False))
        self.assertEqual(set(full.get_all_permissions()), {
            'athena.view_article', 'athena.view_download', 'athena.add_article', 'athena.change_article',
            'athena.delete_article', 'auth.add_user', 'auth.change_user', 'auth.delete_user', 'auth.view_user',
            'athena.add_apikey', 'athena.change_apikey', 'athena.delete_apikey', 'athena.view_apikey'})
        self.assertEqual(DirectoryUserForm(instance=full, actor=self.admin)['edits'].value(), ['articles', 'users'])
        self.client.force_login(full)
        self.assertEqual(self.client.get('/admin/auth/user/').status_code, 200)
        self.assertEqual(self.client.get('/admin/athena/apikey/').status_code, 200)
        form = DirectoryUserForm({'username': 'full', 'role': 'reader', 'edits': ['articles'], 'is_active': 'on'},
                                 instance=full, actor=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        full = User.objects.get(pk=form.save().pk)
        self.assertEqual((full.is_staff, full.is_superuser, full.user_permissions.count()), (False, False, 0))

        # The last superuser keeps user management through the form and the API.
        for edits in [['articles', 'downloads'], ['articles', 'downloads', 'users']]:
            form = DirectoryUserForm({'username': 'administrator', 'role': 'admin' if 'users' not in edits else 'reader',
                                      'edits': edits, 'is_active': 'on'}, instance=self.admin, actor=self.admin)
            self.assertFalse(form.is_valid())
            self.assertIn('No puede quitar su propio acceso de administrador.', form.non_field_errors())
        other = self.directory_admin('other', ['users'])
        form = DirectoryUserForm({'username': 'administrator', 'role': 'admin', 'edits': ['users'], 'is_active': 'on'},
                                 instance=self.admin, actor=other)
        self.assertTrue(form.is_valid(), form.errors)  # Another account can still manage users.
        other.is_active = False
        other.save()
        form = DirectoryUserForm({'username': 'administrator', 'role': 'admin', 'edits': ['articles'], 'is_active': 'on'},
                                 instance=self.admin, actor=viewer)
        self.assertFalse(form.is_valid())
        self.assertIn('Debe conservar al menos un administrador activo.', form.non_field_errors())
        headers, _ = self.key(self.admin, 'admin')
        response = self.client.patch(f'/api/v1/users/{self.admin.pk}/', '{"admin":false}',
                                     content_type='application/json', **headers)
        self.assertEqual(response.status_code, 400)
        # An API update that leaves admin unchanged keeps an administrator's edit areas.
        response = self.client.patch(f'/api/v1/users/{editor.pk}/', '{"email":"editor@example.com","admin":false}',
                                     content_type='application/json', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        editor = User.objects.get(pk=editor.pk)
        self.assertTrue(editor.is_staff and editor.has_perm('athena.change_article'))

    def test_portal_sidebar(self):
        self.client.force_login(self.reader)
        sidebar = self.client.get('/_sidebar.md').content.decode()
        self.assertTrue(sidebar.startswith('- Biblioteca\n  - [Inicio](/)\n'), sidebar)
        self.assertIn('- Participar\n  - [Contribuir](/content/contributing.md)\n', sidebar)
        self.assertIn('- Cuenta\n  - [Mi cuenta](/account.md)\n', sidebar)
        self.assertNotIn('Administración', sidebar)
        self.assertNotIn('Administrar Athena', sidebar)
        self.assertEqual([group for group, _ in sidebar_links(self.reader)], ['Biblioteca', 'Participar', 'Cuenta'])
        self.client.force_login(self.admin)
        self.assertTrue(self.client.get('/_sidebar.md').content.decode().endswith(
            '- Administración\n  - [Administrar Athena](/admin/ ":ignore")\n  - [API para agentes](/api.md)\n'))
        self.assertEqual(sidebar_links(self.admin), [
            ('Biblioteca', [('Inicio', '/'), ('Guías', '/#/guides'), ('Actualizaciones', '/#/updates'),
                            ('Herramientas', '/#/tools'), ('Descargas', '/#/downloads')]),
            ('Participar', [('Contribuir', '/#/content/contributing')]), ('Cuenta', [('Mi cuenta', '/#/account')]),
            ('Administración', [('Administrar Athena', '/admin/'), ('API para agentes', '/#/api')])])
        item = '<a class="rail-item" href="{}"{}><span class="rail-label">{}</span></a>'.format
        reader_links = [item('/', '', 'Inicio'), item('/#/guides', '', 'Guías'), item('/#/content/contributing', '', 'Contribuir'),
                        item('/#/account', '', 'Mi cuenta')]
        for path in ['/admin/', '/admin/auth/user/']:
            response = self.client.get(path)
            self.assertNotContains(response, 'id="nav-sidebar"')
            self.assertNotContains(response, '>Administrar</h2>')
            self.assertContains(response, '<script src="/assets/rail.js"></script>')
            for link in reader_links + ['>Artículos</span></a>', '>Claves de API</span></a>']:
                self.assertContains(response, link, html=False)
            page = response.content.decode()
            labels = re.findall(r'<h2 class="rail-group-label"[^>]*>([^<]+)</h2>', page)
            self.assertEqual(labels, ['Biblioteca', 'Participar', 'Cuenta', 'Administración'])
            admin_group = page[page.index('>Administración</h2>'):]
            self.assertLess(admin_group.index('>API para agentes</span>'), admin_group.index('>Artículos</span>'))
            self.assertEqual(page.count('aria-current="page"'), 1)
        self.assertContains(response, item('/admin/', '', 'Administrar Athena'))
        self.assertContains(response, item('/admin/auth/user/', ' aria-current="page"', 'Usuarios'))
        self.assertContains(self.client.get('/admin/'), item('/admin/', ' aria-current="page"', 'Administrar Athena'))
        self.assertContains(self.client.get('/admin/athena/article/add/'),
                            item('/admin/athena/article/', ' aria-current="page"', 'Artículos'))
        self.assertNotContains(self.client.get('/admin/auth/user/add/?_popup=1'), 'class="rail"')

    def test_changelist_uses_text_pills(self):
        Article.objects.create(title='Draft', slug='draft', summary='Draft', author='Author')
        self.client.force_login(self.admin)
        response = self.client.get('/admin/athena/article/')
        self.assertContains(response, '<span class="pill gold">Publicado</span>')
        self.assertContains(response, '<span class="pill off">Borrador</span>')
        self.assertNotContains(response, 'icon-yes.svg')
        self.assertNotContains(response, 'icon-no.svg')
        self.assertContains(response, '<title>Artículos · Athena</title>')

    def test_account_page(self):
        self.assertEqual(self.client.get('/account.md').status_code, 302)
        self.key(self.reader, 'read')
        self.key(self.admin, 'admin')
        ApiKey.objects.filter(user=self.admin).update(name='admin-key')
        self.client.force_login(self.reader)
        response = self.client.get('/account.md')
        self.assertEqual(response['Content-Type'], 'text/markdown; charset=utf-8')
        page = response.content.decode()
        self.assertTrue(page.startswith('# reader\n'), page)
        self.assertIn('Lector · Última sesión', page)
        self.assertIn('<td>test</td><td>Lectura</td>', page)
        self.assertNotIn('admin-key', page)  # Only the user's own keys.
        self.assertIn('Pida una clave a un administrador.', page)
        self.assertNotIn('/admin/', page)
        # Docsify injects this form; it posts normally with the token rendered here.
        self.assertRegex(page, r'<form method="post" action="/accounts/logout/"><input type="hidden" name="csrfmiddlewaretoken" value="\w+">')
        self.client.force_login(self.admin)
        page = self.client.get('/account.md').content.decode()
        self.assertIn('Administrador · Última sesión', page)
        self.assertIn('admin-key', page)
        self.assertIn('href="/admin/athena/apikey/add/">Crear clave</a>', page)
        for link in ['/admin/athena/article/', '/admin/athena/apikey/', '/admin/athena/download/', '/admin/auth/user/']:
            self.assertIn(f'href="{link}"', page)

    def test_account_redirects_and_password_pages(self):
        self.assertRedirects(self.client.get('/accounts/profile/'), '/#/account', fetch_redirect_response=False)
        self.assertNotContains(self.client.get('/accounts/login/'), 'class="rail"')
        self.client.force_login(self.reader)
        response = self.client.get('/accounts/password_change/')
        self.assertContains(response, 'class="rail"')
        self.assertContains(response, '<a class="rail-item" href="/#/account" aria-current="page">', html=False)
        response = self.client.post('/accounts/password_change/', {
            'old_password': 'Reader-Example-9348!', 'new_password1': 'Changed-Reader-Pass-5521!',
            'new_password2': 'Changed-Reader-Pass-5521!'})
        self.assertRedirects(response, '/#/account', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/account.md').status_code, 200)  # This session stays valid.

    def test_changelists_have_row_controls_and_hidden_actions(self):
        self.key(self.admin, 'read')
        key = ApiKey.objects.get()
        self.client.force_login(self.admin)
        for url, links in [
            ('/admin/athena/article/', ['/#/content/first-guide', f'/admin/athena/article/{self.article.pk}/change/',
                                        f'/admin/athena/article/{self.article.pk}/delete/']),
            ('/admin/athena/apikey/', [f'/admin/athena/apikey/{key.pk}/change/', f'/admin/athena/apikey/{key.pk}/delete/']),
        ]:
            response = self.client.get(url)
            page = response.content.decode()
            self.assertIn('<div class="row-controls">', page)
            for link in links:
                self.assertIn(f'href="{link}"', page)
            self.assertIn('athena/admin-list.js', page)
            # Django's action form is rendered only inside the hidden container that admin-list.js drives.
            hidden = page.index('<div class="bulk-source" hidden>')
            self.assertEqual(page.count('<select name="action"'), 1)
            self.assertLess(hidden, page.index('<select name="action"'))
            self.assertLess(page.index('<select name="action"'), page.index('<table id="result_list">'))
        self.assertNotContains(self.client.get(f'/admin/athena/article/{self.article.pk}/change/'), 'admin-list.js')
        response = self.client.get('/admin/athena/article/')
        self.assertContains(response, '<a class="site-brand" href="/">ATHENA</a>')  # Shown by CSS only without a visible rail.
        self.assertNotContains(response, 'ATHENA <span>')

    def test_relative_last_login(self):
        now = timezone.now()
        for delta, text in [(timedelta(minutes=20), 'hace 20 min'), (timedelta(hours=2), 'hace 2 h'),
                            (timedelta(days=1, hours=3), 'ayer'), (timedelta(days=40), 'hace 40 días')]:
            self.assertEqual(since(now - delta, now), text)
        self.assertEqual(since(None, now), 'nunca')


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class DownloadTests(TestCase):
    def setUp(self):
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(tempfile.TemporaryDirectory())))
        self.admin = User.objects.create_superuser('administrator', password='Correct-Horse-Example-483!')
        self.reader = User.objects.create_user('reader', password='Reader-Example-9348!')
        self.data = b'PK\x03\x04 framework bytes' * 1000
        self.item = Download.objects.create(title='Framework actual', section='framework',
                                            file=ContentFile(self.data, name='Plantilla A360+2024.zip'))

    def key(self, user, scope):
        key = ApiKey(user=user, scope=scope, name='test')
        raw = key.issue()
        key.save()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + raw}

    def test_download_requires_login_and_streams_the_file(self):
        self.assertEqual((self.item.slug, self.item.filename, self.item.size), ('plantilla-a3602024-zip', 'Plantilla A360+2024.zip', len(self.data)))
        url = '/downloads/' + self.item.slug
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.reader)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(response['Content-Length']), len(self.data))
        self.assertEqual(b''.join(response.streaming_content), self.data)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('Plantilla A360+2024.zip', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow, noarchive')
        self.assertEqual(self.item.sha256, hashlib.sha256(self.data).hexdigest())
        self.item.published = False
        self.item.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get('/downloads/missing').status_code, 404)
        # A second file with the same name gets its own slug.
        again = Download.objects.create(title='Copia', file=ContentFile(b'x', name='Plantilla A360+2024.zip'))
        self.assertEqual(again.slug, 'plantilla-a3602024-zip-2')

    def test_import_downloads_maps_folders_and_is_idempotent(self):
        source = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name in ['Export.CORE.zip', 'packages/Tool-1.0.jar', 'Ejercicios/ACME.zip', 'versiones anteriores/Old.zip',
                     'unknown/skip.zip', '.hidden/secret.zip']:
            (source / name).parent.mkdir(parents=True, exist_ok=True)
            (source / name).write_bytes(name.encode())
        out = io.StringIO()
        call_command('import_downloads', str(source), stdout=out, stderr=io.StringIO())
        self.assertIn('4 added, 0 already present, 1 ignored.', out.getvalue())
        sections = dict(Download.objects.exclude(pk=self.item.pk).values_list('title', 'section'))
        self.assertEqual(sections, {'Export.CORE.zip': 'framework', 'Tool-1.0.jar': 'packages',
                                    'ACME.zip': 'exercises', 'Old.zip': 'previous'})
        self.assertEqual(Download.objects.get(title='Old.zip').file.read(), b'versiones anteriores/Old.zip')
        out = io.StringIO()
        call_command('import_downloads', str(source), stdout=out, stderr=io.StringIO())
        self.assertIn('0 added, 4 already present, 1 ignored.', out.getvalue())
        self.assertEqual(Download.objects.count(), 5)

    def test_latest_framework_link_follows_new_uploads(self):
        url = '/downloads/framework/latest'
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.reader)
        self.assertIn('Plantilla A360+2024.zip', self.client.get(url)['Content-Disposition'])
        Download.objects.create(title='Anterior', section='previous', file=ContentFile(b'o', name='Older.zip'))
        newer = Download.objects.create(title='Nueva', section='framework', file=ContentFile(b'n', name='Framework-2.zip'))
        response = self.client.get(url)
        self.assertIn('Framework-2.zip', response['Content-Disposition'])
        self.assertEqual(b''.join(response.streaming_content), b'n')
        newer.published = False
        newer.save()
        self.assertIn('Plantilla A360+2024.zip', self.client.get(url)['Content-Disposition'])
        Download.objects.filter(section='framework').delete()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_downloads_page_search_and_navigation(self):
        Download.objects.create(title='Versión 2025', section='previous', file=ContentFile(b'old', name='old.zip'))
        Download.objects.create(title='Oculto', section='packages', published=False, file=ContentFile(b'h', name='hidden.jar'))
        self.assertEqual(self.client.get('/downloads.md').status_code, 302)
        self.client.force_login(self.reader)
        page = self.client.get('/downloads.md').content.decode()
        self.assertTrue(page.startswith('# Descargas\n\nArchivos aprobados. Solo para usuarios de Athena.'))
        self.assertIn('## Framework', page)
        self.assertIn('Enlace permanente a la última versión: <a href="http://testserver/downloads/framework/latest" download>', page)
        self.assertIn('## Versiones anteriores', page)
        self.assertNotIn('## Paquetes', page)  # Empty sections are omitted; unpublished files are hidden.
        self.assertNotIn('Oculto', page)
        self.assertIn(f'<a class="download-link" href="/downloads/{self.item.slug}" download>', page)
        self.assertIn('<code>Plantilla A360+2024.zip</code>', page)
        self.assertLess(page.index('## Framework'), page.index('## Versiones anteriores'))
        self.assertIn('<details class="download-archive"><summary>Mostrar 1 archivo</summary>', page)
        self.assertNotIn('target=', page)
        for old in ['/archive.md', '/packages.md']:
            self.assertRedirects(self.client.get(old), '/downloads.md', fetch_redirect_response=False)
        sidebar = self.client.get('/_sidebar.md').content.decode()
        self.assertIn('[Descargas](/downloads.md)', sidebar)
        self.assertNotIn('Archivo', sidebar)
        entries = [e for e in self.client.get('/search-index.json').json() if e['kind'] == 'download']
        self.assertEqual([(e['title'], e['section'], e['route']) for e in entries],
                         [('Framework actual', 'Framework', '/downloads/' + self.item.slug),
                          ('Versión 2025', 'Versiones anteriores', '/downloads/old-zip')])

    def test_downloads_page_filter(self):
        Download.objects.create(title='Versión 2025', section='previous', note='Solo lectura', file=ContentFile(b'old', name='old.zip'))
        self.client.force_login(self.reader)
        page = self.client.get('/downloads.md').content.decode()
        self.assertIn('<input id="download-filter" type="search" placeholder="Buscar archivo, sección o nota" autocomplete="off">', page)
        self.assertIn('<select id="download-section"><option value="">Todas</option><option value="framework">Framework</option>'
                      '<option value="previous">Versiones anteriores</option></select>', page)
        self.assertIn('<p id="download-count" class="result-count" aria-live="polite"></p>', page)
        self.assertIn('<section class="download-section" data-section="framework">', page)
        self.assertIn('<article class="catalog-item" data-search="Framework actual Plantilla A360+2024.zip Framework ">', page)
        self.assertIn('<article class="catalog-item" data-search="Versión 2025 old.zip Versiones anteriores Solo lectura">', page)
        self.assertIn('<p class="library-empty download-empty" hidden>No hay archivos que coincidan.</p>', page)
        self.assertLess(page.index('id="download-filter"'), page.index('## Framework'))
        Download.objects.all().delete()
        page = self.client.get('/downloads.md').content.decode()
        self.assertIn('Todavía no hay archivos publicados.', page)
        self.assertNotIn('download-filter', page)

    def test_download_admin_pages(self):
        self.client.force_login(self.admin)
        response = self.client.get('/admin/athena/download/')
        self.assertContains(response, '<span class="pill">Framework</span>')
        self.assertContains(response, f'href="/downloads/{self.item.slug}" title="Descargar"')
        self.assertContains(response, f'href="/admin/athena/download/{self.item.pk}/delete/" title="Eliminar"')
        self.item.published = False
        self.item.save()
        # The download view serves published files only, so the control is disabled.
        self.assertContains(self.client.get('/admin/athena/download/'), 'aria-disabled="true" title="Sin publicar: no se puede descargar"')
        self.assertContains(response, '<title>Descargas · Athena</title>')
        self.assertEqual(self.client.get('/admin/athena/download/add/').status_code, 200)
        self.assertContains(self.client.get(f'/admin/athena/download/{self.item.pk}/change/'), self.item.sha256)
        response = self.client.post('/admin/athena/download/add/', {
            'title': 'Paquete', 'section': 'packages', 'note': '', 'published': 'on',
            'file': SimpleUploadedFile('Tool 2.0.jar', b'jar bytes')})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Download.objects.get(title='Paquete').filename, 'Tool 2.0.jar')

    def test_download_api_scopes(self):
        url = '/api/v1/downloads/'
        read = self.key(self.reader, 'read')
        Download.objects.create(title='Oculto', published=False, file=ContentFile(b'h', name='hidden.jar'))
        self.assertEqual([d['title'] for d in self.client.get(url, **read).json()['results']], ['Framework actual'])
        upload = {'title': 'Nuevo', 'section': 'packages', 'file': SimpleUploadedFile('new.jar', b'new bytes')}
        self.assertEqual(self.client.post(url, upload, **read).status_code, 403)
        self.assertEqual(self.client.post(url, upload, **self.key(self.reader, 'articles')).status_code, 403)
        write = self.key(self.admin, 'articles')
        upload['file'].seek(0)
        self.assertEqual(self.client.post(url, {**upload, 'extra': 'x'}, **write).status_code, 400)
        upload['file'].seek(0)
        response = self.client.post(url, upload, **write)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['url'], '/downloads/new-jar')
        self.assertEqual(response.json()['size'], 9)
        self.assertEqual(len(self.client.get(url, **write).json()['results']), 3)
        self.assertEqual(self.client.delete(url + 'new-jar/', **read).status_code, 403)
        path = Download.objects.get(slug='new-jar').file.path
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(url + 'new-jar/', **write).status_code, 204)
        self.assertFalse(Path(path).exists())
        self.assertEqual(self.client.delete(url + 'new-jar/', **write).status_code, 404)


class RobotsTests(TestCase):
    def test_site_is_not_indexable(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Disallow: /', response.content)
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow, noarchive')
        self.assertEqual(self.client.get('/accounts/login/')['X-Robots-Tag'], 'noindex, nofollow, noarchive')

