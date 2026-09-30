"""Private PDF cache and one bounded renderer for the single-VPS deployment."""
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from django.conf import settings


class ExportBusy(Exception):
    pass


def cached_export(article):
    from .views import article_html
    from .images import referenced_image_ids
    from .models import ManagedImage
    origin = settings.PUBLIC_ORIGIN
    base_url = f'{origin}/content/{article.slug}.pdf'
    html = article_html(article, origin)
    image_versions = {str(image.pk): image.sha256 for image in ManagedImage.objects.filter(
        pk__in=referenced_image_ids(article.body)).order_by('pk')}
    version = hashlib.sha256((html + base_url + json.dumps(image_versions, sort_keys=True)).encode()).hexdigest()
    root = settings.DATA_DIR / 'pdf-cache'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = root / f'{article.pk}-{version}.pdf'
    try:
        return target.open('rb')
    except FileNotFoundError:
        pass
    # ponytail: one renderer per VPS; use a job queue only if export volume requires parallel rendering.
    with (root / 'render.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ExportBusy from error
        if target.exists():
            return target.open('rb')
        with tempfile.TemporaryDirectory(dir=root) as scratch:
            output = Path(scratch) / 'article.pdf'
            try:
                subprocess.run([sys.executable, '-m', 'athena.pdf_export', str(output)],
                               input=json.dumps({'html': html, 'base_url': base_url, 'image_versions': image_versions}), text=True,
                               cwd=settings.BASE_DIR / 'server', stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, timeout=30, check=True)
            except (subprocess.SubprocessError, OSError) as error:
                logging.getLogger(__name__).warning('PDF renderer failed: %s', type(error).__name__)
                raise ExportBusy from error
            if not output.is_file():
                raise ExportBusy
            os.replace(output, target)
        for old in root.glob(f'{article.pk}-*.pdf'):
            if old != target:
                old.unlink(missing_ok=True)
        return target.open('rb')


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (25 * 1024 * 1024, 25 * 1024 * 1024))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'athena.settings')
    import django
    django.setup()
    from weasyprint import HTML
    from .views import pdf_fetcher
    source = json.load(sys.stdin)
    HTML(string=source['html'], base_url=source['base_url'],
         url_fetcher=pdf_fetcher(source.get('image_versions'))).write_pdf(sys.argv[1])
