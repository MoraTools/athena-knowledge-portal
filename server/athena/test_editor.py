import re
import tempfile
from pathlib import Path

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Article


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class ArticleEditorTests(TestCase):
    def setUp(self):
        self.enterContext(override_settings(DATA_DIR=Path(self.enterContext(tempfile.TemporaryDirectory()))))
        self.admin = User.objects.create_superuser('editor', password='Editor-Example-9348!')
        self.article = Article.objects.create(title='Editor guide', slug='editor-guide', summary='Summary',
                                              author='Author', body='# Editor guide\n\nContent.', published=True)
        self.path = f'/admin/athena/article/{self.article.pk}/change/'
        self.client.force_login(self.admin)

    def test_add_and_change_keep_one_source_and_all_settings(self):
        for path in ['/admin/athena/article/add/', self.path]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'name="title"', count=1)
            self.assertContains(response, 'name="body"', count=1)
            self.assertContains(response, 'class="button default desk-save"', count=1)
            for name in ['slug', 'kind', 'summary', 'author', 'tags', 'date', 'published', 'is_public',
                         'pdf_file', 'remove_pdf', 'pdf_only', 'status', 'url', 'download_file', 'markdown_file']:
                self.assertContains(response, f'name="{name}"', count=1)
            self.assertContains(response, 'type="date"')
            self.assertContains(response, 'name="_continue"')
            self.assertContains(response, 'name="_addanother"')
            self.assertContains(response, 'id="article-details"')
            panels = re.findall(r'<section class="desk-detail-panel".*?</section>', response.content.decode(), re.S)
            self.assertEqual(len(panels), 3)
            for index, (label, fields) in enumerate([
                ('Información', ['summary', 'author', 'kind', 'tags', 'slug', 'status', 'url', 'download_file']),
                ('Publicación', ['published', 'is_public', 'date']),
                ('Archivos', ['markdown_file', 'pdf_file', 'remove_pdf', 'pdf_only']),
            ], 1):
                self.assertContains(response, f'id="desk-detail-tab-{index}" aria-controls="desk-detail-panel-{index}"')
                self.assertIn(f'aria-labelledby="desk-detail-tab-{index}"', panels[index - 1])
                self.assertIn(label, panels[index - 1])
                for name in fields:
                    self.assertIn(f'name="{name}"', panels[index - 1])
                self.assertNotIn(' hidden', panels[index - 1])  # Without JavaScript all groups stay reachable.
            self.assertContains(response, 'type="submit" name="_save">Guardar cambios</button>')
            self.assertContains(response, 'name="loaded_revision"', count=1)
        self.assertContains(self.client.get(self.path), 'Publicado · Con cuenta')

    def test_view_only_has_source_and_history_without_save_or_upload(self):
        viewer = User.objects.create_user('viewer', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_article'))
        self.client.force_login(viewer)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<textarea id="id_body" readonly')
        self.assertContains(response, 'Historial')
        self.assertContains(response, 'data-detail-tab', count=3)
        self.assertContains(response, 'role="tabpanel"', count=3)
        for text in ['name="_save"', 'name="_continue"', 'data-image-upload-url', 'Importar Markdown', 'name="pdf_file"']:
            self.assertNotContains(response, text)
        self.assertEqual(self.client.post(self.path, {}).status_code, 403)

    def test_whole_article_save_preserves_non_tool_values_and_revision_guard(self):
        data = {'title': 'Changed title', 'kind': 'guide', 'summary': 'Changed summary',
                'author': 'Changed author', 'tags': 'one, two', 'date': '2026-10-13',
                'body': '# Changed title\n\nUnsaved Markdown.', 'published': 'on', 'is_public': 'True',
                'status': '', 'url': 'https://example.com', 'download_file': 'guide.zip', '_save': '1',
                'loaded_revision': self.article.updated_at.isoformat(),
                'pdf_file': SimpleUploadedFile('guide.pdf', b'%PDF-1.7\nOriginal', content_type='application/pdf')}
        response = self.client.post(self.path, data)
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Changed title')
        self.assertEqual(self.article.body, data['body'])
        self.assertEqual(self.article.summary, 'Changed summary')
        self.assertEqual(self.article.tags, ['one', 'two'])
        self.assertTrue(self.article.published)
        self.assertTrue(self.article.is_public)
        self.assertEqual((self.article.url, self.article.download_file), ('https://example.com', 'guide.zip'))
        self.assertEqual(self.article.pdf_name, 'guide.pdf')
        data.pop('pdf_file')
        data['body'] = 'Stale edit'
        response = self.client.post(self.path, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El artículo cambió desde que abrió esta página.')
        self.article.refresh_from_db()
        self.assertEqual(self.article.body, '# Changed title\n\nUnsaved Markdown.')

    def test_hidden_field_errors_and_native_save_keep_article_semantics(self):
        data = {'title': 'Changed title', 'slug': 'attempted-new-slug', 'kind': 'tool', 'summary': '',
                'author': 'Editor', 'tags': 'one, two', 'date': '2026-09-29', 'body': '# Changed title\n\nContent.',
                'published': '', 'is_public': 'True', 'status': 'stable', 'url': 'https://example.com',
                'download_file': 'tool.zip', 'pdf_only': 'on', '_continue': '1',
                'loaded_revision': self.article.updated_at.isoformat()}
        response = self.client.post(self.path, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'field-summary errors')
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Editor guide')
        data['summary'] = 'Changed summary'
        data['pdf_file'] = SimpleUploadedFile('original.pdf', b'%PDF-1.7\nOriginal', content_type='application/pdf')
        response = self.client.post(self.path, data)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.path, response['Location'])
        self.article.refresh_from_db()
        self.assertEqual(self.article.slug, 'editor-guide')
        self.assertEqual(self.article.tags, ['one', 'two'])
        self.assertFalse(self.article.published)
        self.assertTrue(self.article.is_public)
        self.assertTrue(self.article.pdf_only)
        self.assertEqual(self.article.pdf_name, 'original.pdf')
        self.assertEqual((self.article.status, self.article.url, self.article.download_file),
                         ('stable', 'https://example.com', 'tool.zip'))
        data.pop('pdf_file')
        data['remove_pdf'] = 'on'
        data['loaded_revision'] = self.article.updated_at.isoformat()
        self.assertEqual(self.client.post(self.path, data).status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.pdf_name, '')
