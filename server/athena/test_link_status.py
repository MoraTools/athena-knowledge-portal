import socket
import ssl
import tempfile
import threading
import time
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings

from . import link_status
from .forms import permissions
from .link_status import check, marked_links, refresh, statuses
from .models import Article

PUBLIC = '93.184.216.34'


def addresses(*ips):
    return lambda host, port, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port)) for ip in ips]


class FakeSocket:
    """A socket that answers every request with one fixed HTTP response."""

    def __init__(self, response):
        self.response = response
        self.sent = b''

    def sendall(self, data):
        self.sent += data

    def makefile(self, *args, **kwargs):
        return BytesIO(self.response)

    def close(self):
        pass


def answer(status, extra=''):
    return f'HTTP/1.1 {status} X\r\nContent-Length: 0\r\n{extra}\r\n'.encode()


class MarkedLinkTests(SimpleTestCase):
    def test_only_marked_http_links_without_repeats_at_most_20(self):
        body = ('<a class="open-demo" data-athena-status href="https://demo.test/a?b=1">A</a>'
                '<a href="https://not-marked.test/">B</a>'
                '<a data-athena-status="" href=" http://plain.test:8080/ ">C</a>'
                '<a data-athena-status href="https://demo.test/a?b=1">again</a>'
                '<a data-athena-status href="ftp://files.test/">D</a>'
                '<a data-athena-status href="javascript:alert(1)">E</a>'
                '<a data-athena-status href="/relative">F</a>'
                '<a data-athena-status href="https://bad-port.test:x/">G</a>'
                '<a data-athena-status href="https:///no-host">H</a>'
                '<a data-athena-status>I</a>'
                '<link data-athena-status href="https://link.test/">'
                '<img data-athena-status src="https://img.test/">')
        self.assertEqual(marked_links(body), ['https://demo.test/a?b=1', 'http://plain.test:8080/'])
        many = ''.join(f'<a data-athena-status href="https://d{n}.test/">x</a>' for n in range(30))
        self.assertEqual(marked_links(many), [f'https://d{n}.test/' for n in range(20)])
        self.assertEqual(marked_links('<p>No links</p>'), [])


class CheckTests(SimpleTestCase):
    def run_check(self, url, response=None, error=None, ips=(PUBLIC,)):
        self.sock = FakeSocket(response or b'')
        with patch('socket.getaddrinfo', addresses(*ips)), \
                patch('socket.create_connection', side_effect=error, return_value=self.sock) as self.connect, \
                patch('ssl.create_default_context') as context:
            context.return_value.wrap_socket.side_effect = lambda sock, server_hostname: sock
            self.tls = context.return_value.wrap_socket
            return check(url)

    def test_any_answer_below_500_is_online(self):
        for status in (200, 204, 302, 303, 401, 403, 404, 499):
            self.assertEqual(self.run_check('https://demo.test/', answer(status)), 'online', status)
        for status in (500, 502, 503, 504):
            self.assertEqual(self.run_check('https://demo.test/', answer(status)), 'offline', status)

    def test_one_get_to_the_checked_address_and_no_redirect_followed(self):
        state = self.run_check('https://demo.test/login?next=/', answer(302, 'Location: http://127.0.0.1/admin/\r\n'))
        self.assertEqual(state, 'online')
        self.connect.assert_called_once_with((PUBLIC, 443), timeout=5)
        self.tls.assert_called_once()
        self.assertEqual(self.tls.call_args.kwargs['server_hostname'], 'demo.test')
        self.assertEqual(self.sock.sent.count(b'HTTP/1.1'), 1)
        self.assertTrue(self.sock.sent.startswith(b'GET /login?next=/ HTTP/1.1\r\n'))
        self.assertIn(b'\r\nHost: demo.test\r\n', self.sock.sent)
        self.assertEqual(self.run_check('http://demo.test:8080', answer(200)), 'online')
        self.connect.assert_called_once_with((PUBLIC, 8080), timeout=5)
        self.tls.assert_not_called()
        self.assertIn(b'\r\nHost: demo.test:8080\r\n', self.sock.sent)

    def test_timeout_connection_tls_and_bad_answers_are_offline(self):
        for error in (TimeoutError(), ConnectionRefusedError(), OSError('unreachable'),
                      ssl.SSLCertVerificationError('expired')):
            self.assertEqual(self.run_check('https://demo.test/', error=error), 'offline', error)
        self.assertEqual(self.run_check('https://demo.test/', b'not http\r\n\r\n'), 'offline')
        self.assertEqual(self.run_check('https://demo.test/', b''), 'offline')
        with patch('socket.getaddrinfo', side_effect=socket.gaierror('no such host')):
            self.assertEqual(check('https://missing.test/'), 'offline')

    def test_tls_failure_is_offline(self):
        with patch('socket.getaddrinfo', addresses(PUBLIC)), \
                patch('socket.create_connection', return_value=FakeSocket(b'')), \
                patch('ssl.create_default_context') as context:
            context.return_value.wrap_socket.side_effect = ssl.SSLCertVerificationError('self-signed')
            self.assertEqual(check('https://demo.test/'), 'offline')

    def test_loopback_private_link_local_and_reserved_hosts_are_refused_without_a_request(self):
        for ip in ('127.0.0.1', '10.0.0.5', '172.16.0.1', '192.168.1.10', '169.254.169.254', '0.0.0.0', '240.0.0.1',
                   '100.64.0.1', '::1', 'fe80::1', 'fc00::1', '::ffff:127.0.0.1'):
            self.assertIsNone(self.run_check('http://inside.test/', answer(200), ips=(ip,)), ip)
            self.connect.assert_not_called()
        # One private address among the answers is enough to refuse the host.
        self.assertIsNone(self.run_check('http://mixed.test/', answer(200), ips=(PUBLIC, '127.0.0.1')))
        self.connect.assert_not_called()
        self.assertIsNone(check('http://127.0.0.1:8000/'))
        self.assertIsNone(check('http://[::1]/'))


class CacheTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(DATA_DIR=self.root))
        self.body = ('<a data-athena-status href="https://on.test/">A</a><a data-athena-status href="https://off.test/">B</a>'
                     '<a data-athena-status href="http://inside.test/">C</a>')
        self.states = {'https://on.test/': 'online', 'https://off.test/': 'offline', 'http://inside.test/': None}

    def test_results_stay_5_minutes_and_refused_links_are_left_out(self):
        with patch.object(link_status, 'check', side_effect=self.states.get) as checked, patch('time.time', return_value=1_800_000_000):
            first = statuses(self.body)
            self.assertEqual(first, {
                'https://on.test/': {'state': 'online', 'checked_at': '2027-01-15T08:00:00+00:00'},
                'https://off.test/': {'state': 'offline', 'checked_at': '2027-01-15T08:00:00+00:00'}})
            self.assertEqual(checked.call_count, 3)
        with patch.object(link_status, 'check', side_effect=self.states.get) as checked:
            with patch('time.time', return_value=1_800_000_000 + 299):
                self.assertEqual(statuses(self.body), first)
            checked.assert_not_called()
            with patch('time.time', return_value=1_800_000_000 + 300):
                later = statuses(self.body)
            self.assertEqual(checked.call_count, 3)
            self.assertEqual(later['https://on.test/'], {'state': 'online', 'checked_at': '2027-01-15T08:05:00+00:00'})
        self.assertEqual(statuses('<p>No marked links</p>'), {})
        self.assertEqual(sorted(path.suffix for path in (self.root / 'link-status').iterdir()), ['.json'] * 3)

    def test_one_check_of_a_url_at_a_time(self):
        calls = []

        def slow(url):
            calls.append(url)
            time.sleep(0.2)
            return 'online'
        with patch.object(link_status, 'check', slow):
            threads = [threading.Thread(target=refresh, args=('https://on.test/',)) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(calls, ['https://on.test/'])

    def test_a_slow_check_returns_the_last_result_with_its_time(self):
        body = '<a data-athena-status href="https://on.test/">A</a>'
        with patch.object(link_status, 'check', return_value='offline'), patch('time.time', return_value=time.time() - 600):
            old = statuses(body)
        release = threading.Event()
        started = threading.Event()

        def slow(url):
            started.set()
            release.wait(5)
            return 'online'
        try:
            with patch.object(link_status, 'check', slow), patch.object(link_status, 'TIMEOUT', -0.9):
                self.assertEqual(statuses(body), old)
                self.assertTrue(started.is_set())
                release.set()
                for _ in range(100):
                    if link_status.cached('https://on.test/')['state'] == 'online':
                        break
                    time.sleep(0.02)
                self.assertEqual(statuses(body)['https://on.test/']['state'], 'online')
        finally:
            release.set()


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class StatusEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root_user = User.objects.create_superuser('root')
        cls.editor = User.objects.create_user('editor', is_staff=True)
        cls.editor.user_permissions.set(permissions(['athena.change_article', 'athena.view_article']))
        cls.reader = User.objects.create_user('reader')
        cls.listed = User.objects.create_user('listed')
        cls.inactive = User.objects.create_user('inactive', is_active=False)

    def setUp(self):
        self.enterContext(override_settings(DATA_DIR=Path(self.enterContext(tempfile.TemporaryDirectory()))))
        self.checked = self.enterContext(patch.object(
            link_status, 'check', side_effect=lambda url: 'offline' if 'off' in url else 'online'))
        body = ('<!doctype html><body><a class="open-demo" data-athena-status href="https://on.test/">Abrir</a>'
                '<a data-athena-status href="https://off.test/">Abrir</a><a href="https://other.test/">Otro</a></body>')
        make = lambda slug, **fields: Article.objects.create(  # noqa: E731
            title=slug, slug=slug, summary='S', author='A', **{'format': 'html', 'body': body, 'published': True, **fields})
        make('demos')
        make('publica', is_public=True)
        make('borrador', published=False)
        make('privada', is_restricted=True).allowed_users.set([self.listed])
        make('sin-marcas', body='<!doctype html><body><a href="https://other.test/">Otro</a></body>')
        make('markdown', format='markdown', body='[x](https://on.test/)')

    def status(self, slug, user=None):
        self.client.logout()
        if user:
            self.client.force_login(user)
        return self.client.get(f'/article-status/{slug}/')

    def test_reader_gets_state_and_time_of_the_marked_links_only(self):
        response = self.status('demos', self.reader)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('no-store', response['Cache-Control'])
        data = response.json()
        self.assertEqual(set(data), {'https://on.test/', 'https://off.test/'})
        self.assertEqual(data['https://on.test/']['state'], 'online')
        self.assertEqual(data['https://off.test/']['state'], 'offline')
        self.assertEqual({key for item in data.values() for key in item}, {'state', 'checked_at'})
        self.assertRegex(data['https://on.test/']['checked_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$')
        self.assertEqual(self.checked.call_count, 2)
        self.assertEqual(self.status('demos', self.reader).json(), data)
        self.assertEqual(self.checked.call_count, 2, 'The second reader gets the cached result.')

    def test_same_access_as_the_article(self):
        cases = [
            ('demos', None, 404), ('demos', self.inactive, 404), ('publica', None, 200),
            ('borrador', None, 404), ('borrador', self.reader, 404), ('borrador', self.editor, 200),
            ('privada', None, 404), ('privada', self.reader, 404), ('privada', self.editor, 404),
            ('privada', self.listed, 200), ('privada', self.root_user, 200),
            ('markdown', self.reader, 404), ('no-existe', self.reader, 404),
        ]
        for slug, user, expected in cases:
            checks = self.checked.call_count
            response = self.status(slug, user)
            self.assertEqual(response.status_code, expected, (slug, user))
            self.assertEqual(self.client.get(f'/article-html/{slug}/').status_code, expected, (slug, user))
            if expected == 404:
                self.assertNotIn(b'on.test', response.content)
                self.assertEqual(self.checked.call_count, checks, 'No check for a reader who cannot read the article.')

    def test_no_marked_links_is_empty_and_only_get_is_allowed(self):
        response = self.status('sin-marcas', self.reader)
        self.assertEqual((response.status_code, response.json()), (200, {}))
        self.checked.assert_not_called()
        self.client.force_login(self.reader)
        for method in (self.client.post, self.client.put, self.client.delete, self.client.head):
            response = method('/article-status/demos/')
            self.assertEqual((response.status_code, response['Allow']), (405, 'GET'))
        self.checked.assert_not_called()
