import hashlib
import re
import tempfile

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from .forms import permissions
from .models import Article, Download, DownloadEvent


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class DownloadEventTests(TestCase):
    """Descargas registradas: one event per served file, visible to view_downloadevent holders only."""

    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser('root')
        cls.editor = User.objects.create_user('editor', is_staff=True)
        cls.editor.user_permissions.set(permissions(['athena.view_article', 'athena.view_download',
                                                     'athena.change_download', 'athena.add_download']))
        cls.reader = User.objects.create_user('reader')

    def setUp(self):
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(tempfile.TemporaryDirectory())))
        self.item = Download.objects.create(title='Framework actual', section='framework',
                                            file=ContentFile(b'first', name='Plantilla 1.zip'))

    def get(self, user, url):
        self.client.force_login(user)
        response = self.client.get(url)
        if response.status_code == 200:
            b''.join(response.streaming_content)
        return response

    def test_each_view_logs_the_served_file_and_a_swap_keeps_old_snapshots(self):
        self.assertEqual(self.get(self.reader, '/downloads/' + self.item.slug).status_code, 200)
        self.assertEqual(self.get(self.root, '/downloads/framework/latest').status_code, 200)
        slug = self.item.slug
        self.item.file = ContentFile(b'second file', name='Plantilla 2.zip')
        self.item.save()
        self.item.refresh_from_db()
        self.assertEqual(self.item.slug, slug)
        response = self.get(self.reader, '/downloads/' + slug)
        self.assertIn('Plantilla 2.zip', response['Content-Disposition'])
        rows = list(DownloadEvent.objects.order_by('pk').values_list(
            'user__username', 'username', 'download_id', 'title', 'filename', 'size', 'sha256', 'path'))
        first, second = hashlib.sha256(b'first').hexdigest(), hashlib.sha256(b'second file').hexdigest()
        self.assertEqual(rows, [
            ('reader', 'reader', self.item.pk, 'Framework actual', 'Plantilla 1.zip', 5, first, f'/downloads/{slug}'),
            ('root', 'root', self.item.pk, 'Framework actual', 'Plantilla 1.zip', 5, first, '/downloads/framework/latest'),
            ('reader', 'reader', self.item.pk, 'Framework actual', 'Plantilla 2.zip', 11, second, f'/downloads/{slug}'),
        ])
        # The snapshots outlive the file row and a renamed or deleted account.
        self.item.delete()
        self.reader.username = 'renamed'
        self.reader.save()
        self.assertEqual(list(DownloadEvent.objects.values_list('username', flat=True).order_by('pk')),
                         ['reader', 'root', 'reader'])
        self.assertFalse(DownloadEvent.objects.exclude(download=None).exists())

    def test_no_event_for_missing_unpublished_file_or_anonymous_visitor(self):
        self.client.logout()
        self.assertEqual(self.client.get('/downloads/' + self.item.slug).status_code, 302)
        self.assertEqual(self.client.get('/downloads/framework/latest').status_code, 302)
        self.assertEqual(self.get(self.reader, '/downloads/missing').status_code, 404)
        self.item.file.storage.delete(self.item.file.name)  # A row whose file is gone.
        self.assertEqual(self.get(self.reader, '/downloads/' + self.item.slug).status_code, 404)
        self.assertEqual(self.get(self.reader, '/downloads/framework/latest').status_code, 404)
        self.item.published = False
        self.item.save()
        self.assertEqual(self.get(self.reader, '/downloads/' + self.item.slug).status_code, 404)
        self.assertFalse(DownloadEvent.objects.exists())

    def test_recent_activity_and_list_follow_the_permission(self):
        self.get(self.reader, '/downloads/' + self.item.slug)
        line = '<strong>reader</strong> descargó <span class="download-file">Framework actual (Plantilla 1.zip)</span> · ahora'
        self.client.force_login(self.root)
        page = self.client.get('/admin/')
        self.assertContains(page, line, html=False)
        self.assertContains(page, 'href="/admin/athena/downloadevent/">Ver todas las descargas</a>')
        self.assertContains(page, 'Descargas registradas')  # The sidebar link.
        listing = self.client.get('/admin/athena/downloadevent/')
        self.assertContains(listing, '<td class="field-username">reader</td>', html=True)
        self.assertContains(listing, 'Plantilla 1.zip')
        self.assertEqual(self.client.get('/admin/athena/downloadevent/?q=plantilla').context['cl'].result_count, 1)
        self.assertEqual(self.client.get('/admin/athena/downloadevent/?username=reader').context['cl'].result_count, 1)
        self.assertEqual(self.client.get(f'/admin/athena/downloadevent/?download__id__exact={self.item.pk}').context['cl'].result_count, 1)
        self.assertEqual(self.client.get('/admin/athena/downloadevent/?q=nada').context['cl'].result_count, 0)
        self.client.force_login(self.editor)
        page = self.client.get('/admin/')
        self.assertNotContains(page, 'descargó')
        self.assertNotContains(page, 'Ver todas las descargas')
        self.assertNotContains(page, 'Descargas registradas')
        self.assertEqual(self.client.get('/admin/athena/downloadevent/').status_code, 403)
        # The permission alone opens both.
        self.editor.user_permissions.add(*permissions(['athena.view_downloadevent']))
        self.client.force_login(User.objects.get(pk=self.editor.pk))
        self.assertContains(self.client.get('/admin/'), line, html=False)
        self.assertEqual(self.client.get('/admin/athena/downloadevent/').status_code, 200)

    def test_recent_activity_mixes_by_time_keeps_fifteen_and_the_restricted_filter(self):
        secret = Article.objects.create(title='Informe privado', slug='informe-privado', summary='s', author='a',
                                        body='x', published=True, is_restricted=True)
        kind = ContentType.objects.get_for_model(Article)
        for number in range(10):
            LogEntry.objects.log_actions(self.root.pk, [secret], ADDITION) if number == 0 else LogEntry.objects.create(
                user=self.root, content_type=kind, object_id='0', object_repr=f'Entrada {number}', action_flag=ADDITION)
            self.get(self.reader, '/downloads/' + self.item.slug)
        self.client.force_login(self.root)
        items = re.findall(r'<li class="(\w+)"', self.client.get('/admin/').content.decode())
        self.assertEqual(len(items), 15)
        self.assertEqual(items[:2], ['downloadlink', 'addlink'])  # Newest first, alternating.
        self.client.force_login(self.editor)
        page = self.client.get('/admin/').content.decode()
        self.assertEqual(len(re.findall(r'<li class="(\w+)"', page)), 9)  # The restricted entry is filtered out.
        self.assertNotIn('Informe privado', page)

    def test_admin_page_is_read_only(self):
        self.get(self.reader, '/downloads/' + self.item.slug)
        event = DownloadEvent.objects.get()
        self.client.force_login(self.root)
        self.assertEqual(self.client.get('/admin/athena/downloadevent/add/').status_code, 403)
        self.assertEqual(self.client.post(f'/admin/athena/downloadevent/{event.pk}/delete/', {'post': 'yes'}).status_code, 403)
        detail = self.client.get(f'/admin/athena/downloadevent/{event.pk}/change/')
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'name="_save"')
        self.client.post(f'/admin/athena/downloadevent/{event.pk}/change/', {'username': 'x'})
        self.client.post('/admin/athena/downloadevent/', {'action': 'delete_selected', '_selected_action': [event.pk], 'post': 'yes'})
        event.refresh_from_db()
        self.assertEqual(event.username, 'reader')
        listing = self.client.get('/admin/athena/downloadevent/')
        self.assertNotContains(listing, f'/admin/athena/downloadevent/{event.pk}/change/')
        self.assertNotContains(listing, 'delete_selected')
