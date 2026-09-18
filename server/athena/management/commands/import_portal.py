import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from athena.models import Article


class Command(BaseCommand):
    help = 'Import approved dist content once, preserving routes. Existing database articles are never overwritten.'

    def add_arguments(self, parser):
        parser.add_argument('--source', default=str(settings.BASE_DIR / 'dist'))

    @transaction.atomic
    def handle(self, *args, **options):
        source = Path(options['source']).resolve()
        index = json.loads((source / 'search-index.json').read_text(encoding='utf-8-sig'))
        count = 0
        for entry in index:
            if not entry['route'].startswith('#/content/'):
                continue
            slug = entry['route'].removeprefix('#/content/')
            if not re.fullmatch('[a-z0-9-]+', slug):
                raise CommandError('Invalid article route in import.')
            if Article.objects.filter(slug=slug).exists():
                continue
            raw = (source / 'content' / f'{slug}.md').read_text(encoding='utf-8-sig')
            match = re.match(r'<!--\s*athena:\s*(\{.*?\})\s*-->\s*', raw, re.S)
            if not match:
                raise CommandError(f'Missing metadata: {slug}')
            meta = json.loads(match[1])
            body = raw[match.end():]
            body = re.sub(r'<p class="source-note">.*?</p>\s*', '', body, flags=re.S)
            body = re.sub(r'<p><a class="pdf-link".*?</p>\s*', '', body, flags=re.S)
            article = Article(slug=slug, title=entry['title'], kind=entry['kind'], summary=entry['summary'],
                              author=entry['author'], date=entry['date'], tags=entry['tags'], body=body,
                              published=True, status=meta.get('status', ''), url=meta.get('url', ''),
                              download_file=meta.get('downloadFile', ''))
            if entry.get('pdf'):
                file = (source / entry['pdf'].lstrip('/')).resolve()
                if not file.is_relative_to(source / 'pdf'):
                    raise CommandError('Invalid PDF path in import.')
                article.pdf, article.pdf_name = file.read_bytes(), file.name
            article.full_clean()
            article.save()
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Imported {count} articles; {Article.objects.count()} total.'))
