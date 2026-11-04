import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from .forms import ArticleForm, permissions
from .images import create_image, signed_image_url
from .models import ApiKey, Article, visible_articles
from .test_html_articles import picture

SECRET = 'Texto secreto del informe'


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class RestrictedArticleTests(TestCase):
    """Usuarios seleccionados: only active superusers and listed users see the article, on every path."""

    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser('root')
        cls.editor = User.objects.create_user('editor', is_staff=True)  # Can edit articles, not listed.
        cls.editor.user_permissions.set(permissions(['athena.add_article', 'athena.change_article',
                                                     'athena.delete_article', 'athena.view_article']))
        cls.listed_editor = User.objects.create_user('listed-editor', is_staff=True)
        cls.listed_editor.user_permissions.set(permissions(['athena.add_article', 'athena.change_article',
                                                            'athena.view_article']))
        cls.reader = User.objects.create_user('reader')  # Signed in, not listed.
        cls.listed = User.objects.create_user('listed')

    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.tmp / 'media', DATA_DIR=self.tmp))
        self.only = create_image(picture(), self.root)      # Used only by restricted articles.
        self.shared = create_image(picture(), self.root)    # Used by a restricted and a public article.
        self.restricted = Article.objects.create(
            title='Informe privado', slug='informe-privado', kind='guide', summary='Resumen confidencial',
            author='Autor', body=f'# Informe privado\n\n{SECRET}\n\n![Solo]({self.only.get_absolute_url()})\n\n'
                                 f'![Compartida]({self.shared.get_absolute_url()})',
            published=True, is_restricted=True, pdf=b'%PDF-1.4\n%%EOF', pdf_name='informe.pdf')
        self.restricted.allowed_users.set([self.listed, self.listed_editor])
        self.html = Article.objects.create(
            title='Informe HTML', slug='informe-html', summary='Resumen HTML confidencial', author='Autor',
            format='html', published=True, is_restricted=True,
            body=f'<!doctype html><body><p>{SECRET} HTML</p><img src="{self.only.get_absolute_url()}"></body>')
        self.html.allowed_users.set([self.listed])
        self.public = Article.objects.create(
            title='Guía pública', slug='guia-publica', summary='Pública', author='Autor', published=True,
            is_public=True, body=f'# Guía pública\n\n![Compartida]({self.shared.get_absolute_url()})')

    def login(self, user):
        self.client.logout()
        if user:
            self.client.force_login(user)

    def key(self, user, scope='articles'):
        key = ApiKey(user=user, scope=scope, name='test')
        raw = key.issue()
        key.save()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + raw}

    @staticmethod
    def render_pdf(command, **kwargs):
        Path(command[-1]).write_bytes(b'%PDF-1.4\n%%EOF')

    def test_model_validation_and_defaults(self):
        article = Article(title='A', slug='a', summary='S', author='A', body='Text', is_public=True, is_restricted=True)
        with self.assertRaises(ValidationError) as error:
            article.full_clean()
        self.assertIn('is_public', error.exception.message_dict)
        plain = Article.objects.create(title='B', slug='b', summary='S', author='A', body='Text')
        self.assertEqual((plain.is_restricted, plain.access), (False, 'account'))
        self.assertEqual(self.public.access, 'public')
        self.assertEqual(self.restricted.access, 'restricted')

    def test_reader_paths_404_for_everyone_not_listed(self):
        paths = ['/content/informe-privado.md', '/content/informe-privado', '/pdf/informe-privado.pdf',
                 '/pdf/informe-privado.pdf?download=1', '/content/informe-privado.pdf',
                 '/article-html/informe-html/', '/article-html/informe-html/source']
        for user in [None, self.reader, self.editor]:
            self.login(user)
            for path in paths:
                with self.subTest(user=user, path=path), patch('athena.pdf_export.subprocess.run') as renderer:
                    self.assertEqual(self.client.get(path).status_code, 404)
                    renderer.assert_not_called()

    def test_listed_users_and_superusers_read_every_path(self):
        cases = [(self.listed, ['informe-privado', 'informe-html']), (self.root, ['informe-privado', 'informe-html']),
                 (self.listed_editor, ['informe-privado'])]
        for user, slugs in cases:
            self.login(user)
            for slug in slugs:
                paths = [f'/content/{slug}.md']
                paths += [f'/article-html/{slug}/', f'/article-html/{slug}/source'] if slug == 'informe-html' else [
                    f'/pdf/{slug}.pdf', f'/content/{slug}.pdf']
                for path in paths:
                    with self.subTest(user=user, path=path), patch('athena.pdf_export.subprocess.run', side_effect=self.render_pdf):
                        response = self.client.get(path)
                        self.assertEqual(response.status_code, 200)
                        if hasattr(response, 'streaming_content'):
                            response.close()
        self.login(self.listed_editor)
        self.assertEqual(self.client.get('/article-html/informe-html/').status_code, 404)

    def test_inactive_listed_user_and_drafts(self):
        self.listed.is_active = False
        self.listed.save()
        self.assertFalse(visible_articles(self.listed).filter(pk=self.restricted.pk).exists())
        self.listed.is_active = True
        self.listed.save()
        Article.objects.filter(pk=self.restricted.pk).update(published=False)
        self.login(self.listed)  # Listed reader without edit rights: drafts stay drafts.
        self.assertEqual(self.client.get('/content/informe-privado.md').status_code, 404)
        self.login(self.listed_editor)
        self.assertContains(self.client.get('/content/informe-privado.md'), 'Borrador')
        self.login(self.editor)
        self.assertEqual(self.client.get('/content/informe-privado.md').status_code, 404)

    def test_lists_home_and_search_index_hide_the_article(self):
        for user, visible in [(None, False), (self.reader, False), (self.editor, False), (self.listed, True),
                              (self.root, True)]:
            self.login(user)
            index = self.client.get('/search-index.json').content.decode()
            for text in ['Informe privado', 'Resumen confidencial', SECRET, 'informe-privado']:
                with self.subTest(user=user, text=text):
                    self.assertEqual(text in index, visible)
            for path in ['/guides.md', '/updates.md']:
                with self.subTest(user=user, path=path):
                    self.assertEqual('Informe privado' in self.client.get(path).content.decode(), visible)
            self.assertEqual('Resumen HTML confidencial' in index, visible)
        # The home page counts only readable articles.
        Article.objects.exclude(is_restricted=True).delete()
        self.login(self.reader)
        self.assertContains(self.client.get('/README.md'), 'Todavía no hay artículos publicados.')
        self.login(self.listed)
        self.assertNotContains(self.client.get('/README.md'), 'Todavía no hay artículos publicados.')

    def test_reader_notice_shows_a_count_and_no_names(self):
        self.login(self.listed)
        body = self.client.get('/content/informe-privado.md').content.decode()
        self.assertIn('# Informe privado\n\n<p class="article-access">Acceso restringido: 2 usuarios.</p>', body)
        self.assertNotIn('listed-editor', body)
        self.assertContains(self.client.get('/content/informe-html.md'), 'Acceso restringido: 1 usuario.</p>')
        self.assertNotContains(self.client.get('/content/guia-publica.md'), 'article-access')
        with patch('athena.pdf_export.subprocess.run', side_effect=self.render_pdf) as renderer:
            self.client.get('/content/informe-privado.pdf').close()
        self.assertNotIn('Acceso restringido', json.loads(renderer.call_args.kwargs['input'])['html'])

    def test_images_follow_the_restricted_rule(self):
        only, shared = self.only.get_absolute_url(), self.shared.get_absolute_url()
        for user in [None, self.reader, self.editor]:
            self.login(user)
            with self.subTest(user=user):
                self.assertEqual(self.client.get(only).status_code, 404)
                response = self.client.get(shared)  # The public article keeps its image public.
                self.assertEqual(response.status_code, 200)
                response.close()
        for user in [self.listed, self.root]:
            self.login(user)
            response = self.client.get(only)
            self.assertEqual(response.status_code, 200)
            response.close()
        # The image uploader (here root) is no exception for another editor: only listed users see it.
        Article.objects.filter(pk=self.public.pk).update(is_public=False)
        self.login(None)
        self.assertEqual(self.client.get(shared).status_code, 404)

    def test_signed_image_urls_only_for_allowed_viewers(self):
        self.login(self.listed)
        html = self.client.get('/article-html/informe-html/').content.decode()
        signed = re.search(r'src="(/article-images/[^"]+\?sig=[^"]+)"', html)[1]
        self.login(None)
        response = self.client.get(signed)  # The frame has no session; the signature is the grant.
        self.assertEqual(response.status_code, 200)
        response.close()
        # A non-listed editor's preview does not sign an image used only by a restricted article.
        body = f'<!doctype html><img src="{self.only.get_absolute_url()}">'
        self.login(self.editor)
        preview = self.client.post('/article-html-preview/', {'body': body}).content.decode()
        self.assertNotIn('?sig=', preview)
        # Not even when the editor uploaded it.
        self.only.uploader = self.editor
        self.only.save()
        preview = self.client.post('/article-html-preview/', {'body': body}).content.decode()
        self.assertNotIn('?sig=', preview)
        self.assertEqual(self.client.get(self.only.get_absolute_url()).status_code, 404)
        self.login(self.root)
        self.assertIn('?sig=', self.client.post('/article-html-preview/', {'body': body}).content.decode())
        self.assertTrue(signed_image_url(self.only.pk).startswith(self.only.get_absolute_url()))

    def test_editor_cannot_reuse_a_hidden_image_or_upload_into_the_article(self):
        form = ArticleForm({'title': 'Copia', 'slug': 'copia', 'kind': 'guide', 'summary': 'S', 'author': 'A',
                            'date': '2026-11-04', 'body': f'![Copia]({self.only.get_absolute_url()})',
                            'access': 'account'}, actor=self.editor)
        self.assertFalse(form.is_valid())
        self.assertIn('body', form.errors)
        self.login(self.editor)
        response = self.client.post('/article-images/upload/', {'article_id': self.restricted.pk, 'file': picture()})
        self.assertEqual(response.status_code, 404)

    def test_pdf_export_cache_is_rechecked_per_request(self):
        url = '/content/informe-privado.pdf'
        with patch('athena.pdf_export.subprocess.run', side_effect=self.render_pdf) as renderer:
            self.login(self.listed)
            self.assertTrue(b''.join(self.client.get(url).streaming_content).startswith(b'%PDF'))
            self.assertEqual(len(list((self.tmp / 'pdf-cache').glob('*.pdf'))), 1)
            for user in [None, self.reader, self.editor]:
                self.login(user)
                self.assertEqual(self.client.get(url).status_code, 404)
            self.login(self.root)
            self.assertTrue(b''.join(self.client.get(url).streaming_content).startswith(b'%PDF'))
            self.assertEqual(renderer.call_count, 1)
            # Removing a user from the list takes effect on the next request, cached file or not.
            self.restricted.allowed_users.remove(self.listed)
            self.login(self.listed)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.get('/pdf/informe-privado.pdf').status_code, 404)

    def test_admin_list_change_history_delete_and_view_on_site(self):
        content_type = ContentType.objects.get_for_model(Article).pk
        pk = self.restricted.pk
        LogEntry.objects.log_actions(user_id=self.root.pk, queryset=[self.restricted], action_flag=2, change_message='')
        self.login(self.editor)
        listing = self.client.get('/admin/athena/article/')
        self.assertContains(listing, 'Guía pública')
        self.assertNotContains(listing, 'Informe privado')
        self.assertNotContains(self.client.get('/admin/athena/article/?q=secreto'), 'Informe privado')
        for path in [f'/admin/athena/article/{pk}/change/', f'/admin/athena/article/{pk}/history/',
                     f'/admin/athena/article/{pk}/delete/']:
            with self.subTest(path=path):
                response = self.client.get(path, follow=True)
                self.assertNotContains(response, 'Informe privado')
                self.assertNotContains(response, SECRET)
        self.assertEqual(self.client.get(f'/admin/r/{content_type}/{pk}/').status_code, 404)
        self.assertNotContains(self.client.get('/admin/'), 'Informe privado')
        self.client.post('/admin/athena/article/', {'action': 'delete_selected', '_selected_action': [pk], 'post': 'yes'})
        self.client.post(f'/admin/athena/article/{pk}/delete/', {'post': 'yes'})
        self.assertTrue(Article.objects.filter(pk=pk).exists())
        self.login(self.root)
        listing = self.client.get('/admin/athena/article/')
        self.assertContains(listing, 'Restringido (2)')
        self.assertContains(self.client.get('/admin/'), 'Informe privado')
        self.assertEqual(self.client.get(f'/admin/r/{content_type}/{pk}/').status_code, 302)
        # A deleted restricted article leaves no title in Última actividad.
        self.client.post(f'/admin/athena/article/{pk}/delete/', {'post': 'yes'})
        self.assertFalse(Article.objects.filter(pk=pk).exists())
        self.login(self.editor)
        self.assertNotContains(self.client.get('/admin/'), 'Informe privado')

    def test_admin_access_control_and_picker(self):
        self.login(self.root)
        page = self.client.get(f'/admin/athena/article/{self.restricted.pk}/change/')
        self.assertContains(page, 'name="access"')
        for label in ['Público', 'Con cuenta', 'Usuarios seleccionados']:
            self.assertContains(page, label)
        self.assertContains(page, 'id="id_allowed_users"')
        self.assertContains(page, 'selectfilter')
        self.assertContains(page, 'data-access="restricted"')
        self.assertContains(page, 'Publicado · Restringido')
        form = page.context['adminform'].form
        data = {name: form[name].value() for name in ['title', 'kind', 'summary', 'author', 'date', 'body']}
        data.update(tags='', published='on', loaded_revision=form['loaded_revision'].value(), _continue='1',
                    access='restricted', allowed_users=[self.reader.pk])
        self.assertEqual(self.client.post(f'/admin/athena/article/{self.restricted.pk}/change/', data).status_code, 302)
        self.restricted.refresh_from_db()
        self.assertEqual(list(self.restricted.allowed_users.all()), [self.reader])
        # Switching to Público clears the list and the restriction.
        data.update(access='public', loaded_revision=self.restricted.updated_at.isoformat())
        self.assertEqual(self.client.post(f'/admin/athena/article/{self.restricted.pk}/change/', data).status_code, 302)
        self.restricted.refresh_from_db()
        self.assertEqual((self.restricted.access, self.restricted.allowed_users.count()), ('public', 0))

    def test_api_hides_the_article_from_non_listed_key_owners(self):
        for user in [self.reader, self.editor]:
            headers = self.key(user)
            with self.subTest(user=user):
                listing = self.client.get('/api/v1/articles/?q=secreto', **headers).json()
                self.assertEqual(listing['count'], 0)
                self.assertNotIn('informe-privado', json.dumps(self.client.get('/api/v1/articles/', **headers).json()))
                url = '/api/v1/articles/informe-privado/'
                etag = f'"{self.restricted.updated_at.isoformat()}"'
                self.assertEqual(self.client.get(url, **headers).status_code, 404)
                self.assertEqual(self.client.patch(url, '{"summary":"x"}', content_type='application/json',
                                                   HTTP_IF_MATCH=etag, **headers).status_code, 404 if user == self.editor else 403)
                self.assertEqual(self.client.delete(url, HTTP_IF_MATCH=etag, **headers).status_code,
                                 404 if user == self.editor else 403)
                self.assertEqual(self.client.get(url + 'pdf/', **headers).status_code, 404)
                self.assertEqual(self.client.post(url + 'markdown/', {'file': picture()}, HTTP_IF_MATCH=etag,
                                                  **headers).status_code, 404)
                self.assertEqual(self.client.get(f'/api/v1/article-images/{self.only.pk}/', **headers).status_code, 404)
        self.assertTrue(Article.objects.filter(pk=self.restricted.pk, summary='Resumen confidencial').exists())

    def test_api_access_fields_for_readers_and_editors(self):
        read = self.client.get('/api/v1/articles/informe-privado/', **self.key(self.listed, 'read')).json()
        self.assertEqual(read['access'], 'restricted')
        self.assertNotIn('allowed_users', read)
        root = self.key(self.root, 'admin')
        response = self.client.get('/api/v1/articles/informe-privado/', **root)
        self.assertEqual(response.json()['allowed_users'], ['listed', 'listed-editor'])
        self.assertEqual(self.client.get('/api/v1/articles/', **root).json()['results'][0].keys() >= {'access', 'allowed_users'}, True)
        self.assertEqual(self.client.get('/api/v1/articles/guia-publica/', **root).json()['access'], 'public')
        new = {'slug': 'nuevo', 'title': 'Nuevo', 'summary': 'S', 'author': 'A', 'body': 'Texto'}
        for extra, field in [({'access': 'restricted', 'allowed_users': ['nadie']}, 'allowed_users'),
                             ({'access': 'restricted', 'is_public': True}, 'is_public'),
                             ({'access': 'account', 'allowed_users': ['listed']}, 'allowed_users'),
                             ({'access': 'secret'}, 'access'),
                             ({'access': 'restricted', 'allowed_users': 'listed'}, 'allowed_users')]:
            with self.subTest(extra=extra):
                response = self.client.post('/api/v1/articles/', json.dumps({**new, **extra}),
                                            content_type='application/json', **root)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(field, response.json()['error'])
        response = self.client.post('/api/v1/articles/', json.dumps({**new, 'access': 'restricted', 'allowed_users': ['listed']}),
                                    content_type='application/json', **root)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.json()['access'], response.json()['allowed_users'], response.json()['is_public']),
                         ('restricted', ['listed'], False))
        url, etag = '/api/v1/articles/nuevo/', response['ETag']
        response = self.client.patch(url, '{"is_public": true}', content_type='application/json', HTTP_IF_MATCH=etag, **root)
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(url, '{"is_public": false}', content_type='application/json', HTTP_IF_MATCH=etag, **root)
        self.assertEqual(response.json()['access'], 'restricted')
        response = self.client.patch(url, '{"access": "account"}', content_type='application/json',
                                     HTTP_IF_MATCH=response['ETag'], **root)
        self.assertEqual((response.json()['access'], response.json()['allowed_users']), ('account', []))
        response = self.client.patch(url, '{"is_public": true}', content_type='application/json',
                                     HTTP_IF_MATCH=response['ETag'], **root)
        self.assertEqual(response.json()['access'], 'public')
        response = self.client.patch(url, '{"is_public": false}', content_type='application/json',
                                     HTTP_IF_MATCH=response['ETag'], **root)
        self.assertEqual(response.json()['access'], 'account')
