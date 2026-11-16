import hashlib
import json
import os
import re
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .forms import permissions
from .images import collect_images, create_image, image_path, referenced_image_ids, sign_image_urls
from .models import ApiKey, Article, ManagedImage
from .test_images import picture
from .views import article_html, pdf_fetcher


def box(kind, payload=b''):
    return (8 + len(payload)).to_bytes(4, 'big') + kind + payload


def mp4(brand=b'isom', compatible=b'isomiso2avc1mp41', *, width=64, height=48, media=4000):
    """A minimal ISO BMFF movie: ftyp, moov with one track header (version 0, 84 bytes), mdat."""
    tkhd = bytes(76) + (width << 16).to_bytes(4, 'big') + (height << 16).to_bytes(4, 'big')
    moov = box(b'moov', box(b'mvhd', bytes(100)) + box(b'trak', box(b'tkhd', tkhd)))
    return box(b'ftyp', brand + bytes(4) + compatible) + moov + box(b'mdat', bytes(range(256)) * (media // 256))


def video(data=None, name='demo.mp4', content_type='video/mp4'):
    return SimpleUploadedFile(name, mp4() if data is None else data, content_type=content_type)


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class ArticleVideoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = User.objects.create_user('video-editor', is_staff=True)
        cls.editor.user_permissions.set(permissions(['athena.add_article', 'athena.change_article', 'athena.view_article']))
        cls.other = User.objects.create_user('video-other', is_staff=True)
        cls.other.user_permissions.set(permissions(['athena.add_article', 'athena.change_article']))
        cls.reader = User.objects.create_user('video-reader')

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.root / 'media', DATA_DIR=self.root))
        self.video = create_image(video(), self.editor)
        self.article = Article.objects.create(slug='video-article', title='Video', summary='Video', author='Author',
                                              body='Text')

    def key(self, user, scope='articles'):
        key = ApiKey(user=user, scope=scope, name='video')
        raw = key.issue()
        key.save()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + raw}

    def attach(self, body=None, *, published=True, public=False, format='markdown'):
        url = self.video.get_absolute_url()
        self.article.body = body or f'<video src="{url}" controls preload="metadata"></video>'
        self.article.format, self.article.published, self.article.is_public = format, published, public
        self.article.save()

    def test_upload_api_and_editor_store_the_bytes_with_metadata(self):
        raw = mp4()
        response = self.client.post('/api/v1/article-images/', {'file': video(name='../../x.html', content_type='text/html')},
                                    **self.key(self.editor))
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        url = f'/article-images/{data["id"]}/'
        self.assertEqual(data, {'id': data['id'], 'url': url, 'markdown': f'<video src="{url}" controls preload="metadata"></video>',
                                'content_type': 'video/mp4', 'size': len(raw), 'width': 64, 'height': 48,
                                'sha256': hashlib.sha256(raw).hexdigest()})
        stored = ManagedImage.objects.get(pk=data['id'])
        path = image_path(stored)
        self.assertRegex(path.name, r'^[0-9a-f]{32}\.mp4$')
        self.assertEqual(path.read_bytes(), raw)  # Stored as uploaded, not re-encoded.
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.client.force_login(self.editor)
        response = self.client.post('/article-images/upload/', {'file': video(content_type='application/octet-stream')})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['content_type'], 'video/mp4')
        self.assertEqual(list(self.root.glob('video-upload-*')), [])
        # A movie without a sized track (audio only) is accepted with 0 × 0.
        silent = create_image(video(mp4(width=0, height=0)), self.editor)
        self.assertEqual((silent.width, silent.height), (0, 0))

    def test_content_decides_and_invalid_files_are_rejected(self):
        bad = [b'not a video at all', b'<html>video</html>', picture().read(), mp4(b'qt  ', b'qt  '),  # QuickTime.
               mp4()[:-10],  # mdat runs past the end of the file.
               box(b'ftyp', b'isom' + bytes(4) + b'isom') + box(b'mdat', bytes(100))]  # No moov.
        for raw in bad:
            with self.assertRaises(ValidationError) as caught:
                create_image(SimpleUploadedFile('clip.mp4', raw, content_type='video/mp4'), self.editor)
            self.assertIn('video', ' '.join(caught.exception.messages).lower())
        response = self.client.post('/api/v1/article-images/', {'file': SimpleUploadedFile('clip.mp4', b'plain text')},
                                    **self.key(self.editor))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], ['El video no es válido. Use un archivo MP4 (H.264 y AAC).'])
        # An MP4 named and typed as a PNG is still a video; an image named .mp4 is rejected, not stored.
        self.assertEqual(create_image(video(name='x.png', content_type='image/png'), self.editor).format, 'mp4')
        self.assertEqual(ManagedImage.objects.filter(format='mp4').count(), 2)
        with patch('athena.images.MAX_MP4_BOXES', 2), self.assertRaises(ValidationError):
            create_image(video(), self.editor)
        self.assertEqual(list(self.root.glob('video-upload-*')), [])

    def test_size_cap_and_image_cap_stay_separate(self):
        with patch('athena.images.MAX_VIDEO_BYTES', 1000), self.assertRaises(ValidationError) as caught:
            create_image(video(), self.editor)
        self.assertIn('200 MiB', caught.exception.messages[0])
        upload = video()
        upload.size = 10  # A client-reported size cannot get past the counted bytes.
        with patch('athena.images.MAX_VIDEO_BYTES', 1000), self.assertRaises(ValidationError):
            create_image(upload, self.editor)
        self.assertEqual(list(self.root.glob('video-upload-*')), [])
        with patch('athena.images.MAX_BYTES', 10):
            self.assertEqual(create_image(video(), self.editor).format, 'mp4')
            with self.assertRaises(ValidationError):
                create_image(picture(), self.editor)

    def test_byte_ranges_head_and_headers(self):
        self.attach(public=True)
        raw = image_path(self.video).read_bytes()
        size, url = len(raw), self.video.get_absolute_url()

        def get(range_header=None, method='get'):
            extra = {'HTTP_RANGE': range_header} if range_header else {}
            response = getattr(self.client, method)(url, **extra)
            body = b''.join(response.streaming_content) if response.streaming else response.content
            response.close()
            return response, body

        response, body = get()
        self.assertEqual((response.status_code, body, response['Content-Type']), (200, raw, 'video/mp4'))
        self.assertEqual((response['Accept-Ranges'], response['Content-Length']), ('bytes', str(size)))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', response['Cache-Control'])
        for header, start, end in [('bytes=0-99', 0, 99), ('bytes=100-', 100, size - 1), ('bytes=-10', size - 10, size - 1),
                                   (f'bytes=5-{size + 50}', 5, size - 1), ('bytes=0-0', 0, 0), (f'bytes=-{size + 9}', 0, size - 1)]:
            response, body = get(header)
            self.assertEqual(response.status_code, 206, header)
            self.assertEqual(response['Content-Range'], f'bytes {start}-{end}/{size}')
            self.assertEqual(response['Content-Length'], str(end - start + 1))
            self.assertEqual(body, raw[start:end + 1], header)
        for header in [f'bytes={size}-', f'bytes={size + 1}-{size + 5}', 'bytes=-0']:
            response, body = get(header)
            self.assertEqual(response.status_code, 416, header)
            self.assertEqual(response['Content-Range'], f'bytes */{size}')
        for header in ['bytes=5-2', 'bytes=0-1,4-5', 'items=0-1', 'bytes=-', 'bytes=x-1']:
            response, body = get(header)
            self.assertEqual((response.status_code, body), (200, raw), header)
        response, body = get(method='head')
        self.assertEqual((response.status_code, body, response['Content-Length']), (200, b'', str(size)))
        self.assertEqual((response['Accept-Ranges'], response['Content-Type']), ('bytes', 'video/mp4'))
        response, body = get('bytes=10-19', method='head')
        self.assertEqual((response.status_code, body, response['Content-Range']), (206, b'', f'bytes 10-19/{size}'))
        with patch('athena.views.RANGE_CHUNK', 1000):  # An open range is answered one chunk at a time.
            response, body = get('bytes=50-')
        self.assertEqual((response['Content-Range'], body), (f'bytes 50-1049/{size}', raw[50:1050]))
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_access_rules_match_images(self):
        url = self.video.get_absolute_url()

        def status(user, extra=None):
            client = Client()
            if user:
                client.force_login(user)
            response = client.get(url, **(extra or {}))
            response.close()
            return response.status_code

        # Not attached: only the uploader previews it, also with a byte range.
        self.assertEqual([status(user) for user in (self.editor, self.other, self.reader, None)], [200, 404, 404, 404])
        self.assertEqual(status(self.other, {'HTTP_RANGE': 'bytes=0-1'}), 404)
        self.assertEqual(status(self.editor, {'HTTP_RANGE': 'bytes=0-1'}), 206)
        self.attach(published=False)
        self.assertEqual([status(user) for user in (self.other, self.reader, None)], [200, 404, 404])
        self.attach(published=True)
        self.assertEqual([status(user) for user in (self.reader, None)], [200, 404])
        self.attach(published=True, public=True)
        self.assertEqual(status(None), 200)
        api = f'/api/v1/article-images/{self.video.pk}/'
        response = self.client.get(api, HTTP_RANGE='bytes=0-3', **self.key(self.reader, 'read'))
        self.assertEqual((response.status_code, response['Content-Range']), (206, f'bytes 0-3/{self.video.size}'))
        response.close()
        self.article.is_restricted, self.article.is_public = True, False
        self.article.save()
        self.assertEqual([status(user) for user in (self.reader, None)], [404, 404])

    def test_html_article_signs_video_source_and_poster(self):
        poster = create_image(picture(), self.editor)
        source = create_image(video(), self.editor)
        url, source_url, poster_url = self.video.get_absolute_url(), source.get_absolute_url(), poster.get_absolute_url()
        body = (f'<!doctype html><html><body><video src="{url}" controls></video>'
                f'<video controls poster="{poster_url}"><source src="{source_url}" type="video/mp4"></video></body></html>')
        self.assertEqual(referenced_image_ids(body, html=True), {self.video.pk, source.pk, poster.pk})
        self.attach(body, format='html')  # Account-only, published.
        self.client.force_login(self.reader)
        html = self.client.get(f'/article-html/{self.article.slug}/').content.decode()
        signed = {match[1] for match in re.finditer(r'/article-images/([0-9a-f-]{36})/\?sig=[\w:-]+', html)}
        self.assertEqual(signed, {str(self.video.pk), str(source.pk), str(poster.pk)})
        self.assertIn('media-src', self.client.get(f'/article-html/{self.article.slug}/')['Content-Security-Policy'])
        visitor = Client()  # The opaque-origin frame sends no cookie; the signature alone opens the video.
        src = re.search(rf'{url}\?sig=[\w:-]+', html)[0]
        response = visitor.get(src, HTTP_RANGE='bytes=0-7')
        self.assertEqual((response.status_code, b''.join(response.streaming_content)), (206, mp4()[:8]))
        response.close()
        self.assertEqual(visitor.get(url).status_code, 404)
        self.assertEqual(sign_image_urls(body, {self.video.pk}).count('?sig='), 1)

    def test_markdown_video_attaches_and_gc_keeps_it(self):
        poster = create_image(picture(), self.editor)
        url = self.video.get_absolute_url()
        body = (f'Intro\n\n<video src="{url}" controls poster="{poster.get_absolute_url()}"></video>\n\n'
                f'<video controls>\n<source src="{url}" type="video/mp4">\n</video>\n')
        self.assertEqual(referenced_image_ids(body), {self.video.pk, poster.pk})
        self.attach(body, published=False)
        old = timezone.now() - timedelta(days=2)
        ManagedImage.objects.update(created_at=old, unused_since=old)
        stale = self.root / 'video-upload-killed.part'
        stale.write_bytes(b'partial')
        os.utime(stale, (old.timestamp(), old.timestamp()))
        orphan = image_path(self.video).parent / f'{uuid4().hex}.mp4'
        orphan.write_bytes(b'orphan')
        os.utime(orphan, (old.timestamp(), old.timestamp()))
        with self.captureOnCommitCallbacks(execute=True):
            report = collect_images(now=timezone.now() + timedelta(days=2))
        self.assertEqual(report['images'], [])
        self.assertEqual(sorted(report['orphans']), sorted([orphan.name, stale.name]))
        self.assertTrue(image_path(self.video).exists())
        self.assertFalse(stale.exists() or orphan.exists())
        self.article.body = 'Removed'
        self.article.save()
        ManagedImage.objects.update(unused_since=old)
        with self.captureOnCommitCallbacks(execute=True):
            report = collect_images(now=timezone.now() + timedelta(days=2))
        self.assertEqual(sorted(report['images']), sorted([str(self.video.pk), str(poster.pk)]))
        self.assertFalse(image_path(self.video).exists())

    def test_share_image_and_pdf_never_use_a_video(self):
        headers = self.key(self.editor)
        self.attach()
        etag = self.client.get('/api/v1/articles/video-article/', **headers)['ETag']
        response = self.client.patch('/api/v1/articles/video-article/', json.dumps({'share_image': str(self.video.pk)}),
                                     content_type='application/json', HTTP_IF_MATCH=etag, **headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('share_image', response.json()['error'])
        url = self.video.get_absolute_url()
        self.attach(f'Antes\n\n<video src="{url}" controls></video>\n\nDespués')
        html = article_html(self.article, settings.PUBLIC_ORIGIN)
        self.assertNotIn('<video', html)
        self.assertIn(f'<a href="{url}">Ver video</a>', html)
        self.attach(f"<video controls><source src='{url}?a=1&amp;b=\"x' type='video/mp4'></video>")
        self.assertIn(f'<a href="{url}?a=1&amp;b=&quot;x">Ver video</a>', article_html(self.article, settings.PUBLIC_ORIGIN))
        with self.assertRaises(ValueError):
            pdf_fetcher({str(self.video.pk): self.video.sha256}).fetch(settings.PUBLIC_ORIGIN + url)
