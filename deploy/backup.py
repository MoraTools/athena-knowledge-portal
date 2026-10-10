#!/usr/bin/env python3
"""Keep 14 days of SQLite snapshots and one complete current database/media pair."""
import fcntl
import os
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


def media_pointer(root):
    pointer = root / ('.media-' + uuid.uuid4().hex)
    pointer.symlink_to('current/media')
    os.replace(pointer, root / 'media')


def recover(root, data):
    current = root / 'current'
    if current.exists() and not current.is_symlink():
        raise RuntimeError('Backup current must be a symbolic link.')
    active = current.resolve() if current.is_symlink() else None
    legacy = root / '.legacy-media'
    if legacy.exists():
        if active and active.is_dir():
            media_pointer(root)
            shutil.rmtree(legacy)
        else:
            (root / 'media').unlink(missing_ok=True)
            legacy.rename(root / 'media')
    for pattern in ('.pending-*', '.snapshot-*'):
        for path in root.glob(pattern):
            if path != active:
                shutil.rmtree(path)
    for pattern in ('.current-*', '.media-*'):
        for path in root.glob(pattern):
            path.unlink()
    for path in data.glob('.athena-backup-*'):
        shutil.rmtree(path)


def check_media(database, media):
    with closing(sqlite3.connect(database)) as snapshot:
        names = [row[0] for row in snapshot.execute('SELECT file FROM athena_download')]
        names += [f'article-images/{row[0]}.{row[1]}' for row in snapshot.execute('SELECT id, format FROM athena_managedimage')]
    for name in names:
        path = media / name
        if not path.resolve().is_relative_to(media.resolve()) or not path.is_file():
            raise RuntimeError(f'Backup media is missing or unsafe: {name}')


def create_backup(data=Path('/var/lib/athena'), root=Path('/var/backups/athena')):
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        recover(root, data)
        now = datetime.now(timezone.utc)
        target = root / (now.strftime('%Y%m%dT%H%M%S%f') + '.sqlite3')
        pending = Path(tempfile.mkdtemp(prefix='.pending-', dir=root))
        generation = root / ('.snapshot-' + uuid.uuid4().hex)
        published = False
        history_written = False
        try:
            # Hardlinks keep immutable media alive after deletion, without holding writers during rsync.
            with tempfile.TemporaryDirectory(prefix='.athena-backup-', dir=data) as temporary:
                staged_media = Path(temporary) / 'media'
                staged_media.mkdir()
                with closing(sqlite3.connect(f'file:{data}/athena.sqlite3?mode=rw', uri=True, timeout=20)) as barrier:
                    barrier.execute('BEGIN IMMEDIATE')
                    try:
                        # backup() on the connection with the write transaction would deadlock.
                        with closing(sqlite3.connect(f'file:{data}/athena.sqlite3?mode=ro', uri=True)) as source:
                            with closing(sqlite3.connect(pending / 'database.sqlite3')) as snapshot:
                                source.backup(snapshot)
                                if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                                    raise RuntimeError('Backup integrity check failed.')
                        if (data / 'media').is_dir():
                            try:
                                shutil.copytree(data / 'media', staged_media, copy_function=os.link,
                                                symlinks=True, dirs_exist_ok=True)
                            except shutil.Error as error:
                                raise RuntimeError(f'Media snapshot failed; media and its staging directory must share a filesystem: {error}') from error
                    finally:
                        barrier.rollback()
                command = ['rsync', '-a', '--delete', '--checksum']
                if (root / 'current/media').is_dir():
                    command.append(f'--link-dest={(root / "current/media").resolve()}')
                subprocess.run(command + [f'{staged_media}/', f'{pending}/media/'], check=True)
            check_media(pending / 'database.sqlite3', pending / 'media')
            pending.rename(generation)
            os.link(generation / 'database.sqlite3', target)
            history_written = True
            current = root / 'current'
            previous = os.readlink(current) if current.is_symlink() else None
            pointer = root / ('.current-' + uuid.uuid4().hex)
            pointer.symlink_to(generation.name)
            os.replace(pointer, current)
            try:
                media = root / 'media'
                if media.is_dir() and not media.is_symlink():
                    media.rename(root / '.legacy-media')
                media_pointer(root)
            except Exception:
                if previous is None:
                    current.unlink()
                else:
                    pointer.symlink_to(previous)
                    os.replace(pointer, current)
                if (root / '.legacy-media').exists():
                    media.unlink(missing_ok=True)
                    (root / '.legacy-media').rename(media)
                raise
            published = True
            recover(root, data)
            for path in root.glob('*.sqlite3'):
                if path.stat().st_mtime < (now - timedelta(days=14)).timestamp():
                    path.unlink()
            print(f'Created verified backup: {target.name}')
            print(f'Current database and media: {root}/current')
            return target
        finally:
            if pending.exists():
                shutil.rmtree(pending)
            if not published and (root / 'current').resolve() != generation:
                if history_written:
                    target.unlink(missing_ok=True)
                if generation.exists():
                    shutil.rmtree(generation)


if __name__ == '__main__':
    try:
        create_backup()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Backup failed: {error}')
