"""Prepare reader assets without overwriting the approved migration source in dist."""
import re
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for required in ['README.md', '_sidebar.md', 'search-index.json', 'catalog.json', 'search.md', 'downloads.md']:
    if not (root / 'dist' / required).is_file():
        raise SystemExit(f'Missing approved migration source: dist/{required}. Restore the migration bundle first.')
for source, target in [('dompurify/dist/purify.min.js', 'purify.min.js'), ('docsify/dist/docsify.min.js', 'docsify.min.js'),
                       ('marked/lib/marked.umd.js', 'marked.umd.js')]:
    shutil.copy2(root / 'node_modules' / source, root / 'dist/vendor' / target)
# Athena overrides this theme's content, heading and table selectors. Its web-font @import is dropped: the CSP blocks it
# and Athena ships its own fonts.
theme = (root / 'node_modules/docsify/lib/themes/vue.css').read_text(encoding='utf-8')
theme = re.sub(r'^@import url\([^)]*\);', '', theme).replace('#34495e', '#ffb900').replace('#2c3e50', '#fff')
assert '@import' not in theme, 'vue.css still imports a stylesheet'
(root / 'dist/vendor/vue.css').write_text(theme, encoding='utf-8')
print('VPS reader assets prepared. Existing article and download data preserved.')
