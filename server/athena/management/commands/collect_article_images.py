from django.core.management.base import BaseCommand

from athena.images import collect_images


class Command(BaseCommand):
    help = 'Remove only unused managed article images after a 24-hour grace period.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report candidates without changing files or metadata.')

    def handle(self, *args, **options):
        report = collect_images(dry_run=options['dry_run'])
        label = 'Would remove' if options['dry_run'] else 'Removed'
        for image_id in report['images']:
            self.stdout.write(f'{label} image {image_id}')
        for filename in report['orphans']:
            self.stdout.write(f'{label} orphan {filename}')
        self.stdout.write(f"{label}: {len(report['images'])} images, {len(report['orphans'])} orphans. "
                          f"Retained: {report['referenced']} referenced, {report['grace']} within grace.")
