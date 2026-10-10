from concurrent.futures import ThreadPoolExecutor
import fcntl
import multiprocessing
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from .forms import permissions
from .images import ImageUploadBusy, MAX_BYTES, create_image
from .models import ApiKey, ManagedImage
from .test_images import picture


def capacity_worker(root, barrier, release, active, peak, counters, results):
    def convert(upload, user):
        with counters:
            active.value += 1
            peak.value = max(peak.value, active.value)
        try:
            if not release.wait(15):
                raise RuntimeError('Conversion was not released')
        finally:
            with counters:
                active.value -= 1

    def request():
        barrier.wait(timeout=10)
        try:
            create_image(SimpleNamespace(size=1), None)
        except ImageUploadBusy:
            results.put('busy')
        else:
            results.put('converted')

    with override_settings(DATA_DIR=Path(root)), patch('athena.images._create_image', side_effect=convert):
        with ThreadPoolExecutor(max_workers=4) as threads:
            list(threads.map(lambda _: request(), range(4)))


class ImageCapacityTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(DATA_DIR=self.root))

    def test_two_workers_four_threads_have_one_conversion_peak(self):
        # Match Gunicorn's concurrency with small counters, without allocating decoded image buffers.
        context = multiprocessing.get_context('fork')
        barrier, release = context.Barrier(8), context.Event()
        active, peak, counters = context.Value('i', 0), context.Value('i', 0), context.Lock()
        results = context.Queue()
        workers = [context.Process(target=capacity_worker, args=(
            self.root, barrier, release, active, peak, counters, results)) for _ in range(2)]
        try:
            for worker in workers:
                worker.start()
            self.assertEqual([results.get(timeout=10) for _ in range(7)], ['busy'] * 7)
            self.assertEqual((active.value, peak.value), (1, 1))
            release.set()
            self.assertEqual(results.get(timeout=10), 'converted')
            for worker in workers:
                worker.join(timeout=10)
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual((active.value, peak.value), (0, 1))
        finally:
            release.set()
            for worker in workers:
                if worker.is_alive():
                    worker.kill()
                if worker.pid:
                    worker.join(timeout=10)
            results.close()
            results.join_thread()

    def test_busy_request_does_not_read_upload_or_start_decoder(self):
        upload = Mock(size=1)
        with (self.root / 'image-upload.lock').open('a') as lock, patch('athena.images._create_image') as decode:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ImageUploadBusy):
                create_image(upload, None)
            upload.read.assert_not_called()
            decode.assert_not_called()

    def test_failed_conversion_releases_capacity(self):
        result = object()
        with patch('athena.images._create_image', side_effect=[ValidationError('Invalid image'), result]):
            with self.assertRaises(ValidationError):
                create_image(SimpleNamespace(size=1), None)
            self.assertIs(create_image(SimpleNamespace(size=1), None), result)

    def test_oversized_upload_keeps_validation_response_when_busy(self):
        with (self.root / 'image-upload.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ValidationError) as caught:
                create_image(SimpleNamespace(size=MAX_BYTES + 1), None)
            self.assertNotIsInstance(caught.exception, ImageUploadBusy)


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class ImageCapacityResponseTests(TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(DATA_DIR=self.root, MEDIA_ROOT=self.root / 'media'))
        self.editor = User.objects.create_user('capacity-editor', is_staff=True)
        self.editor.user_permissions.set(permissions(['athena.add_article']))
        key = ApiKey(user=self.editor, scope='articles', name='capacity')
        self.token = key.issue()
        key.save()
        self.client.force_login(self.editor)

    def test_browser_and_api_busy_responses_are_retryable_then_recover(self):
        for url, headers in [('/article-images/upload/', {}), ('/api/v1/article-images/', {
                'HTTP_AUTHORIZATION': 'Bearer ' + self.token})]:
            with self.subTest(url=url):
                before = ManagedImage.objects.count()
                files = list((self.root / 'media/article-images').glob('*'))
                with (self.root / 'image-upload.lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    response = self.client.post(url, {'file': picture()}, **headers)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response['Retry-After'], '2')
                    self.assertIn('otra imagen', response.json()['error'])
                    self.assertEqual(ManagedImage.objects.count(), before)
                    self.assertEqual(list((self.root / 'media/article-images').glob('*')), files)
                self.assertEqual(self.client.post(url, {'file': picture()}, **headers).status_code, 201)
                self.assertEqual(ManagedImage.objects.count(), before + 1)
