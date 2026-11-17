import hashlib
import io
import json
import os
import re
import tempfile
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import AnonymousUser, Permission, User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.http import FileResponse
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .admin import since
from .forms import ArticleForm, DirectoryUserForm, EMAIL_UNAVAILABLE
from .models import ApiKey, Article, Download, LoginAttempt, visible_articles
from .views import article_html, pdf_fetcher, sidebar_links

LIMA = timezone.get_fixed_timezone(-300)  # settings.TIME_ZONE has no daylight saving time.


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class PortalTests(TestCase):
    def setUp(self):
        self.enterContext(override_settings(DATA_DIR=Path(self.enterContext(tempfile.TemporaryDirectory()))))

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
        for path in ['/', '/README.md', '/search-index.json']:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get('/search-index.json').json(), [])
        for path in ['/content/first-guide.md', '/pdf/first-guide.pdf']:
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(self.client.get('/catalog.json').status_code, 302)
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
        self.assertEqual(self.client.get('/api.md').status_code, 404)
        self.client.force_login(self.reader)
        self.assertContains(self.client.get('/api.md'), '## Quick start')
        self.assertNotIn('API para agentes', self.client.get('/_sidebar.md').content.decode())
        self.client.force_login(self.admin)
        self.assertIn('  - [Administración](/admin/ ":ignore")\n  - [API para agentes](/api.md)',
                      self.client.get('/_sidebar.md').content.decode())

    def test_api_docs_stream_current_utf8_file_and_close_it(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        file = root / 'API.md'
        with override_settings(BASE_DIR=root):
            for body in ['# API\n\nGuía pública.\r\n', '# API\n\nVersión recién actualizada.\n']:
                content = body.encode('utf-8')
                file.write_bytes(content)
                os.utime(file, (1, 1))  # A document change must be visible even if the mtime stays the same.
                self.client.logout()
                self.assertEqual(self.client.get('/api.md').status_code, 404)
                for user, paths in [(None, ['/api/docs/']), (self.reader, ['/api/docs/', '/api.md'])]:
                    if user:
                        self.client.force_login(user)
                    for path in paths:
                        with self.subTest(path=path, body=body, user=user), \
                                patch('athena.views.FileResponse', wraps=FileResponse) as send_file:
                            response = self.client.get(path)
                            self.addCleanup(response.close)
                            self.assertEqual((response.status_code, response['Content-Type']),
                                             (200, 'text/markdown; charset=utf-8'))
                            stream = send_file.call_args.args[0]
                            self.assertFalse(stream.closed)
                            self.assertEqual(b''.join(response.streaming_content), content)
                            response.close()
                            self.assertTrue(stream.closed)
            file.unlink()
            for path in ['/api/docs/', '/api.md']:
                self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_api_key_admin_shows_setup(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/admin/athena/apikey/'), 'Verifique una clave con <code>GET /api/v1/me/</code>')
        response = self.client.post('/admin/athena/apikey/add/', {
            'name': 'agent', 'user': self.admin.pk, 'scope': 'admin', 'expires_at': '2099-01-01T00:00'}, follow=True)
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
        self.assertContains(self.client.get('/'), 'Biblioteca pública')
        self.assertEqual(self.client.get('/account.md').status_code, 404)
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
        self.assertContains(response, '<span class="pill gold">Administrador</span>')
        self.assertContains(response, '<span class="pill">Lector</span>')
        self.assertContains(response, 'title="No puedes eliminar tu propia cuenta"')
        self.assertNotContains(response, f'/admin/auth/user/{self.admin.pk}/delete/')
        self.assertRedirects(self.client.get(f'/admin/auth/user/{self.reader.pk}/change/'), f'{url}?user={self.reader.pk}')
        self.assertRedirects(self.client.get('/admin/auth/user/add/'), f'{url}?new=1')

        self.reader.email = 'reader@example.com'
        self.reader.save()
        response = self.client.get(f'{url}?user={self.reader.pk}')
        self.assertContains(response, 'value="reader@example.com"')
        self.assertContains(response, f'href="?user={self.reader.pk}#user-inspector" aria-current="true"')
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

    def test_directory_table_keeps_role_status_and_session_separate(self):
        inactive = User.objects.create_user('inactive-admin', first_name='María', last_name='Salas',
                                             is_staff=True, is_active=False)
        never = User.objects.create_user('long-' + 'u' * 145, first_name='Nombre largo', last_name='Apellido largo')
        self.client.force_login(self.admin)
        response = self.client.get(f'/admin/auth/user/?user={inactive.pk}')
        table = re.search(r'<table class="directory-table".*?</table>', response.content.decode(), re.S).group()
        for heading in ['Usuario', 'Acceso', 'Estado', 'Sesión']:
            self.assertRegex(table, rf'<th scope="col" aria-sort="(?:none|ascending)"><a class="directory-sort"[^>]+>{heading}<span')
        row = re.search(r'<tr[^>]*data-search="inactive-admin.*?</tr>', table, re.S).group()
        self.assertIn('class="is-selected"', row)
        self.assertIn(f'href="?user={inactive.pk}#user-inspector" aria-current="true"', row)
        self.assertIn('title="María Salas"', row)
        self.assertIn('<span class="pill gold">Editor</span>', row)  # Staff without superuser is an editor.
        self.assertIn('<span class="directory-status off">Inactiva</span>', row)
        self.assertIn('<td class="directory-session">nunca</td>', row)
        self.assertNotIn('Lector', row)
        self.assertIn(never.username, table)
        self.assertNotContains(response, 'Datos de ejemplo')
        self.assertNotContains(response, 'action-toggle')

    def test_directory_native_search_ignores_case_and_accents(self):
        self.reader.first_name, self.reader.last_name = 'María', 'Salas'
        self.reader.save()
        self.client.force_login(self.admin)
        url = f'/admin/auth/user/?user={self.reader.pk}'
        response = self.client.get(url, {'q': '  MARIA salas  ', 'user': self.reader.pk})
        self.assertEqual(response.context['query'], 'MARIA salas')
        matches = {user.pk: match for user, _, _, match in response.context['users']}
        self.assertEqual(matches, {self.admin.pk: False, self.reader.pk: True})
        self.assertContains(response, 'name="q" type="search" value="MARIA salas"')
        self.assertContains(response, '<p class="directory-empty" role="status" hidden>')
        response = self.client.get(url, {'q': 'Sin coincidencias', 'user': self.reader.pk})
        self.assertFalse(response.context['has_matches'])
        self.assertContains(response, '<p class="directory-empty" role="status">')
        self.assertTrue(all(not row[3] for row in response.context['users']))

    def test_directory_sorting_and_native_query_links(self):
        first = User.objects.create_user('Álvaro', first_name='María', is_staff=True, is_active=False)
        later = User.objects.create_user('beta', is_active=False)
        never = User.objects.create_user('zeta')
        self.client.force_login(self.admin)
        now = timezone.now()
        User.objects.filter(pk__in=[self.admin.pk, first.pk]).update(last_login=now - timedelta(days=2))
        User.objects.filter(pk=later.pk).update(last_login=now - timedelta(days=1))
        url = '/admin/auth/user/'
        expected = {
            'username': (['administrator', 'Álvaro', 'beta', 'reader', 'zeta'],
                         ['zeta', 'reader', 'beta', 'Álvaro', 'administrator']),
            'role': (['administrator', 'Álvaro', 'beta', 'reader', 'zeta'],
                     ['beta', 'reader', 'zeta', 'Álvaro', 'administrator']),
            'status': (['administrator', 'reader', 'zeta', 'Álvaro', 'beta'],
                       ['Álvaro', 'beta', 'administrator', 'reader', 'zeta']),
            'session': (['administrator', 'Álvaro', 'beta', 'reader', 'zeta'],
                        ['beta', 'administrator', 'Álvaro', 'reader', 'zeta']),
        }
        for field, orders in expected.items():
            for direction, order in zip(['asc', 'desc'], orders):
                with self.subTest(field=field, direction=direction):
                    response = self.client.get(url, {'user': first.pk, 'q': 'MARIA', 'sort': field, 'direction': direction})
                    self.assertEqual([user.username for user, *_ in response.context['users']], order)
                    self.assertEqual(response.context['selected'].pk, first.pk)
                    self.assertEqual([user.pk for user, *_, matches in response.context['users'] if matches], [first.pk])
                    for column, header in zip(expected, response.context['headers']):
                        params = parse_qs(urlsplit(header['url']).query)
                        self.assertEqual(params['user'], [str(first.pk)])
                        self.assertEqual(params['q'], ['MARIA'])
                        self.assertEqual(params['sort'], [column])
                        next_direction = 'desc' if field == column and direction == 'asc' else 'asc'
                        self.assertEqual(params['direction'], [next_direction])
                        state = ('ascending' if direction == 'asc' else 'descending') if field == column else 'none'
                        self.assertEqual(header['aria_sort'], state)
                    self.assertContains(response, f'name="sort" value="{field}"')
                    self.assertContains(response, f'name="direction" value="{direction}"')
        for invalid in [{'sort': 'email', 'direction': 'desc'}, {'sort': 'session', 'direction': 'drop table'},
                        {'sort': '-last_login', 'direction': 'asc'}]:
            response = self.client.get(url, invalid)
            self.assertEqual((response.context['sort'], response.context['direction']), ('username', 'asc'))
            self.assertEqual([user.username for user, *_ in response.context['users']], expected['username'][0])
        response = self.client.get(url, {'new': '1', 'sort': 'role', 'direction': 'desc', 'q': 'beta'})
        self.assertTrue(all(parse_qs(urlsplit(header['url']).query)['new'] == ['1'] for header in response.context['headers']))
        self.assertFalse(any('user' in parse_qs(urlsplit(header['url']).query) for header in response.context['headers']))

    def directory_admin(self, username, edits):
        form = DirectoryUserForm({'username': username, 'role': 'admin', 'edits': edits, 'is_active': 'on'},
                                 instance=User.objects.create_user(username, password='Staff-Example-7215!'), actor=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_directory_blocks_email_writes_and_preserves_existing_addresses(self):
        original_email = ' Existing@EXAMPLE.com '
        self.reader.email = original_email
        self.reader.save()
        self.client.force_login(self.admin)
        url = f'/admin/auth/user/?user={self.reader.pk}'
        response = self.client.get(url)
        self.assertTrue(response.context['form'].fields['email'].disabled)
        self.assertRegex(response.content.decode(), r'<input[^>]*name="email"[^>]*disabled')
        self.assertContains(response, f'title="{EMAIL_UNAVAILABLE}"')
        self.assertContains(response, 'placeholder="No disponible"')
        self.assertContains(response, '<p class="help">Servicio de correo no configurado.</p>')
        self.assertContains(response, f'<p class="visually-hidden" id="id_email_helptext">{EMAIL_UNAVAILABLE}</p>')
        self.assertContains(response, 'tabindex="0" role="group" aria-label="Correo electrónico no disponible" aria-describedby="id_email_helptext"')
        self.assertContains(response, 'id="id_email_helptext"')
        for posted in [{'email': 'malicious@example.com'}, {}]:
            with self.subTest(posted=posted):
                data = {'username': self.reader.username, 'first_name': 'Changed', 'role': 'reader', 'is_active': 'on', **posted}
                self.assertRedirects(self.client.post(url, data), url)
                self.reader.refresh_from_db()
                self.assertEqual((self.reader.email, self.reader.first_name), (original_email, 'Changed'))
        response = self.client.post('/admin/auth/user/?new=1', {'username': 'email-blocked-new',
            'email': 'malicious@example.com', 'role': 'reader', 'is_active': 'on',
            'password1': 'Fresh-Reader-Pass-8824!', 'password2': 'Fresh-Reader-Pass-8824!'})
        user = User.objects.get(username='email-blocked-new')
        self.assertRedirects(response, f'/admin/auth/user/?user={user.pk}')
        self.assertEqual((user.email, user.is_staff, user.is_superuser), ('', False, False))
        self.assertTrue(Client().login(username=user.username, password='Fresh-Reader-Pass-8824!'))

    def test_native_user_popups_block_email_writes_and_keep_manual_creation(self):
        original_email = ' Existing@EXAMPLE.com '
        self.reader.email = original_email
        self.reader.save()
        self.client.force_login(self.admin)
        url = f'/admin/auth/user/{self.reader.pk}/change/?_popup=1'
        response = self.client.get(url)
        self.assertTrue(response.context['adminform'].form.fields['email'].disabled)
        self.assertContains(response, f'title="{EMAIL_UNAVAILABLE}"')
        self.assertContains(response, 'tabindex="0" role="group" aria-label="Correo electrónico no disponible" aria-describedby="id_email_helptext"')
        self.assertContains(response, 'id="id_email_helptext"')
        joined = timezone.localtime(self.reader.date_joined)
        for posted in [{'email': 'malicious@example.com'}, {}]:
            with self.subTest(posted=posted):
                response = self.client.post(url, {'username': self.reader.username, 'first_name': 'Popup',
                    '_popup': '1', 'is_active': 'on', 'date_joined_0': joined.strftime('%Y-%m-%d'),
                    'date_joined_1': joined.strftime('%H:%M:%S'), **posted})
                self.assertEqual(response.status_code, 200)
                self.reader.refresh_from_db()
                self.assertEqual((self.reader.email, self.reader.first_name), (original_email, 'Popup'))
        url = '/admin/auth/user/add/?_popup=1'
        self.assertNotContains(self.client.get(url), 'name="email"')
        response = self.client.post(url, {'username': 'popup-email-blocked', 'email': 'malicious@example.com',
            '_popup': '1', 'usable_password': 'true', 'password1': 'Fresh-Reader-Pass-8824!', 'password2': 'Fresh-Reader-Pass-8824!'})
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='popup-email-blocked')
        self.assertEqual(user.email, '')
        self.assertTrue(Client().login(username=user.username, password='Fresh-Reader-Pass-8824!'))

    def test_user_api_rejects_email_changes_and_preserves_read_values(self):
        headers, _ = self.key(self.admin, 'admin')
        url = f'/api/v1/users/{self.reader.pk}/'
        self.reader.email = 'existing@example.com'
        self.reader.save()
        for value in ['new@example.com', '', None, [], {}]:
            with self.subTest(email=value):
                response = self.client.patch(url, json.dumps({'email': value, 'first_name': 'Rejected'}),
                                             content_type='application/json', **headers)
                self.assertEqual(response.status_code, 400)
                self.reader.refresh_from_db()
                self.assertEqual((self.reader.email, self.reader.first_name), ('existing@example.com', ''))
        for data in [{'first_name': 'API'}, {'email': 'existing@example.com', 'first_name': 'API'}]:
            response = self.client.patch(url, json.dumps(data), content_type='application/json', **headers)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual((response.json()['email'], response.json()['first_name']), ('existing@example.com', 'API'))
        self.assertEqual(self.client.get(url, **headers).json()['email'], 'existing@example.com')
        create = {'username': 'api-email-rejected', 'email': 'new@example.com', 'password': 'Fresh-Reader-Pass-8824!'}
        response = self.client.post('/api/v1/users/', json.dumps(create), content_type='application/json', **headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('temporarily unavailable', str(response.json()['error']))
        self.assertFalse(User.objects.filter(username='api-email-rejected').exists())
        for username, email in [('api-email-omitted', {}), ('api-email-blank', {'email': ''})]:
            response = self.client.post('/api/v1/users/', json.dumps({'username': username,
                'password': 'Fresh-Reader-Pass-8824!', **email}), content_type='application/json', **headers)
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(User.objects.get(username=username).email, '')
        self.assertEqual(self.client.post('/api/v1/users/invitations/', '{}', content_type='application/json', **headers).status_code, 404)

    def test_partial_admin_creates_reader_with_stale_edits(self):
        self.client.force_login(self.directory_admin('manager', ['users']))
        url = '/admin/auth/user/?new=1'
        panel = re.search(r'<form class="directory-panel".*?</form>', self.client.get(url).content.decode(), re.S).group()
        for name in ['password1', 'password2']:
            self.assertRegex(panel, rf'<input[^>]*type="password"[^>]*name="{name}"[^>]*autocomplete="new-password"[^>]*required')
        password = 'Fresh-Reader-Pass-8824!'
        response = self.client.post(url, {'username': 'new-reader', 'role': 'reader', 'is_active': 'on',
                                          'edits': ['articles', 'downloads', 'users'],
                                          'password1': password, 'password2': password})
        created = User.objects.get(username='new-reader')
        self.assertRedirects(response, f'/admin/auth/user/?user={created.pk}')
        self.assertEqual((created.is_staff, created.is_superuser, created.user_permissions.count()), (False, False, 0))
        login = Client()
        self.assertRedirects(login.post('/accounts/login/', {'username': created.username, 'password': password}), '/')
        self.assertEqual(int(login.session['_auth_user_id']), created.pk)

    def test_partial_admin_updates_and_demotes_readers_with_stale_edits(self):
        manager = self.directory_admin('manager', ['users'])
        editor = self.directory_admin('editor', ['articles', 'users'])
        self.client.force_login(manager)
        for user in [self.reader, editor]:
            with self.subTest(user=user.username):
                url = f'/admin/auth/user/?user={user.pk}'
                response = self.client.post(url, {'username': user.username, 'email': 'updated@example.com',
                                                  'role': 'reader', 'edits': ['articles', 'downloads', 'users'],
                                                  'is_active': 'on'})
                self.assertRedirects(response, url)
                user.refresh_from_db()
                self.assertEqual((user.email, user.is_staff, user.is_superuser, user.user_permissions.count()),
                                 ('', False, False, 0))
        response = self.client.post(f'/admin/auth/user/?user={manager.pk}', {
            'username': manager.username, 'role': 'reader', 'edits': ['articles', 'downloads', 'users'], 'is_active': 'on'})
        self.assertContains(response, 'No puede quitar su propio acceso de administrador.')
        manager.refresh_from_db()
        self.assertTrue(manager.is_staff and manager.has_perm('auth.change_user'))

    def test_partial_admin_reader_creation_validates_passwords(self):
        self.client.force_login(self.directory_admin('manager', ['users']))
        valid = 'Fresh-Reader-Pass-8824!'
        cases = [('', '', {'password1': 'required', 'password2': 'required'}),
                 ('', valid, {'password1': 'required'}), (valid, '', {'password2': 'required'}),
                 (valid, 'Other-Reader-Pass-3921!', {'password2': 'password_mismatch'}),
                 ('X7!aQ', 'X7!aQ', {'password2': 'password_too_short'})]
        count = User.objects.count()
        for first, second, errors in cases:
            with self.subTest(errors=errors):
                response = self.client.post('/admin/auth/user/?new=1', {
                    'username': 'invalid-reader', 'role': 'reader', 'is_active': 'on',
                    'edits': ['articles', 'downloads', 'users'], 'password1': first, 'password2': second})
                self.assertEqual(response.status_code, 200)
                actual = response.context['form'].errors.as_data()
                for field, code in errors.items():
                    self.assertIn(code, [error.code for error in actual[field]])
                self.assertFalse(response.context['form'].non_field_errors())
                self.assertEqual(User.objects.count(), count)
                self.assertFalse(User.objects.filter(username='invalid-reader').exists())
                for password in [first, second]:
                    if password:
                        self.assertNotContains(response, password)

    def test_directory_rejects_unknown_reader_edits(self):
        self.client.force_login(self.directory_admin('manager', ['users']))
        count = User.objects.count()
        for query in ['new=1', f'user={self.reader.pk}']:
            with self.subTest(query=query):
                response = self.client.post('/admin/auth/user/?' + query, {
                    'username': 'invalid-reader', 'role': 'reader', 'is_active': 'on', 'edits': ['unknown'],
                    'password1': 'Fresh-Reader-Pass-8824!', 'password2': 'Fresh-Reader-Pass-8824!'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['form'].errors.as_data()['edits'][0].code, 'invalid_choice')
                self.assertRegex(response.content.decode(),
                                 r'<div class="full directory-edit-area">\s*<ul class="errorlist"[^>]*>')
                self.assertEqual(User.objects.count(), count)
                self.assertFalse(User.objects.filter(username='invalid-reader').exists())
        self.reader.refresh_from_db()
        self.assertEqual((self.reader.username, self.reader.is_staff, self.reader.is_superuser), ('reader', False, False))

    def test_reader_has_one_persistent_header_search(self):
        for user in [None, self.reader]:
            if user:
                self.client.force_login(user)
            shell = self.client.get('/').content.decode()
            header = shell.split('<header class="reader-command">', 1)[1].split('</header>', 1)[0]
            self.assertEqual(shell.count('type="search"'), 1)
            self.assertIn('id="athena-search-input"', header)
            self.assertIn('class="command-crumbs"', header)
            self.assertIn('class="command-parent"', header)
            self.assertIn('id="search-scope"', header)
            self.assertIn('href="#main"', shell)
            for removed in ['rail-search-slot', 'rail-search-button', 'command-title', 'command-crumb"', 'athena-search-template']:
                self.assertNotIn(removed, shell)
            for route in ['/README.md', '/guides.md', '/tools.md', '/updates.md', '/search.md']:
                self.assertNotContains(self.client.get(route), 'type="search"')

    def test_article_breadcrumb_kind_comes_from_readable_article(self):
        self.client.force_login(self.reader)
        for kind in ['guide', 'tool', 'announcement', 'release', 'page']:
            self.article.kind = kind
            self.article.save()
            self.assertContains(self.client.get('/content/first-guide.md'), f'data-article-kind="{kind}"')

    def test_new_article_button_on_guides_for_editors(self):
        self.client.force_login(self.reader)
        self.assertNotContains(self.client.get('/guides.md'), 'Nuevo artículo')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/guides.md'), '<a class="copy-page" href="/admin/athena/article/add/">')
        self.assertNotContains(self.client.get('/tools.md'), 'Nuevo artículo')

    def test_guides_topic_source_preserves_fields_and_conditional_links(self):
        self.article.title = 'Álvaro <tema> & "guía"'
        self.article.author = 'Equipo <A>'
        self.article.summary = 'Resumen real & completo'
        self.article.tags = ['Café', 'A|B <tema> "x"', 'Helios', 'Seguridad']
        self.article.date = date(2025, 5, 5)
        self.article.status = 'stable'
        self.article.pdf_name = 'original.pdf'
        self.article.url = 'https://example.test/guide?a=1&b=2'
        self.article.download_file = 'approved.zip'
        self.article.is_public = True
        self.article.save()
        Article.objects.filter(pk=self.article.pk).update(updated_at=datetime(2026, 1, 2, 15, tzinfo=LIMA))
        public = self.client.get('/guides.md').content.decode()
        self.assertIn('<div class="guide-library"><div id="guide-source" hidden>', public)
        self.assertIn('<article class="guide-row"', public)
        self.assertIn('href="#/content/first-guide">Álvaro &lt;tema&gt; &amp; &quot;guía&quot;</a>', public)
        self.assertIn('id="guide-count" class="result-count" role="status"', public)
        self.assertNotIn('<input', public)
        self.assertNotIn('guide-tag', public)
        for removed in ['guide-index', 'guide-table', 'guide-scroll-hint', 'guide-view-switch', 'data-guide-view']:
            self.assertNotIn(removed, public)
        self.assertIn('Equipo &lt;A&gt;', public)
        self.assertIn('Resumen real &amp; completo', public)
        for tag in ['Café', 'A|B &lt;tema&gt; &quot;x&quot;', 'Helios', 'Seguridad']:
            self.assertIn(f'<span>{tag}</span>', public)
        self.assertIn('<time datetime="2026-01-02">2026-01-02</time>', public)
        self.assertNotIn('2025-05-05', public)
        self.assertIn('status-stable', public)
        self.assertIn('href="#/content/first-guide"', public)
        self.assertIn('href="/pdf/first-guide.pdf"', public)
        self.assertIn('href="https://example.test/guide?a=1&amp;b=2"', public)
        self.assertNotIn('Descarga aprobada', public)
        self.assertNotIn('Nuevo artículo', public)
        self.assertNotIn('<tema>', public)
        self.client.force_login(self.reader)
        private = self.client.get('/guides.md').content.decode()
        self.assertIn('href="#/downloads">Descarga aprobada', private)
        self.assertIn('<div id="guide-topics" class="guide-topics"></div>', private)
        self.assertNotIn('data-guide-view', private)
        self.assertIn('aria-live="polite" aria-atomic="true">1 resultado', private)
        self.reader.user_permissions.add(Permission.objects.get(codename='add_article', content_type__app_label='athena'))
        self.assertContains(self.client.get('/guides.md'), 'Nuevo artículo')

    def test_guides_keep_access_filters_draft_exclusion_and_server_date_order(self):
        public = Article.objects.create(title='Public guide', slug='public-guide', summary='Public summary',
                                        author='Public author', tags=['Public'], date=date(2020, 1, 1),
                                        published=True, is_public=True)
        self.article.date = date(2026, 12, 31)
        self.article.tags = ['Private tag']
        self.article.save()
        # The list follows the last update, not the editable article date.
        Article.objects.filter(pk=self.article.pk).update(updated_at=datetime(2026, 1, 1, 12, tzinfo=LIMA))
        Article.objects.filter(pk=public.pk).update(updated_at=datetime(2026, 10, 13, 12, tzinfo=LIMA))
        Article.objects.create(title='Public draft', slug='public-draft', summary='Draft summary', author='Draft author',
                               tags=['Draft tag'], published=False, is_public=True)
        Article.objects.create(title='Private draft', slug='private-draft', summary='Secret draft', author='Draft author',
                               tags=['Secret draft tag'], published=False)
        visitor = self.client.get('/guides.md').content.decode()
        self.assertIn(public.title, visitor)
        self.assertNotIn(self.article.title, visitor)
        self.assertNotIn('Private tag', visitor)
        self.assertNotIn('Draft tag', visitor)
        self.assertIn('>1 resultado</p>', visitor)
        for user in (self.reader, self.admin):
            self.client.force_login(user)
            page = self.client.get('/guides.md').content.decode()
            rows = re.findall(r'<article class="guide-row".*?</article>', page, re.S)
            self.assertEqual(len(rows), 2)
            self.assertIn('href="#/content/public-guide"', rows[0])
            self.assertIn('href="#/content/first-guide"', rows[1])
            self.assertIn('Private tag', page)
            self.assertNotIn('Public draft', page)
            self.assertNotIn('Private draft', page)
            self.assertNotIn('Secret draft tag', page)

    def test_tools_and_feed_show_and_order_by_last_update_in_site_time(self):
        Article.objects.filter(pk=self.article.pk).update(
            kind='announcement', date=date(2026, 12, 31), updated_at=datetime(2026, 9, 2, 3, tzinfo=timezone.get_fixed_timezone(0)))  # 2026-09-01 in Lima
        for slug, kind in [('old-tool', 'tool'), ('new-tool', 'tool'), ('b-release', 'release'), ('a-release', 'release')]:
            Article.objects.create(title=slug, slug=slug, kind=kind, summary='S', author='A', date=date(2020, 1, 1),
                                   published=True)
        stamps = {'old-tool': datetime(2026, 3, 1, 12, tzinfo=LIMA), 'new-tool': datetime(2026, 10, 20, 12, tzinfo=LIMA),
                  'a-release': datetime(2026, 10, 5, 12, tzinfo=LIMA), 'b-release': datetime(2026, 10, 5, 12, tzinfo=LIMA)}
        for slug, stamp in stamps.items():
            Article.objects.filter(slug=slug).update(updated_at=stamp)
        self.client.force_login(self.reader)
        tools = self.client.get('/tools.md').content.decode()
        self.assertLess(tools.index('#/content/new-tool'), tools.index('#/content/old-tool'))
        # One meta order: author, then 'Actualizado' and the date (the page names the type).
        self.assertIn('<small>A · Actualizado <time datetime="2026-10-20">2026-10-20</time></small>', tools)
        self.assertNotIn('2020-01-01', tools)
        updates = self.client.get('/updates.md').content.decode()
        slugs = re.findall(r'<h3><a href="#/content/([\w-]+)">', updates)
        self.assertEqual(slugs, ['a-release', 'b-release', 'first-guide'])  # Equal updates fall back to the title.
        self.assertIn('<time datetime="2026-09-01"><span class="day">01</span>', updates)
        # The date column is the only date: the meta line has type and author, and the title is the only link.
        self.assertNotIn('01/09/2026', updates)
        self.assertNotIn('>Leer</a>', updates)
        self.assertNotIn('<p class="post-actions">', updates)
        self.assertRegex(updates, r'(?s)<h2>Octubre 2026</h2>.*<h2>Septiembre 2026</h2>')
        self.assertNotIn('31/12/2026', updates)

    def test_guide_topics_do_not_change_tools_or_updates(self):
        Article.objects.create(title='Real tool', slug='real-tool', kind='tool', summary='Tool summary', author='Tool author',
                               status='alpha', url='https://example.test/tool', published=True, is_public=True)
        Article.objects.create(title='Real news', slug='real-news', kind='announcement', summary='S', author='A',
                               published=True, is_public=True)
        self.article.is_public = True
        self.article.save()
        for path in ['/tools.md', '/updates.md']:
            page = self.client.get(path).content.decode()
            self.assertIn('class="library-card', page)
            self.assertNotIn('guide-controls', page)
            self.assertNotIn('guide-table', page)
            self.assertNotIn('data-guide-view', page)
        tools = self.client.get('/tools.md').content.decode()
        self.assertIn('Real tool', tools)
        self.assertIn('status-alpha', tools)
        self.assertIn('https://example.test/tool', tools)
        updates = self.client.get('/updates.md').content.decode()
        self.assertIn('class="timeline"', updates)
        self.assertIn('Real news', updates)
        self.assertNotIn('First guide', updates)  # A guide is no update.
        self.assertNotIn('<p class="post-actions">', updates)  # No PDF, site or download: no action row.

    def test_placement_tag_is_no_chip_and_actions_only_with_a_target(self):
        Article.objects.create(title='Start tool', slug='start-tool', kind='tool', summary='S', author='A',
                               tags=['Primeros-Pasos', 'Colas'], published=True, is_public=True)
        Article.objects.create(title='Start news', slug='start-news', kind='announcement', summary='S', author='A',
                               tags=['primeros-pasos', 'Avisos'], url='https://example.test/news', published=True, is_public=True)
        tools = self.client.get('/tools.md').content.decode()
        self.assertIn('<p class="tag-list"><span>Colas</span></p>', tools)
        self.assertIn('data-search="Start tool A S Primeros-Pasos Colas"', tools)  # Matching still finds it.
        updates = self.client.get('/updates.md').content.decode()
        self.assertIn('<p class="tag-list"><span>Avisos</span></p>', updates)
        self.assertIn('<p class="post-actions"><a class="post-link" href="https://example.test/news" target="_blank" rel="noreferrer">Sitio oficial</a></p>', updates)

    def test_updates_are_announcements_and_releases_only(self):
        # Round 3 #26: one set for the page, its crumb and the search type (announcement, release).
        self.article.is_public = True
        self.article.save()  # A changed guide: still in Recientes, not on Actualizaciones.
        Article.objects.create(title='Big news', slug='big-news', kind='announcement', summary='S', author='A',
                               published=True, is_public=True)
        updates = self.client.get('/updates.md').content.decode()
        self.assertEqual(re.findall(r'<h3><a href="#/content/([\w-]+)">', updates), ['big-news'])
        home = self.client.get('/README.md').content.decode()
        self.assertIn('#/content/first-guide', home)
        self.assertIn('</div>\n\n<p><a href="#/updates">Ver anuncios y versiones</a></p>', home)
        self.assertIn('<span>Actualizaciones</span><p>Consulte anuncios y versiones.</p>', home)

    def test_placement_tag_is_no_guide_chip_and_not_in_pdf_meta(self):
        # Round 3 #2: the reader hides the placement tag; Guías chips and the PDF meta line must too.
        Article.objects.create(title='Start guide', slug='start-guide', kind='guide', summary='S', author='A',
                               tags=['Primeros-Pasos', 'Colas'], published=True, is_public=True)
        guides = self.client.get('/guides.md').content.decode()
        self.assertIn('<p class="tag-list"><span>Colas</span></p>', guides)
        self.assertIn('data-search="Start guide A S Primeros-Pasos Colas"', guides)  # Matching still finds it.
        html = article_html(Article(title='T', slug='t', author='Ana', body='# T', tags=['primeros-pasos', 'Colas']),
                            'https://athena.test')
        self.assertIn('<p class="article-meta">Guía · Ana · Colas</p>', html)

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

    @override_settings(PUBLIC_ORIGIN='http://testserver')
    def test_article_pdf_export(self):
        self.assertEqual(self.client.get('/content/first-guide.pdf').status_code, 404)
        self.client.force_login(self.reader)
        response = self.client.get('/content/first-guide.pdf')
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'application/pdf'))
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="first-guide.pdf"')
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))
        # A reader route stays a web link, not an internal anchor of the PDF.
        Article.objects.filter(pk=self.article.pk).update(body='[Tools](#/tools)')
        pdf = b''.join(self.client.get('/content/first-guide.pdf').streaming_content)
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
        # The four theme fonts are the only local files a PDF may read.
        from .views import FONT_DIR, PDF_FONTS
        self.assertEqual(sorted(path.name for path in PDF_FONTS.values()), sorted(path.name for path in FONT_DIR.glob('*.woff2')))
        for url in PDF_FONTS:
            self.assertTrue(fetcher.fetch(url).read().startswith(b'wOF2'), url)
        with self.assertRaises(ValueError):
            fetcher.fetch((FONT_DIR / 'LICENSE.md').as_uri())

    def test_admin_index_lists_last_activity(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/admin/'), 'Todavía no hay actividad')
        self.client.post('/admin/auth/user/?user=%s' % self.reader.pk,
                         {'username': 'reader', 'role': 'reader', 'edits': [], 'is_active': 'on'})
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
        for edits in [['users', 'articles'], ['users', 'downloads'], ['articles', 'downloads', 'users']]:
            with self.subTest(edits=edits):
                post = {'username': 'reader', 'role': 'admin', 'edits': edits, 'is_active': 'on'}
                response = self.client.post(directory + f'?user={self.reader.pk}', post)
                self.assertContains(response, 'que usted tiene')
                self.assertFalse(User.objects.get(pk=self.reader.pk).is_staff)
                response = self.client.post(directory + '?new=1', {
                    **post, 'username': 'denied-admin', 'password1': 'Fresh-Reader-Pass-8824!',
                    'password2': 'Fresh-Reader-Pass-8824!'})
                self.assertContains(response, 'que usted tiene')
                self.assertFalse(User.objects.filter(username='denied-admin').exists())
        post = {'username': 'reader', 'role': 'admin', 'edits': ['users'], 'is_active': 'on'}
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
                'body': 'Body', 'status': '', 'url': '', 'download_file': '',
                'loaded_revision': self.article.updated_at.isoformat()}
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
        self.assertIn('Editor · Última sesión', self.client.get('/account.md').content.decode())  # admin.role_label
        self.assertIn('[Administración](/admin/', self.client.get('/_sidebar.md').content.decode())

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
        response = self.client.patch(f'/api/v1/users/{editor.pk}/', '{"first_name":"Updated","admin":false}',
                                     content_type='application/json', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        editor = User.objects.get(pk=editor.pk)
        self.assertEqual(editor.first_name, 'Updated')
        self.assertTrue(editor.is_staff and editor.has_perm('athena.change_article'))

    def test_portal_sidebar(self):
        self.client.force_login(self.reader)
        sidebar = self.client.get('/_sidebar.md').content.decode()
        self.assertTrue(sidebar.startswith('- Biblioteca\n  - [Inicio](/)\n'), sidebar)
        self.assertIn('- Participar\n  - [Contribuir](/content/contributing.md)\n', sidebar)
        self.assertIn('- Cuenta\n  - [Mi cuenta](/account.md)\n', sidebar)
        self.assertNotIn('Administración', sidebar)
        self.assertNotIn('[Administración](/admin/', sidebar)
        self.assertEqual([group for group, _ in sidebar_links(self.reader)], ['Biblioteca', 'Participar', 'Cuenta'])
        self.client.force_login(self.admin)
        self.assertTrue(self.client.get('/_sidebar.md').content.decode().endswith(
            '- Administración\n  - [Administración](/admin/ ":ignore")\n  - [API para agentes](/api.md)\n'))
        self.assertEqual(sidebar_links(self.admin), [
            ('Biblioteca', [('Inicio', '/'), ('Guías', '/#/guides'), ('Actualizaciones', '/#/updates'),
                            ('Herramientas', '/#/tools'), ('Descargas', '/#/downloads')]),
            ('Participar', [('Contribuir', '/#/content/contributing')]), ('Cuenta', [('Mi cuenta', '/#/account')]),
            ('Administración', [('Administración', '/admin/'), ('API para agentes', '/#/api')])])
        item = '<a class="rail-item" href="{}"{}><span class="rail-label">{}</span></a>'.format
        reader_links = [item('/', '', 'Inicio'), item('/#/guides', '', 'Guías'), item('/#/content/contributing', '', 'Contribuir'),
                        item('/#/account', '', 'Mi cuenta')]
        for path in ['/admin/', '/admin/auth/user/', '/admin/athena/article/', '/admin/athena/apikey/', '/admin/athena/download/']:
            response = self.client.get(path)
            self.assertNotContains(response, 'id="header"')
            self.assertNotContains(response, 'id="user-tools"')
            self.assertNotContains(response, 'class="site-brand"')
            self.assertNotContains(response, 'id="nav-sidebar"')
            self.assertNotContains(response, '>Administrar</h2>')
            self.assertContains(response, '<script src="/assets/rail.js"></script>')
            for link in reader_links + [item('/#/api', '', 'API para agentes'), '>Artículos</span></a>', '>Claves de API</span></a>']:
                self.assertContains(response, link, html=False)
            page = response.content.decode()
            labels = re.findall(r'<p class="rail-group-label"[^>]*>([^<]+)</p>', page)
            self.assertEqual(labels, ['Biblioteca', 'Participar', 'Cuenta', 'Administración'])
            admin_group = page[page.index('>Administración</p>'):]
            self.assertLess(admin_group.index('>API para agentes</span>'), admin_group.index('>Artículos</span>'))
            self.assertEqual(page.count('aria-current="page"'), 1)
        self.assertContains(response, item('/admin/', '', 'Administración'))
        self.assertContains(self.client.get('/admin/auth/user/'), item('/admin/auth/user/', ' aria-current="page"', 'Usuarios'))
        self.assertContains(self.client.get('/admin/'), item('/admin/', ' aria-current="page"', 'Administración'))
        self.assertContains(self.client.get('/admin/athena/article/add/'),
                            item('/admin/athena/article/', ' aria-current="page"', 'Artículos'))
        self.assertNotContains(self.client.get('/admin/auth/user/add/?_popup=1'), 'class="rail"')
        response = Client().get('/admin/login/')
        self.assertContains(response, 'id="header"')
        self.assertContains(response, '<a class="site-brand" href="/">ATHENA</a>')
        self.assertContains(response, '<a class="site-section" href="/admin/">Administración</a>')

    def test_sidebar_uses_feed_label_for_spanish_and_english(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / 'dist').mkdir()
        sidebar = root / 'dist/_sidebar.md'
        with override_settings(BASE_DIR=root):
            for label in ['Actualizaciones', 'Updates']:
                with self.subTest(label=label), patch('athena.views._sidebar_cache', (None, [])):
                    sidebar.write_text(f'- [Inicio](/)\n- [{label}](/updates.md "Feed timeline")\n'
                                       '- [Updates guide](/content/updates-guide.md)\n', encoding='utf-8')
                    self.client.force_login(self.reader)
                    reader = self.client.get('/_sidebar.md')
                    self.assertContains(reader, '[Actualizaciones](/updates.md "Feed timeline")')
                    self.assertNotContains(reader, '[Updates](/updates.md')
                    self.assertContains(reader, '[Updates guide](/content/updates-guide.md)')
                    self.assertIn(('Actualizaciones', '/#/updates'), dict(sidebar_links(self.admin))['Biblioteca'])
                    self.client.force_login(self.admin)
                    admin = self.client.get('/admin/')
                    self.assertContains(admin, '<a class="rail-item" href="/#/updates"><span class="rail-label">Actualizaciones</span></a>')
                    self.assertNotContains(admin, '>Updates</span>')

    def test_changelist_uses_text_pills(self):
        Article.objects.create(title='Draft', slug='draft', summary='Draft', author='Author')
        self.client.force_login(self.admin)
        response = self.client.get('/admin/athena/article/')
        self.assertContains(response, '<span class="pill">Publicado</span>')
        self.assertContains(response, '<span class="pill warn">Borrador</span>')
        self.assertNotContains(response, 'icon-yes.svg')
        self.assertNotContains(response, 'icon-no.svg')
        self.assertContains(response, '<title>Artículos · Athena</title>')

    def test_account_page(self):
        self.assertEqual(self.client.get('/account.md').status_code, 404)
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
        self.assertRegex(page, r'<td data-sort-value="\d{4}-\d{2}-\d{2}T[^"]+">\d{2}/\d{2}/\d{4}</td>')
        self.assertNotIn('admin-key', page)  # Only the user's own keys.
        self.assertIn('Pida una clave a un administrador.', page)
        self.assertIn('<h2>Mis claves de API</h2>\n<p>Una clave de API permite que un script o un agente use Athena con su cuenta. '
                      'No la necesita para leer guías ni descargar archivos.</p>', page)
        self.assertNotIn('/admin/', page)
        # Docsify injects this form; it posts normally with the token rendered here.
        self.assertRegex(page, r'<form method="post" action="/accounts/logout/"><input type="hidden" name="csrfmiddlewaretoken" value="\w+">')
        self.client.force_login(self.admin)
        page = self.client.get('/account.md').content.decode()
        self.assertIn('Administrador · Última sesión', page)
        self.assertIn('href="/accounts/password_change/">Cambiar contraseña</a>', page)
        self.assertIn('admin-key', page)
        self.assertIn('href="/admin/athena/apikey/add/">Crear clave</a>', page)
        for link in ['/admin/athena/article/', '/admin/athena/apikey/', '/admin/athena/download/', '/admin/auth/user/']:
            self.assertIn(f'href="{link}"', page)
        self.assertIn('<a class="account-button" href="/#/api">API para agentes</a>', page)  # The page's one name.
        self.assertIn('<div class="account-grid">', page)
        # A reader without keys: one sentence (what a key is for, who gives one) in the narrow panel.
        ApiKey.objects.filter(user=self.reader).delete()
        self.client.force_login(self.reader)
        page = self.client.get('/account.md').content.decode()
        self.assertIn('<div class="account-grid no-keys">', page)
        self.assertIn('<h2>Mis claves de API</h2>\n<p>Una clave de API permite que un script o un agente use Athena con su '
                      'cuenta; la entrega un administrador.</p>\n', page)
        self.assertNotIn('Pida una clave', page)

    def test_account_logout_requires_post_and_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin)
        page = strict.get('/account.md').content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="(\w+)"', page)[1]
        self.assertEqual(strict.get('/accounts/logout/').status_code, 405)
        self.assertEqual(strict.post('/accounts/logout/').status_code, 403)
        self.assertEqual(strict.post('/accounts/logout/', {'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertEqual(strict.get('/account.md').status_code, 404)

    def test_account_redirects_and_password_pages(self):
        self.assertRedirects(self.client.get('/accounts/profile/'), '/#/account', fetch_redirect_response=False)
        self.assertNotContains(self.client.get('/accounts/login/'), 'class="rail"')
        self.client.force_login(self.reader)
        response = self.client.get('/accounts/password_change/')
        self.assertContains(response, 'class="rail"')
        self.assertContains(response, '<a class="rail-item" href="/#/account" aria-current="page">', html=False)
        # The reader's crumb row, and plain labels without Django's colon.
        self.assertContains(response, '<div class="command-crumbs"><a href="/">Athena</a><span aria-hidden="true">›</span><a href="/#/account">Mi cuenta</a>'
                                      '<span aria-hidden="true">›</span><span aria-current="page">Cambiar contraseña</span></div>', html=False)
        for field, label in [('old_password', 'Contraseña actual'), ('new_password1', 'Contraseña nueva'),
                             ('new_password2', 'Repita la contraseña nueva')]:
            self.assertContains(response, f'<label for="id_{field}">{label}</label>', html=False)
        self.assertNotContains(response, ':</label>')
        self.assertNotContains(self.client.get('/accounts/login/'), 'command-crumbs')
        # The reader's command bar: a nav for the crumbs and a search field that reaches the reader search route.
        self.assertContains(response, '<header class="account-command reader-command">', html=False)
        self.assertContains(response, '<nav class="command-lead" aria-label="Ruta de navegación">', html=False)
        self.assertContains(response, '<form class="search athena-search" role="search" action="/" method="get">', html=False)
        self.assertContains(response, 'name="q" type="search"', html=False)
        self.assertRedirects(self.client.get('/', {'q': ' cola & pagos '}), '/#/search?q=cola%20%26%20pagos',
                             fetch_redirect_response=False)
        self.assertEqual(self.client.get('/', {'q': ' '}).status_code, 200)  # An empty search opens the reader.
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
        self.assertNotContains(response, '<a class="site-brand" href="/">ATHENA</a>')
        self.assertNotContains(response, 'ATHENA <span>')

    def test_api_key_expiry_is_one_native_field_in_the_site_zone(self):
        from django import forms
        self.client.force_login(self.admin)
        page = self.client.get('/admin/athena/apikey/add/').content.decode()
        self.assertRegex(page, r'<label[^>]* for="id_expires_at"[^>]*>Vence')
        self.assertRegex(page, r'<input type="datetime-local" name="expires_at" value="\d{4}-\d\d-\d\dT\d\d:\d\d"')
        for gone in ['expires_at_0', 'calendarlink', 'clocklink', 'add_id_user', 'change_id_user', 'view_id_user']:
            self.assertNotIn(gone, page)
        old = forms.SplitDateTimeField().clean(['2099-01-01', '00:00:00'])  # The split widget's parsing.
        self.client.post('/admin/athena/apikey/add/', {'name': 'zone', 'user': self.admin.pk, 'scope': 'read',
                                                       'expires_at': '2099-01-01T00:00'})
        key = ApiKey.objects.get(name='zone')
        self.assertEqual(key.expires_at, old)
        self.assertEqual(key.expires_at, datetime(2099, 1, 1, tzinfo=LIMA))
        response = self.client.post(f'/admin/athena/apikey/{key.pk}/change/', {'name': 'zone', 'expires_at': ''})
        self.assertContains(response, 'Este campo es obligatorio.')
        past = self.client.post(f'/admin/athena/apikey/{key.pk}/change/', {'name': 'zone', 'expires_at': '2020-01-01T08:30'})
        self.assertEqual(past.status_code, 302)
        key.refresh_from_db()
        self.assertEqual(key.expires_at, datetime(2020, 1, 1, 8, 30, tzinfo=LIMA))

    def test_admin_pages_have_h1_and_administracion_root(self):
        self.client.force_login(self.admin)
        key = ApiKey.objects.create(user=self.admin, name='crumbs', digest='d' * 64, password_digest='p' * 64)
        root = '<a href="/admin/">Administración</a>'
        for path in ['/admin/athena/article/', '/admin/athena/apikey/add/', f'/admin/athena/apikey/{key.pk}/change/',
                     f'/admin/athena/article/{self.article.pk}/delete/', f'/admin/athena/article/{self.article.pk}/history/',
                     '/admin/athena/', f'/admin/auth/user/{self.reader.pk}/password/']:
            page = self.client.get(path).content.decode()
            self.assertIn(root, page, path)
            self.assertNotIn('>Inicio</a>', page, path)
            self.assertEqual(page.count('<h1'), 1, path)
        delete = self.client.get(f'/admin/athena/article/{self.article.pk}/delete/')
        self.assertContains(delete, '<h1>Eliminar «First guide»</h1>', html=True)
        edit = self.client.get(f'/admin/athena/article/{self.article.pk}/change/')
        self.assertContains(edit, '<h1 class="visually-hidden">Editar artículo: First guide</h1>', html=True)
        self.assertContains(self.client.get('/admin/athena/article/add/'), '<h1 class="visually-hidden">Nuevo artículo</h1>', html=True)
        self.assertNotContains(edit, '<script>')  # The admin CSP allows no inline script.
        self.assertContains(edit, 'data-pane="source">Editar</button>')

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
        self.assertEqual(self.client.get('/downloads.md').status_code, 404)
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
        self.assertEqual([(e['title'], e['section'], e['route'], e['prose']) for e in entries],
                         [('Framework actual', 'Framework', '/downloads/' + self.item.slug, self.item.note),
                          ('Versión 2025', 'Versiones anteriores', '/downloads/old-zip', '')])

    def test_downloads_page_filter(self):
        Download.objects.create(title='Versión 2025', section='previous', note='Solo lectura', file=ContentFile(b'old', name='old.zip'))
        self.client.force_login(self.reader)
        page = self.client.get('/downloads.md').content.decode()
        self.assertNotIn('<input', page)
        self.assertIn('<select id="download-section"><option value="">Todas</option><option value="framework">Framework</option>'
                      '<option value="previous">Versiones anteriores</option></select>', page)
        self.assertIn('<p id="download-count" class="result-count" role="status" aria-live="polite" aria-atomic="true"></p>', page)
        self.assertIn('<section class="download-section" data-section="framework">', page)
        self.assertIn('<article class="catalog-item" data-search="Framework actual Plantilla A360+2024.zip Framework ">', page)
        self.assertIn('<article class="catalog-item" data-search="Versión 2025 old.zip Versiones anteriores Solo lectura">', page)
        self.assertIn('<p class="library-empty download-empty" hidden>No hay archivos que coincidan.</p>', page)
        self.assertLess(page.index('id="download-section"'), page.index('## Framework'))
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

    def test_download_api_patch_moves_old_release_to_previous(self):
        from .views import current_framework
        url = f'/api/v1/downloads/{self.item.slug}/'
        write = self.key(self.admin, 'articles')

        def patch(data, headers=write, path=url):
            return self.client.patch(path, json.dumps(data), content_type='application/json', **headers)

        newer = Download.objects.create(title='Nueva', section='framework', file=ContentFile(b'n', name='Framework-2.zip'))
        older = Download.objects.create(title='Anterior', section='framework', file=ContentFile(b'o', name='Older.zip'))
        self.assertEqual(current_framework(), older)
        path, digest = self.item.file.path, self.item.sha256
        for bad in [{'file': 'other.zip'}, {'section': 'previous', 'published': False}, {'slug': 'x'},
                    {'filename': 'x.zip'}, {'sha256': '0' * 64}, {'extra': 'x'}, {}, {'section': 'archive'},
                    {'title': ''}, {'note': 5}]:
            with self.subTest(bad=bad), self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(patch(bad).status_code, 400)
        self.assertEqual(self.client.patch(url, 'section=previous', content_type='application/x-www-form-urlencoded',
                                           **write).status_code, 400)
        self.assertEqual(Download.objects.get(pk=self.item.pk).section, 'framework')
        self.assertEqual(patch({'section': 'previous'}, self.key(self.reader, 'read')).status_code, 403)
        self.assertEqual(patch({'section': 'previous'}, self.key(self.reader, 'articles')).status_code, 403)
        self.assertEqual(patch({'section': 'previous'}, path='/api/v1/downloads/missing/').status_code, 404)
        with self.captureOnCommitCallbacks(execute=True):
            response = patch({'section': 'previous'}, path=f'/api/v1/downloads/{older.slug}/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['section'], 'previous')
        self.assertEqual(current_framework(), newer)
        with self.captureOnCommitCallbacks(execute=True):
            response = patch({'title': 'Framework 2024', 'note': 'Versión anterior'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()['title'], response.json()['note'], response.json()['section']),
                         ('Framework 2024', 'Versión anterior', 'framework'))
        self.item.refresh_from_db()
        self.assertEqual((self.item.file.path, self.item.sha256), (path, digest))
        self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), digest)
        self.assertEqual(self.client.put(url, '{}', content_type='application/json', **write)['Allow'], 'PATCH, DELETE')


class RobotsTests(TestCase):
    def test_site_is_not_indexable(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Disallow: /', response.content)
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow, noarchive')
        self.assertEqual(self.client.get('/accounts/login/')['X-Robots-Tag'], 'noindex, nofollow, noarchive')


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class ReaderPageTests(TestCase):
    """Server-rendered reader pages: sign-in, unavailable, home Recientes, Descargas, search text and the PDF meta line."""

    @classmethod
    def setUpTestData(cls):
        cls.reader = User.objects.create_user('reader', password='Reader-Example-9348!')
        cls.listed = User.objects.create_user('listed')

    def setUp(self):
        self.enterContext(override_settings(DATA_DIR=Path(self.enterContext(tempfile.TemporaryDirectory()))))

    def test_sign_in_page_plain_heading_download_context_and_one_error_text(self):
        page = self.client.get('/accounts/login/')
        self.assertContains(page, '<h1>Ingresar</h1>', html=True)
        self.assertNotContains(page, 'El conocimiento del equipo')
        self.assertNotContains(page, 'Ingrese para descargar este archivo.')
        self.assertContains(self.client.get('/accounts/login/?next=/downloads/plantilla'), '<p>Ingrese para descargar este archivo.</p>', html=True)
        self.assertNotContains(self.client.get('/accounts/login/?next=/%23/guides'), 'Ingrese para descargar')
        # A visitor learns nothing about downloads: a real, a guessed and the latest link all read "este archivo".
        item = Download.objects.create(title='Plantilla <3.2>', section='framework', file=ContentFile(b'x', name='plantilla.zip'))
        for next_path in [f'/downloads/{item.slug}', '/downloads/framework/latest', '/downloads/no-existe']:
            page = self.client.get('/accounts/login/', {'next': next_path})
            self.assertContains(page, '<p>Ingrese para descargar este archivo.</p>', html=True)
            self.assertNotContains(page, 'Plantilla &lt;3.2&gt;')
        self.assertNotContains(self.client.get('/accounts/login/'), 'aria-invalid')
        # Wrong password, unknown user and an inactive account read the same; Django's own wording is gone.
        User.objects.create_user('inactive', password='Inactive-Example-1!', is_active=False)
        errors = []
        for username, password in [('reader', 'wrong'), ('nobody', 'wrong'), ('inactive', 'Inactive-Example-1!')]:
            response = self.client.post('/accounts/login/', {'username': username, 'password': password})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'introduzca')
            errors.append(re.search(r'<p class="errorlist nonfield".*?</p>', response.content.decode(), re.S)[0])
            # Both fields point to the error, which is announced when the page loads.
            for name in ['username', 'password']:
                self.assertRegex(response.content.decode(), rf'<input [^>]*aria-invalid="true" aria-describedby="login-error"[^>]*id="id_{name}"')
        self.assertEqual(errors, ['<p class="errorlist nonfield" id="login-error" role="alert">Usuario o contraseña incorrectos.</p>'] * 3)
        for _ in range(2):  # The fifth failure locks; the lockout keeps its own message (DL-0010).
            self.client.post('/accounts/login/', {'username': 'reader', 'password': 'wrong'})
        locked = self.client.post('/accounts/login/', {'username': 'reader', 'password': 'Reader-Example-9348!'})
        self.assertEqual(locked.status_code, 429)
        self.assertContains(locked, 'Demasiados intentos. Intente de nuevo en 15 minutos.', status_code=429)
        self.assertNotContains(locked, 'Usuario o contraseña incorrectos.', status_code=429)

    def test_unavailable_article_is_one_view_for_unknown_draft_and_restricted(self):
        Article.objects.create(title='Borrador', slug='borrador', summary='s', author='a', body='# Borrador')
        restricted = Article.objects.create(title='Privado', slug='privado', summary='s', author='a', body='# Privado',
                                            published=True, is_restricted=True)
        restricted.allowed_users.set([self.listed])
        for user in [None, self.reader]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            for suffix in ['.md', '.pdf']:
                responses = [self.client.get(f'/content/{slug}{suffix}') for slug in ['no-existe', 'borrador', 'privado']]
                self.assertEqual({(r.status_code, r.content) for r in responses}, {(404, responses[0].content)}, (user, suffix))
            page = self.client.get('/not-found.md').content.decode()
            self.assertIn('Puede que la dirección sea incorrecta o que el artículo tenga acceso limitado.', page)
            self.assertIn('<a class="post-link" href="#/search">Buscar en Athena</a><a class="post-link" href="#/">Ir al inicio</a>', page)
            # A visitor's one primary action is Ingresar, with one line on why.
            self.assertEqual('<p class="post-actions"><a class="download-link" href="/accounts/login/">Ingresar</a>' in page, user is None)
            self.assertEqual('Si tiene una cuenta, ingrese: puede que con ella tenga acceso.' in page, user is None)
            # The same line for unknown and restricted addresses, so it tells nothing about the article.
            self.assertEqual('Si necesita acceso, pídalo a un administrador de Athena.' in page, user is not None)
            self.assertNotIn('rivado', page)

    def test_home_recent_uses_the_library_access_rule_and_last_update(self):
        def make(slug, **fields):
            return Article.objects.create(title=slug, slug=slug, summary='s', author='a', body='# ' + slug,
                                          **{'published': True, **fields})
        old = make('old-public', is_public=True)
        make('private')
        make('draft', published=False, is_public=True)
        restricted = make('restricted', is_restricted=True, is_public=True)
        restricted.allowed_users.set([self.listed])
        for i in range(4):
            make(f'public-{i}', is_public=True)
        old.summary = 'edited'
        old.save()  # An edit moves the article to the top (DL-0022).

        def recent(user):
            self.client.logout()
            if user:
                self.client.force_login(user)
            page = self.client.get('/README.md').content.decode()
            return re.findall(r'<a class="guide-title" href="#/content/([^"]+)">', page)
        self.assertEqual(recent(None), ['old-public', 'public-3', 'public-2', 'public-1', 'public-0'])
        self.assertEqual(recent(self.reader), ['old-public', 'public-3', 'public-2', 'public-1', 'public-0'])
        Article.objects.filter(slug__startswith='public-').update(published=False)
        self.assertEqual(recent(None), ['old-public'])
        self.assertEqual(recent(self.reader), ['old-public', 'private'])
        self.assertEqual(recent(self.listed), ['old-public', 'restricted', 'private'])
        for user in [None, self.reader, self.listed]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            self.assertEqual(recent(user), [a.slug for a in visible_articles(user or AnonymousUser()).order_by('-updated_at', 'title')[:5]])
        page = self.client.get('/README.md').content.decode()
        self.assertIn('## Recientes', page)
        self.assertIn('</div>\n\n<p><a href="#/updates">Ver anuncios y versiones</a></p>', page)
        # One hero line for visitors and signed-in users.
        self.client.logout()
        self.assertIn('<p>Guías, herramientas y conocimiento compartido por el equipo.</p>', self.client.get('/README.md').content.decode())
        self.assertIn('<p>Guías, herramientas y conocimiento compartido por el equipo.</p>', page)  # page: signed in.
        self.assertNotIn('feed', page)
        self.assertIn(f'<small>Guía</small><small>Actualizado <time datetime="{timezone.localdate(old.updated_at).isoformat()}">', page)

    def test_home_first_steps_are_tagged_readable_articles_in_date_order(self):
        def home(user=None):
            self.client.logout()
            if user:
                self.client.force_login(user)
            return self.client.get('/README.md').content.decode()

        def first_steps(user=None):
            page = home(user)
            if '## Primeros pasos' not in page:
                return None
            self.assertLess(page.index('## Primeros pasos'), page.index('## Recientes'))
            part = page[page.index('## Primeros pasos'):page.index('## Recientes')]
            # The Recientes date cell in every row.
            self.assertEqual(part.count('<small>Actualizado <time datetime="'), part.count('class="guide-topic-row"'))
            return re.findall(r'<a class="guide-title" href="#/content/([^"]+)">', part)

        def make(slug, day, tags, **fields):
            return Article.objects.create(title=slug, slug=slug, summary='s', author='a', body='# ' + slug, tags=tags,
                                          date=date(2026, 1, day), **{'published': True, **fields})
        make('sin-etiqueta', 1, ['Colas'], is_public=True)
        self.assertIsNone(first_steps())  # Shown only when at least one article has the tag.
        make('mayusculas', 3, ['Primeros-Pasos'], is_public=True)
        make('primero', 2, ['primeros-pasos', 'Colas'], is_public=True)
        make('parecida', 1, ['no-primeros-pasos'], is_public=True)
        make('con-cuenta', 4, ['primeros-pasos'])
        make('borrador', 1, ['primeros-pasos'], published=False, is_public=True)
        make('restringido', 1, ['primeros-pasos'], is_restricted=True).allowed_users.set([self.listed])
        for day in range(5, 9):
            make(f'mas-{day}', day, ['primeros-pasos'])
        self.assertEqual(first_steps(), ['primero', 'mayusculas'])  # Visitors: public articles only.
        self.assertEqual(first_steps(self.reader), ['primero', 'mayusculas', 'con-cuenta', 'mas-5', 'mas-6'])  # At most 5.
        self.assertEqual(first_steps(self.listed), ['restringido', 'primero', 'mayusculas', 'con-cuenta', 'mas-5'])
        self.assertIn('<small>Guía</small><small>Actualizado <time datetime="', home(self.reader))  # Round 3 #4: the Recientes cell.

    def test_downloads_mark_the_framework_file_that_latest_serves(self):
        def make(title, section, minutes):
            item = Download.objects.create(title=title, section=section, file=ContentFile(b'x', name=title + '.zip'))
            Download.objects.filter(pk=item.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))
            return Download.objects.get(pk=item.pk)
        current, older = make('nuevo', 'framework', 1), make('anterior', 'framework', 5)
        package = make('paquete', 'packages', 1)
        Download.objects.filter(pk=make('oculto', 'framework', 0).pk).update(published=False)
        self.client.force_login(self.reader)
        page = self.client.get('/downloads.md').content.decode()
        hidden = '<span class="visually-hidden" lang="es"> {}</span>'  # Each link names its file for screen readers.
        self.assertIn(f'<p class="post-actions"><span class="status">Versión actual</span><a class="download-link" href="/downloads/{current.slug}" download>Descargar{hidden.format(current.title)}</a></p>', page)
        self.assertIn(f'<a class="account-button" href="/downloads/{older.slug}" download>Descargar{hidden.format(older.title)}</a>', page)
        self.assertIn(f'<a class="account-button" href="/downloads/{package.slug}" download>Descargar{hidden.format(package.title)}</a>', page)
        self.assertEqual(page.count('class="download-link"'), 1)  # One gold primary: only the current Framework file.
        self.assertEqual(page.count('Versión actual'), 1)  # Only Framework has a rule for "current".
        self.assertIn(f'<small>1\xa0byte · <time datetime="{timezone.localdate(current.created_at).isoformat()}">', page)
        self.assertIn(current.filename, self.client.get('/downloads/framework/latest')['Content-Disposition'])

    def test_search_text_drops_fences_escapes_and_controls(self):
        from .views import html_text, search_entry
        article = Article(title='T', slug='t', kind='guide', summary='s', author='a', published=True, updated_at=timezone.now(),
                          body='# T\n\nUse \\*todo\\* and `code` **bold**.\n\n```powershell\n$ruta = "C:\\\\Bots"\n```\n\n<!-- hidden -->\n')
        entry = search_entry(article)
        self.assertEqual(entry['text'], 'T Use *todo* and code bold. $ruta = "C:\\\\Bots"')
        self.assertEqual(entry['prose'], 'T Use *todo* and … bold.')  # Excerpts come from prose: no code, no paths.
        self.assertNotIn('powershell', json.dumps(entry))
        self.assertEqual(html_text('<p>Demo <button>Pantalla completa ▶</button><span aria-hidden="true">✓<b>x</b></span>'
                                   '<video controls>Sin video</video><img aria-hidden="true" alt=""> fin</p>'), 'Demo fin')

    def test_search_entry_sections_and_full_text(self):
        from .views import search_entry
        body = ('Intro con **negrita** y `código`.\n\n## Instalar\n\nPaso uno.\n\n```powershell\n$ruta = "C:\\\\Bots"\n```\n\n'
                '<span aria-hidden="true">oculto</span> visible\n\nDetalles\n--------\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n'
                '### Notas &amp; avisos\n\n> Cita final.')
        article = Article(title='Guía <A&B>', slug='guia', kind='guide', summary='s', author='a', body=body,
                          published=False, pdf_name='g.pdf', updated_at=timezone.now())
        entry = search_entry(article)
        # The text is the stored body; the sections follow the reader's body, with its title heading and PDF link.
        self.assertEqual(entry['text'], 'Intro con negrita y código. Instalar Paso uno. $ruta = "C:\\\\Bots" visible '
                                        'Detalles a b 1 2 Notas & avisos Cita final.')
        self.assertEqual(entry['prose'], 'Intro con negrita y …. Instalar Paso uno. visible Detalles a b 1 2 Notas & avisos Cita final.')
        self.assertEqual(entry['headings'], [
            {'level': 1, 'raw': 'Guía &lt;A&amp;B&gt;', 'title': 'Guía <A&B>', 'text': 'Intro con negrita y código.',
             'prose': 'Intro con negrita y ….'},
            {'level': 2, 'raw': 'Instalar', 'title': 'Instalar', 'text': 'Paso uno. $ruta = "C:\\\\Bots" visible',
             'prose': 'Paso uno. visible'},
            {'level': 2, 'raw': 'Detalles', 'title': 'Detalles', 'text': 'a b 1 2', 'prose': 'a b 1 2'},
            {'level': 3, 'raw': 'Notas &amp; avisos', 'title': 'Notas & avisos', 'text': 'Cita final. Abrir PDF original',
             'prose': 'Cita final. Abrir PDF original'}])

    def test_search_prose_skips_code_and_keeps_text_after_unclosed_code(self):
        from .views import html_texts
        self.assertEqual(html_texts('<p>a <code>x</code> b</p><pre><code>y</code></pre><p>c</p>'), ('a x b y c', 'a … b c'))  # "…" only for inline code
        # Hidden text stays out of both; code inside hidden text and hidden text inside code too.
        self.assertEqual(html_texts('<p>a <span aria-hidden="true">h <code>x</code></span> <code>y <button>z</button></code> b</p>'),
                         ('a y b', 'a … b'))
        # An HTML article with an unclosed code element loses no prose after it.
        self.assertEqual(html_texts('<p>a <code>x</p><h2>Later</h2><p>text</p>'), ('a x Later text', 'a x Later text'))
        self.assertEqual(html_texts('<pre>a <span aria-hidden="true">h</pre> b'), ('a h b', 'b'))

    def test_html_article_prose_is_paragraph_text_only(self):
        # Round 3 #6: card titles, section headings and link labels do not run into the excerpt; matching keeps them.
        body = ('<main><p class="intro">Demos grabadas.</p><h2 id="f">Finanzas</h2><div class="grid">'
                '<article class="card"><div class="body"><h3 id="c">Cobranzas</h3><p>Lee la cola de cuotas vencidas.</p>'
                '<p class="links"><a href="https://x.test/">Abrir demo</a></p></div></article>'
                '<article class="card"><div class="body"><h3 id="r">Registro</h3><p>Extrae los datos.</p></div></article>'
                '</div><ul><li>Uno <code>x</code></li></ul></main>')
        article = Article(title='Demos', slug='demos', kind='page', summary='s', author='a', format='html', body=body,
                          updated_at=timezone.now())
        from .views import search_entry
        entry = search_entry(article)
        self.assertEqual(entry['prose'], 'Demos grabadas. Lee la cola de cuotas vencidas. Extrae los datos. Uno …')
        self.assertEqual(entry['text'], 'Demos grabadas. Finanzas Cobranzas Lee la cola de cuotas vencidas. Abrir demo '
                                        'Registro Extrae los datos. Uno x')

    def test_search_text_keeps_text_after_an_unclosed_hidden_element(self):
        from .views import search_text
        for opener in ['<p aria-hidden="true">', '<button>', '<video src=a.mp4>', '<span aria-hidden="true">']:
            with self.subTest(opener=opener):
                text = search_text(opener + 'x\n\n## Later\n\ntext')
                self.assertIn('Later', text)
                self.assertIn('text', text)
        text = search_text('Antes <span aria-hidden="true">medio\n\n## Después\n\nfin')
        self.assertLess(text.index('Antes'), text.index('medio'))
        self.assertLess(text.index('medio'), text.index('Después'))
        self.assertLess(text.index('Después'), text.index('fin'))
        self.assertEqual(search_text('Antes <span aria-hidden="true">oculto</span> después\n\n## Later\n\ntext'),
                         'Antes después Later text')

    def test_pdf_export_has_the_reader_meta_line_and_address(self):
        from weasyprint import HTML
        article = Article(title='Guía', slug='guia', author='Ana & Co', published=True, body='# Guía\n\nTexto `x`\n\n## Parte',
                          tags=['Colas', 'Excel'], updated_at=datetime(2026, 9, 27, 15, tzinfo=LIMA))
        html = article_html(article, 'https://athena.test')
        # The reader's order and date ('27 sept 2026', as Intl writes it); tags as plain text.
        self.assertIn('<h1>Guía</h1>\n<p class="article-meta">Guía · Ana &amp; Co · Actualizado 27 sept 2026 · Colas, Excel</p>', html)
        article.author, article.tags, article.updated_at = '', [], datetime(2026, 11, 14, 15, tzinfo=LIMA)
        self.assertIn('<p class="article-meta">Guía · Actualizado 14 nov 2026</p>', article_html(article, 'https://athena.test'))
        self.assertIn('html { string-set: address "https://athena.test/#/content/guia · " }', html)
        self.assertIn('@bottom-left { content: string(title);', html)  # The title next to the address.
        self.assertIn('content: string(address) counter(page)', html)
        # Theme A: the local Inter and Cormorant files, and no colour outside the suite tokens.
        style = html[html.index('<style>'):html.index('</style>')]
        self.assertNotRegex(style[style.index('@page'):], r'#[0-9a-fA-F]{3}')
        fetcher, fetched = pdf_fetcher(), []
        fetch = fetcher.fetch
        fetcher.fetch = lambda url, headers=None: fetched.append(url) or fetch(url, headers)
        self.assertTrue(HTML(string=html, base_url='https://athena.test/content/guia.pdf', url_fetcher=fetcher).write_pdf().startswith(b'%PDF-'))
        self.assertTrue({'inter-latin.woff2', 'cormorant-300-700-latin.woff2'} <= {url.rsplit('/', 1)[-1] for url in fetched}, fetched)
