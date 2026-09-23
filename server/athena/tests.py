import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .admin import since
from .forms import ArticleForm
from .models import ApiKey, Article, LoginAttempt


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
        for _ in range(10):
            self.assertEqual(self.client.post('/accounts/login/', {'username': 'missing', 'password': 'wrong'}).status_code, 200)
        self.assertEqual(self.client.post('/accounts/login/', {'username': 'missing', 'password': 'wrong'}).status_code, 429)

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
        for bad in ['[]', '{"published":"false"}', '{"tags":"wrong"}', '{"unexpected":"value"}']:
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

        data = {'username': 'reader2', 'first_name': 'Ana', 'last_name': '', 'email': '', 'role': 'admin', 'is_active': 'on'}
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

    def test_portal_sidebar(self):
        self.client.force_login(self.reader)
        sidebar = self.client.get('/_sidebar.md').content.decode()
        self.assertIn('[Mi cuenta](/accounts/profile/', sidebar)
        self.assertNotIn('Administrar Athena', sidebar)
        self.client.force_login(self.admin)
        self.assertIn('[Administrar Athena](/admin/', self.client.get('/_sidebar.md').content.decode())
        reader_links = ['<a href="/">Inicio</a>', '<a href="/#/guides">Guías</a>', '<a href="/#/content/contributing">Contribuir</a>',
                        '<a href="/accounts/profile/">Mi cuenta</a>', '<li class="active"><a href="/admin/" aria-current="true">Administrar Athena</a>']
        for path in ['/admin/', '/admin/auth/user/']:
            response = self.client.get(path)
            self.assertNotContains(response, 'id="nav-sidebar"')
            for link in reader_links + ['<h2 id="portal-sidebar-admin">Administrar</h2>', '>Artículos</a>', '>Claves de API</a>']:
                self.assertContains(response, link, html=False)
        self.assertContains(response, '<li class="active"><a href="/admin/auth/user/" aria-current="page">Usuarios</a>')
        self.assertContains(self.client.get('/admin/athena/article/add/'),
                            '<li class="active"><a href="/admin/athena/article/" aria-current="page">Artículos</a>')
        self.assertNotContains(self.client.get('/admin/auth/user/add/?_popup=1'), 'portal-sidebar')

    def test_relative_last_login(self):
        now = timezone.now()
        for delta, text in [(timedelta(minutes=20), 'hace 20 min'), (timedelta(hours=2), 'hace 2 h'),
                            (timedelta(days=1, hours=3), 'ayer'), (timedelta(days=40), 'hace 40 días')]:
            self.assertEqual(since(now - delta, now), text)
        self.assertEqual(since(None, now), 'nunca')
