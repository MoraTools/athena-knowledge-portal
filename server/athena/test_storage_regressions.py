import hashlib
import io
import os
import select
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase, override_settings

from .models import Download


class DownloadStorageTests(TransactionTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.root / 'media'))

    def test_failed_insert_and_replacement_remove_only_new_file(self):
        item = Download.objects.create(title='Original', file=ContentFile(b'old', name='same.zip'))
        other = Download.objects.create(title='Other', file=ContentFile(b'other', name='other.zip'))
        old_path = Path(item.file.path)
        with self.assertRaises(IntegrityError):
            Download.objects.create(title='Duplicate', slug=item.slug, file=ContentFile(b'new', name='duplicate.zip'))
        self.assertFalse((self.root / 'media/downloads/duplicate.zip').exists())
        item.slug = other.slug
        item.file = ContentFile(b'replacement', name='replacement.zip')
        with self.assertRaises(IntegrityError):
            item.save()
        self.assertFalse((self.root / 'media/downloads/replacement.zip').exists())
        self.assertEqual(old_path.read_bytes(), b'old')
        item.refresh_from_db()
        self.assertEqual((item.slug, item.sha256), ('same-zip', hashlib.sha256(b'old').hexdigest()))

    def test_failed_upload_can_be_retried_and_old_cleanup_failure_keeps_new_file(self):
        original = Download.objects.create(title='Original', file=ContentFile(b'old', name='same.zip'))
        item = Download(title='Retry', slug=original.slug, file=ContentFile(b'retry', name='retry.zip'))
        with self.assertRaises(IntegrityError):
            item.save()
        self.assertFalse(item.file._committed)
        item.slug = 'retry-zip'
        item.save()
        self.assertEqual(Path(item.file.path).read_bytes(), b'retry')
        storage, old_path = item.file.storage, Path(item.file.path)
        item.file = ContentFile(b'replacement', name='new.zip')
        with patch.object(storage, 'delete', side_effect=OSError('fixture cleanup failure')), self.assertLogs(level='ERROR'):
            item.save()
        item.refresh_from_db()
        self.assertEqual(item.file.read(), b'replacement')
        self.assertTrue(old_path.exists())

    def test_replacement_waits_for_outer_commit_and_rollback_keeps_old_file(self):
        item = Download.objects.create(title='Original', file=ContentFile(b'old', name='same.zip'))
        old_path = Path(item.file.path)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                item.file = ContentFile(b'rolled back', name='rolled-back.zip')
                item.save()
                self.assertTrue(old_path.is_file())
                raise RuntimeError('rollback')
        item.refresh_from_db()
        self.assertEqual(item.file.read(), b'old')
        # Django has no outer-rollback callback; the unreferenced new file is safe but remains on disk.
        self.assertEqual((self.root / 'media/downloads/rolled-back.zip').read_bytes(), b'rolled back')
        with transaction.atomic():
            item.file = ContentFile(b'new', name='new.zip')
            item.save()
            self.assertTrue(old_path.is_file())
        self.assertFalse(old_path.exists())
        self.assertEqual((item.slug, item.size, item.sha256), ('same-zip', 3, hashlib.sha256(b'new').hexdigest()))

    def test_concurrent_same_name_uploads_succeed_with_distinct_slugs(self):
        # Use an on-disk copy: SQLite's shared in-memory test DB does not wait on write locks.
        with sqlite3.connect(self.root / 'athena.sqlite3') as target:
            connection.connection.backup(target)
        source = '''import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'athena.settings'
django.setup()
from django.core.files.base import ContentFile
from django.db.models.query import QuerySet
from athena.models import Download
original_exists = QuerySet.exists
def paused_exists(query):
    result = original_exists(query)
    if query.model is Download and sys.argv[1] == 'first' and not result:
        print('slug-selected', flush=True)
        sys.stdin.readline()
    return result
QuerySet.exists = paused_exists
if sys.argv[1] != 'first':
    print('started', flush=True)
item = Download.objects.create(title=sys.argv[1], file=ContentFile(sys.argv[1].encode(), name='same.zip'))
print(item.slug, flush=True)
'''
        env = {**os.environ, 'ATHENA_DATA_DIR': str(self.root), 'ATHENA_DEBUG': '1',
               'ATHENA_SECRET_KEY': 'local-storage-regression'}
        processes = []
        try:
            first = subprocess.Popen([sys.executable, '-c', source, 'first'], cwd=settings.BASE_DIR / 'server', env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(first)
            self.assertTrue(select.select([first.stdout], [], [], 10)[0], 'First upload did not take the lock')
            self.assertEqual(first.stdout.readline().strip(), 'slug-selected')
            second = subprocess.Popen([sys.executable, '-c', source, 'second'], cwd=settings.BASE_DIR / 'server', env=env,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(second)
            self.assertTrue(select.select([second.stdout], [], [], 10)[0], 'Second upload did not start')
            self.assertEqual(second.stdout.readline().strip(), 'started')
            self.assertIsNone(second.poll())
            output, errors = first.communicate('\n', timeout=15)
            self.assertEqual(first.returncode, 0, errors)
            self.assertEqual(output.strip(), 'same-zip')
            output, errors = second.communicate(timeout=15)
            self.assertEqual(second.returncode, 0, errors)
            self.assertEqual(output.strip(), 'same-zip-2')
            with sqlite3.connect(self.root / 'athena.sqlite3') as database:
                rows = database.execute('SELECT slug, file, size, sha256 FROM athena_download ORDER BY slug').fetchall()
            self.assertEqual([row[0] for row in rows], ['same-zip', 'same-zip-2'])
            self.assertEqual(len(list((self.root / 'media/downloads').iterdir())), 2)
            for slug, name, size, digest in rows:
                data = (self.root / 'media' / name).read_bytes()
                self.assertEqual((size, digest), (len(data), hashlib.sha256(data).hexdigest()))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_import_rejects_file_and_directory_links_and_keeps_valid_reruns(self):
        source = self.root / 'source'
        (source / 'packages/nested').mkdir(parents=True)
        (source / 'packages/nested/good.jar').write_bytes(b'package fixture')
        (source / 'framework.zip').write_bytes(b'framework fixture')
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'private.jar').write_bytes(b'disposable outside fixture')
        (source / 'packages/linked.jar').symlink_to(outside / 'private.jar')
        (source / 'packages/linked-directory').symlink_to(outside, target_is_directory=True)
        (source / 'packages/inside-link.jar').symlink_to(source / 'packages/nested/good.jar')
        output, errors = io.StringIO(), io.StringIO()
        call_command('import_downloads', str(source), stdout=output, stderr=errors)
        self.assertIn('2 added, 0 already present, 3 ignored.', output.getvalue())
        self.assertEqual(errors.getvalue().count('Ignored (symbolic link)'), 3)
        self.assertEqual(set(Download.objects.values_list('title', 'section')),
                         {('framework.zip', 'framework'), ('good.jar', 'packages')})
        self.assertEqual(Download.objects.get(title='good.jar').file.read(), b'package fixture')
        output = io.StringIO()
        call_command('import_downloads', str(source), stdout=output, stderr=io.StringIO())
        self.assertIn('0 added, 2 already present, 3 ignored.', output.getvalue())
        self.assertEqual(len(list((self.root / 'media/downloads').iterdir())), 2)
        alias = self.root / 'source-alias'
        alias.symlink_to(source, target_is_directory=True)
        with self.assertRaises(CommandError):
            call_command('import_downloads', str(alias), stdout=io.StringIO())
