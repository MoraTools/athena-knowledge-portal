#!/usr/bin/env python3
"""Create consistent SQLite backups, including article PDFs, and retain 14 days."""
import os
import sqlite3
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
