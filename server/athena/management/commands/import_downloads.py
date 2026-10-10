import errno
import os
import stat
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
        if root.is_symlink() or not root.is_dir():
            raise CommandError(f'Not a directory: {root}')
        root = root.resolve()
        created = skipped = ignored = 0
        # Directory descriptors and O_NOFOLLOW also prevent a link swap between checking and opening.
        for directory, folders, names, directory_fd in os.fwalk(root, follow_symlinks=False):
            for folder in sorted(folders):
                path = Path(directory) / folder
                if folder.startswith('.') or path.is_symlink():
                    folders.remove(folder)
                    if path.is_symlink() and not folder.startswith('.'):
                        self.stderr.write(f'Ignored (symbolic link): {path.relative_to(root)}')
                        ignored += 1
            folders.sort()
            for name in sorted(names):
                if name.startswith('.'):
                    continue
                relative = (Path(directory) / name).relative_to(root)
                try:
                    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                except OSError as error:
                    if error.errno != errno.ELOOP:
                        raise CommandError(f'Cannot open {relative}: {error}') from error
                    self.stderr.write(f'Ignored (symbolic link): {relative}')
                    ignored += 1
                    continue
                with os.fdopen(descriptor, 'rb') as file:
                    if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                        continue
                    section = 'framework' if len(relative.parts) == 1 else FOLDERS.get(relative.parts[0].casefold())
                    if not section:
                        self.stderr.write(f'Ignored (unknown folder): {relative}')
                        ignored += 1
                        continue
                    if Download.objects.filter(slug=download_slug(name)).exists():
                        skipped += 1
                        continue
                    Download.objects.create(title=name, section=section, file=File(file, name=name))
                self.stdout.write(f'Added {relative} → {section}')
                created += 1
        self.stdout.write(self.style.SUCCESS(f'{created} added, {skipped} already present, {ignored} ignored.'))
