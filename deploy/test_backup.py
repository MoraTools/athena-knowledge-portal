"""Local backup checks with an rsync stand-in; no VPS paths or private files are used."""
import errno
import hashlib
import io
import os
import select
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import backup


def mirror(command, check):
    assert command[:4] == ['rsync', '-a', '--delete', '--checksum'] and check
    shutil.copytree(command[-2], command[-1], symlinks=True, dirs_exist_ok=True)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.data = self.work / 'data'
        self.root = self.work / 'backups'
        (self.data / 'media/downloads').mkdir(parents=True)
        (self.data / 'media/article-images').mkdir()
        self.download = self.data / 'media/downloads/original.zip'
        self.download.write_bytes(b'disposable download fixture')
        self.image = self.data / ('media/article-images/' + 'a' * 32 + '.png')
        self.image.write_bytes(b'disposable image fixture')
        with sqlite3.connect(self.data / 'athena.sqlite3') as database:
            database.executescript('CREATE TABLE athena_download (file TEXT, size INTEGER, sha256 TEXT);'
                                   'CREATE TABLE athena_managedimage (id TEXT, format TEXT);')
            data = self.download.read_bytes()
            database.execute('INSERT INTO athena_download VALUES (?, ?, ?)',
                             ('downloads/original.zip', len(data), hashlib.sha256(data).hexdigest()))
            database.execute('INSERT INTO athena_managedimage VALUES (?, ?)', ('a' * 32, 'png'))

    def run_backup(self, sync=mirror):
        with patch.object(backup.subprocess, 'run', sync), redirect_stdout(io.StringIO()):
            return backup.create_backup(self.data, self.root)

    def assert_restorable(self, directory=None):
        directory = directory or (self.root / 'current').resolve()
        restore = Path(self.enterContext(tempfile.TemporaryDirectory()))
        shutil.copy2(directory / 'database.sqlite3', restore / 'athena.sqlite3')
        shutil.copytree(directory / 'media', restore / 'media')
        with sqlite3.connect(restore / 'athena.sqlite3') as database:
            self.assertEqual(database.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            for name, size, digest in database.execute('SELECT file, size, sha256 FROM athena_download'):
                data = (restore / 'media' / name).read_bytes()
                self.assertEqual((size, digest), (len(data), hashlib.sha256(data).hexdigest()))
            for identity, fmt in database.execute('SELECT id, format FROM athena_managedimage'):
                self.assertTrue((restore / 'media/article-images' / f'{identity}.{fmt}').is_file())

    def replace_and_delete_live_files(self):
        replacement = self.data / 'media/downloads/replacement.zip'
        replacement.write_bytes(b'new download fixture')
        data = replacement.read_bytes()
        with sqlite3.connect(self.data / 'athena.sqlite3', timeout=1) as database:
            database.execute('BEGIN IMMEDIATE')
            database.execute('UPDATE athena_download SET file=?, size=?, sha256=?',
                             ('downloads/replacement.zip', len(data), hashlib.sha256(data).hexdigest()))
            database.execute('DELETE FROM athena_managedimage')
        self.download.unlink()
        self.image.unlink()

    def test_concurrent_replacement_and_cleanup_leave_a_restorable_snapshot(self):
        def during_copy(command, check):
            self.replace_and_delete_live_files()  # This transaction must succeed after the staging barrier ends.
            mirror(command, check)

        target = self.run_backup(during_copy)
        self.assert_restorable()
        self.assertEqual((self.root / 'media/downloads/original.zip').read_bytes(), b'disposable download fixture')
        self.assertEqual(target.read_bytes(), (self.root / 'current/database.sqlite3').read_bytes())
        self.assertFalse(self.download.exists())
        previous = (self.root / 'current').resolve()

        def next_copy(command, check):
            self.assertIn(f'--link-dest={previous}/media', command)
            mirror(command, check)

        self.run_backup(next_copy)
        self.assert_restorable()
        self.assertFalse((self.root / 'media/downloads/original.zip').exists())
        self.assertEqual(len(list(self.root.glob('.snapshot-*'))), 1)
        self.assertEqual(len(list(self.root.glob('*.sqlite3'))), 2)

    def test_failed_copy_and_pointer_publish_keep_previous_current(self):
        self.run_backup()
        previous = os.readlink(self.root / 'current')

        def fail_copy(command, check):
            Path(command[-1]).mkdir()
            (Path(command[-1]) / 'partial').write_bytes(b'partial')
            raise subprocess.CalledProcessError(1, command)

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_backup(fail_copy)
        self.assertEqual(os.readlink(self.root / 'current'), previous)
        real_replace = os.replace

        def fail_publish(source, destination):
            if Path(destination) == self.root / 'current':
                raise OSError('fixture publication failure')
            return real_replace(source, destination)

        with patch.object(backup.os, 'replace', fail_publish), self.assertRaises(OSError):
            self.run_backup()
        self.assertEqual(os.readlink(self.root / 'current'), previous)
        failed = False

        def fail_alias(source, destination):
            nonlocal failed
            if Path(destination) == self.root / 'media' and not failed:
                failed = True
                raise OSError('fixture alias publication failure')
            return real_replace(source, destination)

        with patch.object(backup.os, 'replace', fail_alias), self.assertRaises(OSError):
            self.run_backup()
        self.assertEqual(os.readlink(self.root / 'current'), previous)
        self.assert_restorable()
        self.assertEqual(len(list(self.root.glob('*.sqlite3'))), 1)
        self.assertFalse(list(self.root.glob('.pending-*')))

    def test_legacy_mirror_upgrade_rolls_back_on_late_publish_failure(self):
        (self.root / 'media').mkdir(parents=True)
        (self.root / 'media/legacy').write_bytes(b'old mirror fixture')
        real_replace = os.replace

        def fail_alias(source, destination):
            if Path(destination) == self.root / 'media':
                raise OSError('fixture alias publication failure')
            return real_replace(source, destination)

        with patch.object(backup.os, 'replace', fail_alias), self.assertRaises(OSError):
            self.run_backup()
        self.assertFalse((self.root / 'current').exists())
        self.assertFalse((self.root / 'media').is_symlink())
        self.assertEqual((self.root / 'media/legacy').read_bytes(), b'old mirror fixture')
        self.run_backup()
        self.assertTrue((self.root / 'media').is_symlink())
        self.assertFalse((self.root / '.legacy-media').exists())
        self.assert_restorable()

    def test_base_exception_after_publication_keeps_complete_current_and_history(self):
        self.run_backup()
        real_replace = os.replace

        def interrupt(source, destination):
            real_replace(source, destination)
            if Path(destination) == self.root / 'current':
                raise KeyboardInterrupt('fixture interruption')

        with patch.object(backup.os, 'replace', interrupt), self.assertRaises(KeyboardInterrupt):
            self.run_backup()
        self.assert_restorable()
        self.assertEqual(len(list(self.root.glob('*.sqlite3'))), 2)
        self.run_backup()
        self.assertEqual(len(list(self.root.glob('.snapshot-*'))), 1)

    def worker(self, mode):
        source = '''import os, shutil, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import backup
mode = sys.argv[4]
def mirror(command, check):
    if mode == 'pause':
        print('copy-start', flush=True)
        sys.stdin.readline()
    shutil.copytree(command[-2], command[-1], symlinks=True, dirs_exist_ok=True)
backup.subprocess.run = mirror
if mode == 'exit-after-current':
    original_replace = os.replace
    def replace(source, destination):
        original_replace(source, destination)
        if Path(destination).name == 'current':
            os._exit(73)
    backup.os.replace = replace
print('started', flush=True)
sys.stdin.readline()
backup.create_backup(Path(sys.argv[2]), Path(sys.argv[3]))
'''
        process = subprocess.Popen([sys.executable, '-c', source, str(Path(__file__).parent), str(self.data),
                                    str(self.root), mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_worker, process)
        self.assertTrue(select.select([process.stdout], [], [], 10)[0], 'Backup process did not start')
        self.assertEqual(process.stdout.readline().strip(), 'started')
        process.stdin.write('\n')
        process.stdin.flush()
        return process

    @staticmethod
    def stop_worker(process):
        if process.poll() is None:
            process.kill()
        process.communicate()

    def wait_for_copy(self, process):
        self.assertTrue(select.select([process.stdout], [], [], 10)[0], 'Backup did not reach media copy')
        self.assertEqual(process.stdout.readline().strip(), 'copy-start')

    def test_concurrent_backup_runs_are_serialized(self):
        first = self.worker('pause')
        self.wait_for_copy(first)
        second = self.worker('pause')
        self.assertFalse(select.select([second.stdout], [], [], 0.2)[0], 'Second backup bypassed the process lock')
        output, errors = first.communicate('\n', timeout=10)
        self.assertEqual(first.returncode, 0, errors)
        self.wait_for_copy(second)
        output, errors = second.communicate('\n', timeout=10)
        self.assertEqual(second.returncode, 0, errors)
        self.assert_restorable()
        self.assertEqual(len(list(self.root.glob('*.sqlite3'))), 2)

    def test_process_exit_before_and_after_current_publication_recovers(self):
        self.run_backup()
        previous = os.readlink(self.root / 'current')
        process = self.worker('pause')
        self.wait_for_copy(process)
        process.kill()
        process.communicate(timeout=10)
        self.assertEqual(os.readlink(self.root / 'current'), previous)
        self.assertTrue(list(self.root.glob('.pending-*')))
        self.assertTrue(list(self.data.glob('.athena-backup-*')))
        self.assert_restorable()
        self.replace_and_delete_live_files()
        process = self.worker('exit-after-current')
        output, errors = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 73, errors)
        self.assertNotEqual(os.readlink(self.root / 'current'), previous)
        self.assert_restorable()
        self.run_backup()
        self.assert_restorable()
        self.assertFalse(list(self.root.glob('.pending-*')))
        self.assertFalse(list(self.data.glob('.athena-backup-*')))
        self.assertEqual(len(list(self.root.glob('.snapshot-*'))), 1)

    def test_missing_media_and_unavailable_hardlinks_do_not_publish(self):
        self.run_backup()
        previous = os.readlink(self.root / 'current')
        with patch.object(backup.os, 'link', side_effect=OSError(errno.EXDEV, 'cross-device fixture')):
            with self.assertRaisesRegex(RuntimeError, 'share a filesystem'):
                self.run_backup()
        self.download.unlink()
        with self.assertRaisesRegex(RuntimeError, 'media is missing'):
            self.run_backup()
        self.assertEqual(os.readlink(self.root / 'current'), previous)
        self.assert_restorable()

    def test_database_history_retains_fourteen_days(self):
        self.run_backup()
        old, recent = self.root / 'old.sqlite3', self.root / 'recent.sqlite3'
        for path, age in [(old, 15), (recent, 13)]:
            path.write_bytes(b'disposable history fixture')
            timestamp = (datetime.now(timezone.utc) - timedelta(days=age)).timestamp()
            os.utime(path, (timestamp, timestamp))
        self.run_backup()
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())


if __name__ == '__main__':
    unittest.main()
