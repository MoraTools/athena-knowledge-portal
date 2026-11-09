import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, override_settings

from . import notify
from .models import Download, DownloadEvent

REAL_POST = notify.post  # setUp patches notify.post; the HTTP test calls the real one.


class SyncThread:
    """Runs the target on start(), so tests see the send without real threads."""

    def __init__(self, target, args, daemon):
        assert daemon
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, ATHENA_NTFY_SERVER='https://ntfy.invalid')
class NotifyTests(TestCase):
    """ntfy phone notifications: framework downloads and sign-ins only, after commit, never breaking the request."""

    @classmethod
    def setUpTestData(cls):
        cls.reader = User.objects.create_user('reader', password='a long test password', first_name='Ana',
                                              last_name='Pérez')
        cls.staff = User.objects.create_user('staffer', password='a long test password', is_staff=True)

    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (folder / 'topic').write_text('test-topic\n')
        self.enterContext(override_settings(MEDIA_ROOT=folder / 'media', ATHENA_NTFY_TOPIC_FILE=str(folder / 'topic')))
        self.post = self.enterContext(mock.patch.object(notify, 'post'))
        self.enterContext(mock.patch.object(notify, 'Thread', SyncThread))
        self.item = Download.objects.create(title='Framework actual', section='framework',
                                            file=ContentFile(b'zip', name='Plantilla 1.zip'))

    def get(self, url):
        self.client.force_login(self.reader)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.get(url)
            if response.status_code == 200:
                b''.join(response.streaming_content)
        return response

    def sent(self):
        return [call.args for call in self.post.call_args_list]

    def test_framework_download_from_each_path_sends_one(self):
        for path in ['/downloads/' + self.item.slug, '/downloads/framework/latest']:
            self.post.reset_mock()
            self.assertEqual(self.get(path).status_code, 200)
            self.assertEqual(self.sent(), [('https://ntfy.invalid', 'test-topic', 'Athena: descarga de plantilla',
                                            f'reader descargó Framework actual (Plantilla 1.zip)\n{path}')])

    def test_other_section_and_404_send_none(self):
        other = Download.objects.create(title='Paquete', section='packages', file=ContentFile(b'p', name='p.zip'))
        self.assertEqual(self.get('/downloads/' + other.slug).status_code, 200)
        self.assertEqual(DownloadEvent.objects.filter(download=other).count(), 1)  # Still logged.
        self.assertEqual(self.get('/downloads/missing').status_code, 404)
        self.item.file.storage.delete(self.item.file.name)
        self.assertEqual(self.get('/downloads/framework/latest').status_code, 404)
        self.assertEqual(self.sent(), [])

    def test_portal_and_admin_sign_in_send_one_each_and_failures_none(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post('/accounts/login/', {'username': 'reader', 'password': 'wrong password'}).status_code, 200)
        self.assertEqual(self.sent(), [])
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post('/accounts/login/', {'username': 'reader', 'password': 'a long test password'}).status_code, 302)
        self.assertEqual(self.sent(), [('https://ntfy.invalid', 'test-topic', 'Athena: inicio de sesión',
                                        'reader (Ana Pérez) inició sesión')])
        self.post.reset_mock()
        self.client.logout()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post('/admin/login/', {'username': 'staffer', 'password': 'a long test password'}).status_code, 302)
        self.assertEqual(self.sent(), [('https://ntfy.invalid', 'test-topic', 'Athena: inicio de sesión', 'staffer inició sesión')])

    def test_no_topic_file_sends_nothing_and_logs_once(self):
        notify._off_logged = False
        with override_settings(ATHENA_NTFY_TOPIC_FILE='/nonexistent/athena-ntfy-topic'):
            with self.assertLogs('athena.notify', 'WARNING') as logs:
                self.assertEqual(self.get('/downloads/framework/latest').status_code, 200)
            with self.assertNoLogs('athena.notify'):
                self.assertEqual(self.get('/downloads/framework/latest').status_code, 200)
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(self.sent(), [])

    def test_sender_error_keeps_the_response_and_logs_only_the_type(self):
        self.post.side_effect = OSError('https://ntfy.invalid/test-topic refused')
        with self.assertLogs('athena.notify', 'WARNING') as logs:
            response = self.get('/downloads/framework/latest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(logs.output, ['WARNING:athena.notify:ntfy notification failed: OSError'])
        self.post.side_effect = None

    def test_thread_start_error_keeps_the_sign_in(self):
        with mock.patch.object(SyncThread, 'start', side_effect=RuntimeError('no thread')), self.assertLogs('athena.notify', 'WARNING'):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post('/accounts/login/', {'username': 'reader', 'password': 'a long test password'})
        self.assertEqual(response.status_code, 302)

    def test_rolled_back_transaction_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(RuntimeError), transaction.atomic():
                notify.send('Athena: inicio de sesión', 'reader inició sesión')
                raise RuntimeError('rollback')
        self.assertEqual(callbacks, [])
        self.assertEqual(self.sent(), [])

    def test_post_sends_the_body_with_title_in_the_query(self):
        conn = mock.MagicMock()
        conn.getresponse.return_value.status = 200
        with mock.patch('http.client.HTTPSConnection', return_value=conn) as https:
            REAL_POST('https://ntfy.invalid/base/', 'test-topic', 'Athena: inicio de sesión', 'reader')
        https.assert_called_once_with('ntfy.invalid', timeout=5)
        conn.request.assert_called_once_with(
            'POST', '/base/test-topic?title=Athena%3A+inicio+de+sesi%C3%B3n&priority=default', b'reader')
        conn.close.assert_called_once()

