import json
import re
import tempfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .forms import permissions
from .images import collect_images, create_image, image_path
from .models import ApiKey, Article, ManagedImage

# What Caddy sends: the public Host and X-Forwarded-Proto, which SECURE_PROXY_SSL_HEADER reads.
HTTPS = {'HTTP_X_FORWARDED_PROTO': 'https', 'HTTP_HOST': 'testserver'}


def upload(size=(1200, 630), fmt='PNG'):
    data = BytesIO()
    Image.new('RGB', size, '#ffb900').save(data, format=fmt)
    return SimpleUploadedFile('share.' + fmt.lower(), data.getvalue())


def meta(page):
    return dict(re.findall(r'<meta (?:property|name)="([^"]+)" content="([^"]*)"', page))


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class ShareLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = User.objects.create_user('share-editor', is_staff=True)
        cls.editor.user_permissions.set(permissions(['athena.add_article', 'athena.change_article', 'athena.view_article']))
        cls.other = User.objects.create_user('share-other', is_staff=True)
        cls.other.user_permissions.set(permissions(['athena.add_article', 'athena.change_article']))
        cls.admin = User.objects.create_superuser('share-admin')

    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=root / 'media', DATA_DIR=root))
        self.image = create_image(upload(), self.editor)
        self.article = self.make('shared', is_public=True)

    def make(self, slug, *, published=True, share=True, **fields):
        return Article.objects.create(slug=slug, title=f'Título {slug} & más', summary=f'Resumen de {slug} "citado"',
                                      author='Autor', body='Texto privado del cuerpo', published=published,
                                      share_image=self.image if share else None, **fields)

    def key(self, user, scope='articles'):
        key = ApiKey(user=user, scope=scope, name='share')
        raw = key.issue()
        key.save()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + raw}

    def test_share_page_for_public_and_account_only_articles(self):
        account = self.make('account-only')
        for article in [self.article, account]:
            response = self.client.get(f'/s/{article.slug}', **HTTPS)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
            page = response.content.decode()
            tags = meta(page)
            image_url = f'https://testserver/s/{article.slug}/image?v={self.image.sha256[:16]}'
            self.assertEqual(tags, {
                'viewport': 'width=device-width,initial-scale=1', 'robots': 'noindex, nofollow', 'description': f'Resumen de {article.slug} &quot;citado&quot;',
                'og:type': 'article', 'og:site_name': 'Athena', 'og:locale': 'es_ES',
                'og:title': f'Título {article.slug} &amp; más', 'og:description': f'Resumen de {article.slug} &quot;citado&quot;',
                'og:url': f'https://testserver/s/{article.slug}', 'og:image': image_url, 'og:image:type': 'image/png',
                'og:image:width': '1200', 'og:image:height': '630', 'twitter:card': 'summary_large_image',
            })
            self.assertIn(f'<meta http-equiv="refresh" content="0;url=/#/content/{article.slug}">', page)
            self.assertIn(f'<a href="/#/content/{article.slug}">', page)
            self.assertNotIn('<script', page)
            self.assertNotIn('Texto privado', page)
            self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.client.get('/s/shared/', **HTTPS).status_code, 200)

    def test_every_other_case_is_the_same_bare_redirect(self):
        self.make('draft', published=False, is_public=True)
        restricted = self.make('restricted', is_restricted=True)
        restricted.allowed_users.add(self.editor)
        self.make('no-image', share=False, is_public=True)
        self.client.force_login(self.admin)  # Even a reader who may open the article gets no preview data.
        for slug in ['draft', 'restricted', 'no-image', 'unknown']:
            for client in [self.client, self.client_class()]:
                response = client.get(f'/s/{slug}', **HTTPS)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response['Location'], f'/#/content/{slug}')
                self.assertEqual(response.content, b'')
                self.assertNotIn('ETag', response)
        image_path(self.image).unlink()  # A missing file also means no preview.
        self.assertEqual(self.client.get('/s/shared').status_code, 302)
        self.assertEqual(self.client.post('/s/shared').status_code, 405)

    def test_image_route_access_headers_and_conditional_get(self):
        version = self.image.sha256[:16]
        response = self.client.get(f'/s/shared/image?v={version}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), image_path(self.image).read_bytes())
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(response['ETag'], f'"{self.image.sha256}"')
        self.assertEqual(response['Cache-Control'], 'public, max-age=31536000, immutable')
        self.assertNotIn('Vary', response)
        self.assertEqual(self.client.get('/s/shared/image')['Cache-Control'], 'public, max-age=3600')
        cached = self.client.get(f'/s/shared/image?v={version}', HTTP_IF_NONE_MATCH=f'"{self.image.sha256}"')
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached['ETag'], f'"{self.image.sha256}"')
        self.assertEqual(self.client.head('/s/shared/image').status_code, 200)
        self.assertEqual(self.client.post('/s/shared/image').status_code, 405)
        self.make('draft', published=False, is_public=True)
        self.make('restricted', is_restricted=True)
        self.make('no-image', share=False, is_public=True)
        self.client.force_login(self.admin)
        for slug in ['draft', 'restricted', 'no-image', 'unknown']:
            self.assertEqual(self.client.get(f'/s/{slug}/image?v={version}').status_code, 404)

    def test_share_image_follows_article_access_on_the_image_route(self):
        account = create_image(upload(), self.editor)
        Article.objects.filter(pk=self.make('account-only', share=False).pk).update(share_image=account)
        self.assertEqual(self.client.get(self.image.get_absolute_url()).status_code, 200)  # Public article.
        self.assertEqual(self.client.get(account.get_absolute_url()).status_code, 404)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(account.get_absolute_url()).status_code, 200)

    def test_share_image_is_kept_by_cleanup_and_released_when_cleared(self):
        self.image.refresh_from_db()
        self.assertIsNone(self.image.unused_since)
        old = timezone.now() + timedelta(days=3)
        ManagedImage.objects.filter(pk=self.image.pk).update(created_at=old - timedelta(days=10))
        report = collect_images(now=old)
        self.assertEqual(report['images'], [])
        self.assertTrue(image_path(self.image).is_file())
        self.article.share_image = None
        self.article.save()
        self.image.refresh_from_db()
        self.assertIsNotNone(self.image.unused_since)
        ManagedImage.objects.filter(pk=self.image.pk).update(unused_since=old - timedelta(days=2))
        self.assertEqual(collect_images(now=old)['images'], [str(self.image.pk)])

    def test_api_set_clear_validation_and_scopes(self):
        headers = self.key(self.editor)
        url = '/api/v1/articles/shared/'

        def patch(value, auth=headers):
            etag = self.client.get(url, **auth)['ETag']
            return self.client.patch(url, json.dumps({'share_image': value}), content_type='application/json',
                                     HTTP_IF_MATCH=etag, **auth, **HTTPS)

        data = self.client.get(url, **headers, **HTTPS).json()
        self.assertEqual(data['share_image'], str(self.image.pk))
        self.assertEqual(data['share_url'], 'https://testserver/s/shared')
        listed = self.client.get('/api/v1/articles/', **headers).json()['results']
        self.assertEqual({row['slug']: row['share_image'] for row in listed}['shared'], str(self.image.pk))
        response = patch(None)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()['share_image'], response.json()['share_url']), (None, None))
        jpeg = create_image(upload(fmt='JPEG'), self.editor)
        response = patch(str(jpeg.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['share_image'], str(jpeg.pk))
        self.assertEqual(response.json()['share_url'], 'https://testserver/s/shared')
        small = create_image(upload((599, 315)), self.editor)
        short = create_image(upload((600, 314)), self.editor)
        webp = create_image(upload(fmt='WEBP'), self.editor)
        big = create_image(upload(), self.editor)
        ManagedImage.objects.filter(pk=big.pk).update(size=5 * 1000 * 1000 + 1)
        foreign = create_image(upload(), self.other)
        for value in [str(small.pk), str(short.pk), str(webp.pk), str(big.pk), str(foreign.pk), 'not-a-uuid',
                      '00000000-0000-0000-0000-000000000000', 5, ['x'], True]:
            response = patch(value)
            self.assertEqual(response.status_code, 400, value)
            self.assertIn('share_image', response.json()['error'])
        self.assertEqual(Article.objects.get(slug='shared').share_image_id, jpeg.pk)
        read = self.key(self.editor, scope='read')
        self.assertEqual(patch(None, read).status_code, 403)
        self.assertEqual(self.client.get(url, **read, **HTTPS).json()['share_url'], 'https://testserver/s/shared')
        created = self.client.post('/api/v1/articles/', json.dumps({
            'slug': 'created-share', 'title': 'Nuevo', 'summary': 'Resumen', 'author': 'Autor', 'kind': 'guide',
            'date': '2026-11-16', 'body': 'Texto', 'share_image': str(jpeg.pk)}), content_type='application/json', **headers)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()['share_image'], str(jpeg.pk))

    def test_admin_form_shows_field_and_link_and_saves(self):
        self.client.force_login(self.editor)
        path = f'/admin/athena/article/{self.article.pk}/change/'
        page = self.client.get(path, **HTTPS)
        self.assertContains(page, 'athena/share-image.js')
        self.assertContains(page, 'data-share-image')
        self.assertContains(page, f'name="share_image" value="{self.image.pk}"')
        self.assertContains(page, f'src="/article-images/{self.image.pk}/"')
        self.assertContains(page, 'value="https://testserver/s/shared"')
        self.assertContains(page, 'data-copy-share-link')
        self.assertContains(page, 'también si el artículo es solo para usuarios con cuenta')
        self.assertNotContains(page, 'related-widget-wrapper" data-model-ref="managedimage')
        draft = self.make('draft-link', published=False)
        self.assertContains(self.client.get(f'/admin/athena/article/{draft.pk}/change/'),
                            'Sin vista previa mientras el artículo sea un borrador')
        plain = self.make('plain', share=False)
        self.assertNotContains(self.client.get(f'/admin/athena/article/{plain.pk}/change/'), 'share-link-url')
        replacement = create_image(upload((1200, 630), 'JPEG'), self.editor)
        data = {'title': self.article.title, 'slug': 'shared', 'kind': 'guide', 'summary': self.article.summary,
                'author': 'Autor', 'date': self.article.date.isoformat(), 'tags': '', 'body': self.article.body,
                'format': 'markdown', 'published': 'on', 'access': 'public', 'share_image': str(replacement.pk),
                'loaded_revision': self.article.updated_at.isoformat(), '_continue': '1'}
        self.assertEqual(self.client.post(path, data).status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.share_image_id, replacement.pk)
        small = create_image(upload((300, 200)), self.editor)
        data.update(share_image=str(small.pk), loaded_revision=self.article.updated_at.isoformat())
        self.assertContains(self.client.post(path, data), 'al menos 600 × 315 píxeles')
        data.update(share_image='')
        self.assertEqual(self.client.post(path, data).status_code, 302)
        self.article.refresh_from_db()
        self.assertIsNone(self.article.share_image_id)

    def test_robots_lets_preview_crawlers_read_share_pages_only(self):
        self.assertEqual(self.client.get('/robots.txt').content, b'User-agent: *\nAllow: /s/\nDisallow: /\n')
