import json
import re
import tempfile
import time
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .forms import ArticleForm, permissions
from .images import check_references, collect_images, create_image, referenced_image_ids, sync_image_usage
from .models import ApiKey, Article, ManagedImage
from .views import html_text


def picture():
    data = BytesIO()
    Image.new('RGB', (3, 2), '#ffb900').save(data, format='PNG')
    return SimpleUploadedFile('image.png', data.getvalue(), content_type='image/png')


SANDBOX = 'sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox'


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class HtmlArticleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = User.objects.create_user('html-editor', is_staff=True)
        cls.editor.user_permissions.set(permissions(['athena.add_article', 'athena.change_article', 'athena.view_article']))
        cls.other = User.objects.create_user('other-editor', is_staff=True)
        cls.other.user_permissions.set(permissions(['athena.add_article', 'athena.change_article']))
        cls.add_only = User.objects.create_user('add-only', is_staff=True)
        cls.add_only.user_permissions.set(permissions(['athena.add_article', 'athena.view_article']))
        cls.reader = User.objects.create_user('reader')

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.root / 'media', DATA_DIR=self.root))
        self.image = create_image(picture(), self.editor)
        self.body = ('<!doctype html><html lang="es"><head><style>h2 { color: red }</style>'
                     '<script>const secret = "script text";</script></head><body>'
                     '<h2 id="uno">Galería de demos</h2><p>Texto visible de la demo.</p>'
                     f'<img src="{self.image.get_absolute_url()}" alt="Captura">'
                     '<template><p>Plantilla oculta</p></template></body></html>')
        self.article = Article.objects.create(title='Demos', slug='demos', summary='Demos', author='Author',
                                              format='html', body=self.body, published=True)

    def key(self, user, scope='articles'):
        key = ApiKey(user=user, scope=scope, name='html')
        raw = key.issue()
        key.save()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + raw}

    def signed_src(self, html):
        return re.search(r'src="(/article-images/[^"]+)"', html)[1]

    def test_format_field_defaults_to_markdown_and_api_create_read_update(self):
        self.assertEqual(Article.objects.create(title='Old', slug='old', summary='S', author='A', body='Text').format,
                         'markdown')
        headers = self.key(self.editor)
        response = self.client.post('/api/v1/articles/', json.dumps({
            'slug': 'api-html', 'title': 'API HTML', 'summary': 'S', 'author': 'A', 'format': 'html',
            'body': '<!doctype html><p>Hola</p>'}), content_type='application/json', **headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['format'], 'html')
        read = self.client.get('/api/v1/articles/api-html/', **headers)
        self.assertEqual(read.json()['format'], 'html')
        # PATCH without format keeps the format.
        response = self.client.patch('/api/v1/articles/api-html/', json.dumps({'summary': 'Changed'}),
                                     content_type='application/json', HTTP_IF_MATCH=read['ETag'], **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['format'], 'html')
        response = self.client.patch('/api/v1/articles/api-html/', json.dumps({'format': 'pdf'}),
                                     content_type='application/json', HTTP_IF_MATCH=response['ETag'], **headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('format', response.json()['error'])
        listed = self.client.get('/api/v1/articles/', **headers).json()['results']
        self.assertEqual({item['slug']: item['format'] for item in listed}['old'], 'markdown')

    def test_only_article_changers_create_html(self):
        response = self.client.post('/api/v1/articles/', json.dumps({
            'slug': 'no-html', 'title': 'No', 'summary': 'S', 'author': 'A', 'format': 'html', 'body': '<p>x</p>'}),
            content_type='application/json', **self.key(self.add_only))
        self.assertEqual(response.status_code, 400)
        self.assertIn('format', response.json()['error'])
        self.assertFalse(Article.objects.filter(slug='no-html').exists())
        values = {'slug': 'form-html', 'title': 'T', 'summary': 'S', 'author': 'A', 'kind': 'guide',
                  'date': '2026-11-03', 'tags': '', 'body': '<p>x</p>', 'format': 'html'}
        self.assertIn('format', ArticleForm(values, actor=self.add_only).errors)
        self.assertTrue(ArticleForm(values, actor=self.editor).is_valid())
        self.client.force_login(self.add_only)
        page = self.client.get('/admin/athena/article/add/').content.decode()
        self.assertIn('value="markdown"', page)
        self.assertNotIn('value="html"', page)
        self.assertNotIn('data-html-preview-url', page)

    def test_html_route_access_rules(self):
        path = '/article-html/demos/'
        self.assertEqual(self.client.get(path).status_code, 404)  # Account-only article, anonymous visitor.
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get(path + 'source').content.decode(), self.body)
        self.article.published = False
        self.article.save()
        self.assertEqual(self.client.get(path).status_code, 404)  # Drafts: editors only.
        self.assertEqual(self.client.get(path + 'source').status_code, 404)
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.article.published = self.article.is_public = True
        self.article.save()
        self.client.logout()
        self.assertEqual(self.client.get(path).status_code, 200)  # Public article for a visitor.
        self.assertEqual(self.client.get(path + 'source').status_code, 200)
        Article.objects.create(title='Plain', slug='plain', summary='S', author='A', body='Text', published=True,
                               is_public=True)
        self.assertEqual(self.client.get('/article-html/plain/').status_code, 404)
        self.assertEqual(self.client.post(path).status_code, 405)

    def test_html_document_headers_bridge_and_reader_csp(self):
        self.client.force_login(self.reader)
        response = self.client.get('/article-html/demos/')
        csp = response['Content-Security-Policy']
        self.assertTrue(csp.startswith(SANDBOX + ';'), csp)
        self.assertNotIn('allow-same-origin', csp)
        for directive in ["default-src 'none'", "script-src 'unsafe-inline'", "connect-src 'none'", "form-action 'none'",
                          "frame-ancestors 'self'", "object-src 'none'", "base-uri 'none'"]:
            self.assertIn(directive, csp)
        self.assertIn("img-src 'self' http://testserver data: blob:", csp)
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertIn('no-store', response['Cache-Control'])
        html = response.content.decode()
        self.assertEqual(html.count("post({ type: 'athena:ready' })"), 1)
        self.assertLess(html.index('athena:ready'), html.index('</body>'))
        self.assertGreater(html.index('athena:ready'), html.index('<template>'))
        # Without </body> the bridge is appended.
        self.article.body = '<p>Sin cierre</p>'
        self.article.save()
        self.assertTrue(self.client.get('/article-html/demos/').content.decode().rstrip().endswith('</script>'))
        # The reader page keeps its strict policy.
        reader = self.client.get('/')['Content-Security-Policy']
        self.assertIn("script-src 'self';", reader)
        self.assertIn("frame-ancestors 'none'", reader)

    def test_bridge_exposes_the_image_viewer_call(self):
        self.client.force_login(self.reader)
        html = self.client.get('/article-html/demos/').content.decode()
        bridge = html[html.rindex('<script>'):]
        self.assertIn('window.athena = Object.freeze({', bridge)
        self.assertIn('openImages(items, index = 0)', bridge)
        self.assertIn("post({ type: 'athena:images', items:", bridge)
        self.assertIn("type === 'athena:images-closed'", bridge)
        self.assertIn("new CustomEvent('athena:images-closed'", bridge)

    def test_bridge_reports_the_outline_for_the_page_tree(self):
        self.client.force_login(self.reader)
        html = self.client.get('/article-html/demos/').content.decode()
        bridge = html[html.rindex('<script>'):]
        self.assertIn("post({ type: 'athena:outline', items })", bridge)
        self.assertIn("document.querySelectorAll('h2[id], h3[id]')", bridge)
        self.assertIn('meta[name="athena-outline"]', bridge)
        self.assertIn('new MutationObserver(queueOutline)', bridge)
        self.assertIn('requestAnimationFrame(outline)', bridge)
        self.assertIn("type === 'athena:focus'", bridge)
        self.assertIn('focus({ preventScroll: true })', bridge)

    def test_reader_markdown_marker_tools_and_pdf_export(self):
        self.article.pdf, self.article.pdf_name = b'%PDF-1.7\nattached', 'attached.pdf'
        self.article.save()
        self.client.force_login(self.editor)
        page = self.client.get('/content/demos.md').content.decode()
        self.assertIn('<div class="html-article" data-src="/article-html/demos/" data-source="/article-html/demos/source"', page)
        self.assertIn('# Demos', page)
        self.assertNotIn('Galería de demos', page)
        self.assertNotIn('Exportar PDF', page)
        self.assertIn('Editar artículo', page)
        self.assertIn('/pdf/demos.pdf', page)
        self.assertEqual(self.client.get('/content/demos.pdf').status_code, 404)
        self.assertEqual(self.client.get('/pdf/demos.pdf').status_code, 200)
        Article.objects.create(title='Plain', slug='plain', summary='S', author='A', body='Text', published=True)
        self.assertIn('Exportar PDF', self.client.get('/content/plain.md').content.decode())

    def test_signed_image_urls(self):
        url = self.image.get_absolute_url()
        self.assertEqual(self.client.get(url).status_code, 404)  # Account-only article: no session, no signature.
        self.client.force_login(self.reader)
        src = self.signed_src(self.client.get('/article-html/demos/').content.decode())
        self.assertRegex(src, rf'^{url}\?sig=[\w:-]+$')
        visitor = Client()
        response = visitor.get(src)
        self.assertEqual(response.status_code, 200)  # Valid without a session.
        self.assertEqual(response['Content-Type'], 'image/png')
        response.close()
        signature = src.split('sig=')[1]
        other = create_image(picture(), self.editor)
        self.assertEqual(visitor.get(f'{other.get_absolute_url()}?sig={signature}').status_code, 404)  # Wrong id.
        self.assertEqual(visitor.get(f'{url}?sig={signature}x').status_code, 404)
        self.assertEqual(visitor.get(f'{url}?sig=').status_code, 404)
        with patch('django.core.signing.time.time', return_value=time.time() + 3601):
            self.assertEqual(visitor.get(src).status_code, 404)  # Expired after one hour.
            self.assertEqual(self.client.get(src).status_code, 200)  # A session still reads it.
        # Article images are signed wherever they appear; another host's path is left alone.
        self.article.body = (f'<img src="{other.get_absolute_url()}"><img src="https://evil.test{url}">'
                             f'<img src="https://evil.test/x{url}"><div style="background:url(\'{url}\')"></div>')
        self.article.save()
        html = self.client.get('/article-html/demos/').content.decode()
        self.assertIn(f'<img src="{other.get_absolute_url()}?sig=', html)
        self.assertIn(f'src="https://evil.test{url}"', html)
        self.assertIn(f'src="https://evil.test/x{url}"', html)
        self.assertIn(f"url('{url}?sig=", html)

    def test_html_references_keep_images_and_validate(self):
        css = create_image(picture(), self.editor)
        self.article.body = (f'<style>.hero {{ background: url("{css.get_absolute_url()}") }}</style>'
                             f'<script>const shots = ["https://athena.moratechnology.com{self.image.get_absolute_url()}"];</script>')
        self.article.save()
        self.assertEqual(referenced_image_ids(self.article.body, html=True), {css.pk, self.image.pk})
        self.assertEqual(referenced_image_ids(f'<img src="https://evil.test{css.get_absolute_url()}">', html=True), set())
        sync_image_usage()
        self.assertEqual(ManagedImage.objects.filter(unused_since=None).count(), 2)
        later = timezone.now() + timedelta(days=3)
        self.assertEqual(collect_images(now=later)['images'], [])
        self.assertEqual(ManagedImage.objects.count(), 2)
        missing = '/article-images/00000000-0000-4000-8000-000000000001/'
        with self.assertRaises(ValidationError):
            check_references(f'<img src="{missing}">', html=True)
        foreign = create_image(picture(), self.other)
        with self.assertRaises(ValidationError):
            check_references(f'<img src="{foreign.get_absolute_url()}">', actor=self.editor, html=True)
        check_references(f'<img src="{css.get_absolute_url()}">', actor=self.other, html=True)  # Attached, readable.

    def test_search_text_from_html(self):
        self.assertEqual(html_text(self.body), 'Galería de demos Texto visible de la demo.')
        self.assertEqual(html_text('<p>a<strong>b</strong>c</p><p>d</p><svg><text>icon</text></svg>'), 'abc d')
        self.client.force_login(self.reader)
        entry = next(item for item in self.client.get('/search-index.json').json() if item['route'] == '#/content/demos')
        self.assertEqual(entry['text'], 'Galería de demos Texto visible de la demo.')
        self.assertEqual(entry['headings'], [])
        self.assertNotIn('script text', json.dumps(entry))

    def test_editor_preview_endpoint(self):
        own = create_image(picture(), self.editor)
        foreign = create_image(picture(), self.other)
        body = f'<p>Vista</p><img src="{own.get_absolute_url()}"><img src="{foreign.get_absolute_url()}"></body>'
        self.assertEqual(self.client.post('/article-html-preview/', {'body': body}).status_code, 403)
        for user in [self.reader, self.add_only]:
            self.client.force_login(user)
            self.assertEqual(self.client.post('/article-html-preview/', {'body': body}).status_code, 403)
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get('/article-html-preview/').status_code, 405)
        response = self.client.post('/article-html-preview/?theme=dark&lang=es', {'body': body})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Security-Policy'].startswith(SANDBOX + ';'))
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
        html = response.content.decode()
        self.assertIn(f'<img src="{own.get_absolute_url()}?sig=', html)  # Own unsaved upload.
        self.assertIn(f'<img src="{foreign.get_absolute_url()}">', html)  # Another editor's unattached upload.
        self.assertIn('athena:ready', html)
        self.assertEqual(self.client.post('/article-html-preview/', {'body': 'x' * (1024 * 1024 + 1)}).status_code, 400)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.editor)
        self.assertEqual(strict.post('/article-html-preview/', {'body': body}).status_code, 403)

    def test_admin_editor_format_switch(self):
        self.client.force_login(self.editor)
        page = self.client.get(f'/admin/athena/article/{self.article.pk}/change/').content.decode()
        header = re.search(r'<h2 id="desk-source-heading">HTML</h2>.*?<span id="desk-count">', page, re.S)[0]
        self.assertIn('<fieldset class="desk-format"><legend>Formato</legend>', header)
        self.assertIn('checked', re.search(r'<input[^>]*value="html"[^>]*>', header)[0])
        self.assertIn('data-html-preview-url="/article-html-preview/"', page)
        self.assertIn('data-format="html"', page)
        self.assertEqual(page.count('name="format"'), 2)
        response = self.client.post(f'/admin/athena/article/{self.article.pk}/change/', {
            'title': 'Demos', 'kind': 'guide', 'summary': 'Demos', 'author': 'Author', 'tags': '', 'date': '2026-11-03',
            'format': 'markdown', 'body': '# Demos\n\nAhora Markdown.', 'published': 'on', 'access': 'account',
            'status': '', 'url': '', 'download_file': '', '_save': '1',
            'loaded_revision': self.article.updated_at.isoformat()})
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.format, 'markdown')

    def test_fonts_allow_the_opaque_frame(self):
        response = self.client.get('/fonts/inter-latin.woff2', HTTP_ORIGIN='null')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Access-Control-Allow-Origin'], '*')
        response.close()
        styles = self.client.get('/assets/suite-tokens.css')
        self.assertEqual(styles.status_code, 200)
        self.assertIn('text/css', styles['Content-Type'])
        styles.close()
