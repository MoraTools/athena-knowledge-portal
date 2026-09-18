import os
import secrets

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create the first administrator and save credentials in a private file, never stdout.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write('An administrator already exists; no credentials changed.')
            return
        password = secrets.token_urlsafe(24)
        fd = os.open(options['output'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w') as file:
                file.write(f'Username: {options["username"]}\nPassword: {password}\n')
            User.objects.create_superuser(options['username'], password=password)
        except Exception:
            os.unlink(options['output'])
            raise
        self.stdout.write('Administrator created. Credentials saved in the requested private file.')
