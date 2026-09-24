from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from athena.models import Download, download_slug

# Top-level folders of the former OneDrive tree; files at the root are the current framework.
FOLDERS = {'packages': 'packages', 'ejercicios': 'exercises', 'versiones anteriores': 'previous'}


class Command(BaseCommand):
    help = 'Copy a download folder tree into Athena. Existing slugs are skipped, so reruns are safe.'

    def add_arguments(self, parser):
        parser.add_argument('directory')

    def handle(self, *args, **options):
        root = Path(options['directory'])
        if not root.is_dir():
            raise CommandError(f'Not a directory: {root}')
        created = skipped = ignored = 0
        for path in sorted(root.rglob('*')):
            relative = path.relative_to(root)
            if not path.is_file() or any(part.startswith('.') for part in relative.parts):
                continue
            section = 'framework' if len(relative.parts) == 1 else FOLDERS.get(relative.parts[0].casefold())
            if not section:
                self.stderr.write(f'Ignored (unknown folder): {relative}')
                ignored += 1
                continue
            if Download.objects.filter(slug=download_slug(path.name)).exists():
                skipped += 1
                continue
            with path.open('rb') as file:
                Download.objects.create(title=path.name, section=section, file=File(file, name=path.name))
            self.stdout.write(f'Added {relative} → {section}')
            created += 1
        self.stdout.write(self.style.SUCCESS(f'{created} added, {skipped} already present, {ignored} ignored.'))
