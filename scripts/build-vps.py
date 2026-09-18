"""Prepare reader assets without overwriting the approved migration source in dist."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for required in ['README.md', '_sidebar.md', 'search-index.json', 'catalog.json', 'search.md', 'downloads.md']:
    if not (root / 'dist' / required).is_file():
        raise SystemExit(f'Missing approved migration source: dist/{required}. Restore the migration bundle first.')
for source, target in [('dompurify/dist/purify.min.js', 'purify.min.js'), ('docsify/lib/docsify.min.js', 'docsify.min.js')]:
    shutil.copy2(root / 'node_modules' / source, root / 'dist/vendor' / target)
print('VPS reader assets prepared. Existing article and download data preserved.')
