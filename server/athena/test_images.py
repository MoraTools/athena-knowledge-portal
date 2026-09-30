import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import select
import sqlite3
import subprocess
import sys
import tempfile
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image

from .forms import ArticleForm, permissions
from .images import collect_images, create_image, image_path, referenced_image_ids
from .models import ApiKey, Article, ManagedImage
from .pdf_export import cached_export
from .views import pdf_fetcher


def picture(fmt='PNG', *, name='image.png', content_type='image/png'):
    data = BytesIO()
    Image.new('RGB', (3, 2), '#ffb900').save(data, format=fmt)
    return SimpleUploadedFile(name, data.getvalue(), content_type=content_type)


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class ArticleImageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = User.objects.create_user('image-editor', is_staff=True)
        cls.editor.user_permissions.set(permissions(['athena.add_article', 'athena.change_article', 'athena.view_article']))
        cls.reader = User.objects.create_user('image-reader')
        cls.other = User.objects.create_user('other-editor', is_staff=True)
        cls.other.user_permissions.set(permissions(['athena.add_article', 'athena.change_article']))
        cls.add_only = User.objects.create_user('add-only', is_staff=True)
        cls.add_only.user_permissions.set(permissions(['athena.add_article']))
        cls.viewer = User.objects.create_user('view-only', is_staff=True)
        cls.viewer.user_permissions.set(permissions(['athena.view_article']))
        cls.article = Article.objects.create(slug='image-article', title='Images', summary='Images', author='Author', body='Text')

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.root / 'media', DATA_DIR=self.root))

    def key(self, user, scope='articles'):
        key = ApiKey(user=user, scope=scope, name='images')
        raw = key.issue()
        key.save()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + raw}

    def image(self, **kwargs):
        return create_image(picture(**kwargs), self.editor)

    def values(self, body, slug='new-images'):
        return {'slug': slug, 'title': 'Images', 'summary': 'Summary', 'author': 'Author', 'body': body,
                'kind': 'guide', 'date': '2026-09-29', 'tags': ''}

    def attach(self, image, *, published=False, public=False):
        self.article.body = f'![Example]({image.get_absolute_url()})'
        self.article.published, self.article.is_public = published, public
        self.article.save()

    def test_actual_bytes_safe_names_and_metadata(self):
        for fmt, extension in [('PNG', 'png'), ('JPEG', 'jpg'), ('WEBP', 'webp')]:
            image = self.image(fmt=fmt, name='../../attack.html', content_type='text/html')
            self.assertRegex(image.filename, r'^[0-9a-f]{32}\.' + extension + '$')
            path = image_path(image)
            self.assertEqual(path.parent, self.root / 'media/article-images')
            self.assertEqual(image.size, path.stat().st_size)
            self.assertEqual(image.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual((image.width, image.height), (3, 2))
            with Image.open(path) as saved:
                self.assertEqual(saved.format, fmt)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_invalid_oversized_animated_and_appended_data(self):
        for raw in [b'<svg xmlns="http://www.w3.org/2000/svg"/>', b'<html>image</html>', b'not an image']:
            with self.assertRaises(ValidationError):
                create_image(SimpleUploadedFile('image.png', raw, content_type='image/png'), self.editor)
        with patch('athena.images.MAX_BYTES', 4), self.assertRaises(ValidationError):
            self.image()
        with patch('athena.images.MAX_PIXELS', 5), self.assertRaises(ValidationError):
            self.image()
        animated = BytesIO()
        frames = [Image.new('RGB', (3, 2), color) for color in ['red', 'blue']]
        frames[0].save(animated, format='PNG', save_all=True, append_images=frames[1:])
        with self.assertRaises(ValidationError):
            create_image(SimpleUploadedFile('a.png', animated.getvalue()), self.editor)
        raw = picture().read() + b'<script>attack</script>'
        image = create_image(SimpleUploadedFile('a.png', raw), self.editor)
        self.assertNotIn(b'<script>', image_path(image).read_bytes())

    def test_failed_database_write_removes_only_its_new_file(self):
        with patch.object(ManagedImage, 'save', side_effect=RuntimeError('database failure')):
            with self.assertRaises(RuntimeError):
                self.image()
        self.assertEqual(list((self.root / 'media/article-images').iterdir()), [])
        image = self.image()
        original = image_path(image).read_bytes()
        with patch('athena.images.ManagedImage', side_effect=lambda **kwargs: ManagedImage(id=image.pk, **kwargs)):
            with self.assertRaises(FileExistsError):
                self.image()
        self.assertEqual(image_path(image).read_bytes(), original)

    def test_session_upload_requires_csrf_and_area_permissions(self):
        url = '/article-images/upload/'
        self.assertEqual(self.client.post(url, {'file': picture()}).status_code, 403)
        for user in [self.reader, self.viewer]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(url, {'file': picture()}).status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.editor)
        self.assertEqual(csrf_client.post(url, {'file': picture()}).status_code, 403)
        csrf_client.get('/admin/athena/article/add/')
        csrf = csrf_client.cookies['csrftoken'].value
        response = csrf_client.post(url, {'file': picture()}, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 201)
        image = ManagedImage.objects.get(pk=response.json()['id'])
        self.assertEqual(image.uploader, self.editor)
        self.assertEqual(response.json()['markdown'], f'![Imagen]({image.get_absolute_url()})')
        self.client.force_login(self.add_only)
        self.assertEqual(self.client.post(url, {'file': picture()}).status_code, 201)
        self.assertEqual(self.client.post(url, {'file': picture(), 'article_id': self.article.pk}).status_code, 403)
        self.client.force_login(self.editor)
        self.assertEqual(self.client.post(url, {'file': picture(), 'article_id': self.article.pk}).status_code, 201)
        self.assertEqual(self.client.post(url, {'file': picture(), 'article_id': 'not-an-id'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'file': picture(), 'article_id': 999999}).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_editor_forms_and_first_save_staging(self):
        self.client.force_login(self.editor)
        for url in ['/admin/athena/article/add/', f'/admin/athena/article/{self.article.pk}/change/']:
            page = self.client.get(url)
            self.assertContains(page, 'data-image-upload-url="/article-images/upload/"')
            self.assertContains(page, 'athena/article-images.js')
        self.client.force_login(self.viewer)
        self.assertNotContains(self.client.get(f'/admin/athena/article/{self.article.pk}/change/'), 'data-image-upload-url')
        image = self.image()
        form = ArticleForm(self.values(f'Before\n\n![Screenshot]({image.get_absolute_url()})\n\nAfter'), actor=self.editor)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        image.refresh_from_db()
        self.assertIsNone(image.unused_since)
        self.assertIn(image.get_absolute_url(), saved.body)
        self.client.force_login(self.editor)
        self.assertContains(self.client.get('/content/' + saved.slug + '.md'), image.get_absolute_url())

    def test_unattached_preview_is_only_for_active_authorized_uploader(self):
        image = self.image()
        for user, expected in [(None, 404), (self.reader, 404), (self.other, 404), (self.editor, 200)]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            response = self.client.get(image.get_absolute_url())
            self.assertEqual(response.status_code, expected)
            response.close()
        self.editor.user_permissions.clear()
        self.assertEqual(self.client.get(image.get_absolute_url()).status_code, 404)
        self.editor.user_permissions.set(permissions(['athena.change_article']))
        self.editor.is_active = False
        self.editor.save()
        self.assertEqual(self.client.get(image.get_absolute_url()).status_code, 404)

    def test_staging_ownership_and_unreadable_draft_reuse(self):
        image = self.image()
        body = f'![Secret]({image.get_absolute_url()})'
        form = ArticleForm(self.values(body), actor=self.other)
        self.assertFalse(form.is_valid())
        self.attach(image)  # The second editor can read all drafts, but an add-only author cannot.
        form = ArticleForm(self.values(body), actor=self.add_only)
        self.assertFalse(form.is_valid())
        form = ArticleForm(self.values(body), actor=self.other)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

    def test_images_follow_live_article_visibility_and_shared_references(self):
        image = self.image()
        for published, public in [(False, False), (False, True), (True, False), (True, True)]:
            self.attach(image, published=published, public=public)
            for user in [None, self.reader, self.editor, self.viewer]:
                self.client.logout()
                if user:
                    self.client.force_login(user)
                allowed = user == self.editor or (published and (public or user is not None))
                response = self.client.get(image.get_absolute_url())
                self.assertEqual(response.status_code, 200 if allowed else 404)
                if allowed:
                    self.assertEqual(response['Content-Type'], 'image/png')
                    self.assertIn('no-store', response['Cache-Control'])
                    self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
                    self.assertIn('noindex', response['X-Robots-Tag'])
                response.close()
        shared = Article.objects.create(**{k: v for k, v in self.values(self.article.body, 'shared').items() if k != 'tags'}, published=True, is_public=True)
        self.attach(image, published=False)
        self.client.logout()
        self.assertEqual(self.client.get(image.get_absolute_url()).status_code, 200)
        shared.delete()
        self.assertEqual(self.client.get(image.get_absolute_url()).status_code, 404)

    def test_saved_images_survive_uploader_deletion(self):
        image = self.image()
        self.attach(image, published=True, public=True)
        self.editor.delete()
        image.refresh_from_db()
        self.assertIsNone(image.uploader_id)
        response = self.client.get(image.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertEqual(collect_images()['images'], [])

    def test_symlink_is_never_served_or_saved_as_a_reference(self):
        image = self.image()
        target = self.root / 'private-file'
        target.write_bytes(b'private')
        image_path(image).unlink()
        (self.root / 'media/article-images' / image.filename).symlink_to(target)
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(image.get_absolute_url()).status_code, 404)
        form = ArticleForm(self.values(f'![Unsafe]({image.get_absolute_url()})'), actor=self.editor)
        self.assertFalse(form.is_valid())
        self.assertIn('body', form.errors)
        self.assertEqual(target.read_bytes(), b'private')

    def test_markdown_references_and_conservative_gc_scan(self):
        image = self.image()
        url = image.get_absolute_url()
        for body in [f'![one]({url})', f'![one][ref]\n\n[ref]: {url} "Title"',
                     f'![one][]\n\n[one]: <{settings.PUBLIC_ORIGIN}{url}?v=1#fragment>',
                     f'<img src="{url}" alt="one">', f'![one]({url.replace("-", "%2D")})']:
            self.assertEqual(referenced_image_ids(body), {image.pk}, body)
            self.article.body = body
            self.article.save()
        for body in [f'```md\n![unused]({url})\n```', f'[unused]: {url}',
                     f'<!-- {settings.PUBLIC_ORIGIN}{url} -->', url.replace('-', '%2D')]:
            self.assertEqual(referenced_image_ids(body, conservative=True), {image.pk})
        self.assertEqual(referenced_image_ids(f'![other](https://other.example{url})'), set())
        self.assertEqual(referenced_image_ids(f'![bad](file://{url})'), set())

    def test_bearer_upload_authoring_markdown_and_read_scopes(self):
        endpoint = '/api/v1/article-images/'
        self.client.force_login(self.editor)
        self.assertEqual(self.client.post(endpoint, {'file': picture()}).status_code, 401)
        for user, scope in [(self.reader, 'articles'), (self.editor, 'read')]:
            self.assertEqual(self.client.post(endpoint, {'file': picture()}, **self.key(user, scope)).status_code, 403)
        headers = self.key(self.editor)
        response = self.client.post(endpoint, {'file': picture()}, **headers)
        self.assertEqual(response.status_code, 201)
        image = ManagedImage.objects.get(pk=response.json()['id'])
        image_api = endpoint + str(image.pk) + '/'
        self.assertEqual(self.client.get(image_api, **headers).status_code, 200)
        self.assertEqual(self.client.get(image_api, **self.key(self.editor, 'read')).status_code, 404)
        data = {'slug': 'api-images', 'title': 'API images', 'summary': 'Image', 'author': 'Agent',
                'body': response.json()['markdown']}
        response = self.client.post('/api/v1/articles/', data=json.dumps(data), content_type='application/json', **headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.client.get(image_api, **self.key(self.reader, 'read')).status_code, 404)
        raw = f'![Screenshot][screen]\n\n[screen]: {settings.PUBLIC_ORIGIN}{image.get_absolute_url()}\n'
        response = self.client.post('/api/v1/articles/api-images/markdown/', {'file': SimpleUploadedFile('article.md', raw.encode())},
                                    HTTP_IF_MATCH=response['ETag'], **headers)
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.patch('/api/v1/articles/api-images/', data=json.dumps({'published': True, 'is_public': True}),
                                     content_type='application/json', HTTP_IF_MATCH=response['ETag'], **headers)
        self.assertEqual(response.status_code, 200)
        response = self.client.get(image_api, **self.key(self.reader, 'read'))
        self.assertEqual(response.status_code, 200)
        response.close()
        self.client.logout()
        self.assertEqual(self.client.get(image.get_absolute_url()).status_code, 200)

    def test_gc_dry_run_grace_drafts_shared_and_unrelated_files(self):
        image = self.image()
        old = timezone.now() - timedelta(days=2)
        ManagedImage.objects.filter(pk=image.pk).update(created_at=old, unused_since=old)
        out = StringIO()
        call_command('collect_article_images', dry_run=True, stdout=out)
        self.assertIn(str(image.pk), out.getvalue())
        self.assertTrue(ManagedImage.objects.filter(pk=image.pk).exists())
        self.assertTrue(image_path(image).exists())
        self.attach(image)  # Drafts protect images, including old staging uploads.
        shared = Article.objects.create(slug='shared', title='Shared', summary='Shared', author='Author', body=self.article.body)
        self.article.body = 'Removed'
        self.article.save()
        self.assertEqual(collect_images()['images'], [])
        shared.delete()
        image.refresh_from_db()
        self.assertGreater(image.unused_since, old)
        self.assertEqual(collect_images()['images'], [])
        downloads = self.root / 'media/downloads'
        downloads.mkdir(parents=True)
        unrelated = downloads / 'important.png'
        unrelated.write_bytes(b'download')
        odd = image_path(image).parent / 'keep.txt'
        odd.write_bytes(b'not generated')
        orphan = image_path(image).parent / f'{uuid4().hex}.png'
        orphan.write_bytes(b'orphan')
        os.utime(orphan, (old.timestamp(), old.timestamp()))
        with self.captureOnCommitCallbacks(execute=True):
            report = collect_images(now=timezone.now() + timedelta(days=2))
            self.assertEqual(report['images'], [str(image.pk)])
            self.assertEqual(report['orphans'], [orphan.name])
            self.assertTrue(image_path(image).exists())  # Not removed before the transaction commits.
        self.assertFalse(image_path(image).exists())
        self.assertFalse(orphan.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(odd.exists())

    def test_gc_conservative_references_and_orphan_grace(self):
        image = self.image()
        old = timezone.now() - timedelta(days=2)
        ManagedImage.objects.filter(pk=image.pk).update(created_at=old, unused_since=old)
        self.article.body = f'````markdown\n![example]({image.get_absolute_url()})\n````'
        self.article.save()
        orphan = image_path(image).parent / f'{uuid4().hex}.webp'
        orphan.write_bytes(b'recent orphan')
        self.assertEqual(collect_images(dry_run=True)['images'], [])
        self.assertEqual(collect_images(dry_run=True)['orphans'], [])
        out = StringIO()
        call_command('collect_article_images', dry_run=True, stdout=out)
        self.assertIn('1 referenced', out.getvalue())

    def test_save_rechecks_after_form_validation_and_no_dangling_reference(self):
        image = self.image()
        old = timezone.now() - timedelta(days=2)
        ManagedImage.objects.filter(pk=image.pk).update(created_at=old, unused_since=old)
        form = ArticleForm(self.values(f'![Expired]({image.get_absolute_url()})'), actor=self.editor)
        self.assertTrue(form.is_valid(), form.errors)
        with self.captureOnCommitCallbacks(execute=True):
            collect_images()
        with self.assertRaises(ValidationError):
            form.save()
        self.assertFalse(Article.objects.filter(slug='new-images').exists())
        missing = f'![Missing](/article-images/{uuid4()}/)'
        headers = self.key(self.editor)
        response = self.client.patch('/api/v1/articles/image-article/', data=json.dumps({'body': missing}),
                                     content_type='application/json', HTTP_IF_MATCH=f'"{self.article.updated_at.isoformat()}"', **headers)
        self.assertEqual(response.status_code, 400)
        self.article.refresh_from_db()
        self.assertEqual(self.article.body, 'Text')

    def test_pdf_manifest_safe_loading_and_cache_invalidation(self):
        image, foreign = self.image(), self.image()
        self.attach(image, published=True, public=True)
        fetcher = pdf_fetcher({str(image.pk): image.sha256})
        url = settings.PUBLIC_ORIGIN + image.get_absolute_url()
        self.assertEqual(fetcher.fetch(url).read(), image_path(image).read_bytes())
        for denied in [settings.PUBLIC_ORIGIN + foreign.get_absolute_url(), 'file://' + str(image_path(image)),
                       'http://169.254.169.254/', 'https://other.example' + image.get_absolute_url(),
                       settings.PUBLIC_ORIGIN + '/article-images/../downloads/x']:
            with self.assertRaises(ValueError):
                fetcher.fetch(denied)
        def render(command, **kwargs):
            source = json.loads(kwargs['input'])
            self.assertEqual(source['image_versions'], {str(image.pk): image.sha256})
            self.assertIn(image.get_absolute_url(), source['html'])
            self.assertTrue(source['base_url'].startswith(settings.PUBLIC_ORIGIN))
            Path(command[-1]).write_bytes(b'%PDF-1.4\n%%EOF')
        with patch('athena.pdf_export.subprocess.run', side_effect=render) as renderer:
            cached_export(self.article).close()
            cached_export(self.article).close()
            self.assertEqual(renderer.call_count, 1)
        original_hash = image.sha256
        ManagedImage.objects.filter(pk=image.pk).update(sha256='0' * 64)
        with patch('athena.pdf_export.subprocess.run', side_effect=lambda command, **kwargs: Path(command[-1]).write_bytes(b'%PDF')) as renderer:
            cached_export(self.article).close()
            renderer.assert_called_once()
        image_path(image).write_bytes(b'changed')
        with self.assertRaises(ValueError):
            pdf_fetcher({str(image.pk): original_hash}).fetch(url)

    def test_pdf_embeds_real_managed_pixels(self):
        from weasyprint import HTML
        from .views import article_html
        image = self.image()
        self.attach(image, published=True)
        pdf = HTML(string=article_html(self.article, settings.PUBLIC_ORIGIN), base_url=settings.PUBLIC_ORIGIN,
                   url_fetcher=pdf_fetcher({str(image.pk): image.sha256})).write_pdf()
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'/Subtype /Image', pdf)


class ImageTransactionTests(TransactionTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.root / 'media', DATA_DIR=self.root))
        self.editor = User.objects.create_user('race-editor', is_staff=True)
        self.image = create_image(picture(), self.editor)
        old = timezone.now() - timedelta(days=2)
        ManagedImage.objects.filter(pk=self.image.pk).update(created_at=old, unused_since=old)

    def test_rollback_keeps_metadata_and_file(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                collect_images()
                self.assertTrue(image_path(self.image).is_file())
                raise RuntimeError('rollback')
        self.assertTrue(ManagedImage.objects.filter(pk=self.image.pk).exists())
        self.assertTrue(image_path(self.image).is_file())

    def test_writer_serializes_with_collector_in_real_sqlite(self):
        # Copy the disposable test DB to exercise independent processes and IMMEDIATE write transactions.
        with sqlite3.connect(self.root / 'athena.sqlite3') as target:
            connection.connection.backup(target)
        env = {**os.environ, 'ATHENA_DATA_DIR': str(self.root), 'ATHENA_DEBUG': '1',
               'ATHENA_SECRET_KEY': 'local-image-race-test'}
        writer_source = '''import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE']='athena.settings'
django.setup()
from django.db import transaction
from athena.models import Article
with transaction.atomic():
    print('locked', flush=True)
    sys.stdin.readline()
    Article.objects.create(slug='race', title='Race', summary='Race', author='Author', body=sys.argv[1])
print('saved', flush=True)
'''
        gc_source = '''import django, os
os.environ['DJANGO_SETTINGS_MODULE']='athena.settings'
django.setup()
from athena.images import collect_images
print('started', flush=True)
print(collect_images(), flush=True)
'''
        body = f'![Race]({self.image.get_absolute_url()})'
        writer = subprocess.Popen([sys.executable, '-c', writer_source, body], cwd=settings.BASE_DIR / 'server', env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        collector = None
        try:
            self.assertTrue(select.select([writer.stdout], [], [], 10)[0], 'Writer did not start')
            self.assertEqual(writer.stdout.readline().strip(), 'locked')
            collector = subprocess.Popen([sys.executable, '-c', gc_source], cwd=settings.BASE_DIR / 'server', env=env,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertTrue(select.select([collector.stdout], [], [], 10)[0], 'Collector did not start')
            self.assertEqual(collector.stdout.readline().strip(), 'started')
            self.assertIsNone(collector.poll())
            output, errors = writer.communicate('\n', timeout=15)
            self.assertEqual(writer.returncode, 0, errors)
            self.assertIn('saved', output)
            output, errors = collector.communicate(timeout=15)
            self.assertEqual(collector.returncode, 0, errors)
            self.assertIn("'images': []", output)
            self.assertTrue(image_path(self.image).is_file())
        finally:
            for process in [writer, collector]:
                if process and process.poll() is None:
                    process.kill()
                    process.communicate()
