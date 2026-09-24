#!/usr/bin/env python3
"""Create consistent SQLite backups, including article PDFs, and retain 14 days; mirror uploaded downloads."""
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.umask(0o077)
root = Path('/var/backups/athena')
root.mkdir(parents=True, exist_ok=True)
now = datetime.now(timezone.utc)
target = root / (now.strftime('%Y%m%dT%H%M%S') + '.sqlite3')
with sqlite3.connect('file:/var/lib/athena/athena.sqlite3?mode=ro', uri=True) as source, sqlite3.connect(target) as backup:
    source.backup(backup)
    if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise RuntimeError('Backup integrity check failed.')
for file in root.glob('*.sqlite3'):
    if file.stat().st_mtime < (now - timedelta(days=14)).timestamp():
        file.unlink()
print(f'Created verified backup: {target.name}')
# Downloads are files, not database rows: keep one mirror of the current set (no history).
media = Path('/var/lib/athena/media')
if media.is_dir():
    try:
        subprocess.run(['rsync', '-a', '--delete', f'{media}/', f'{root}/media/'], check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Media backup failed: {error}')
    print(f'Mirrored downloads: {root}/media')
