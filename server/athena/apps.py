from django.apps import AppConfig


class AthenaConfig(AppConfig):
    name = 'athena'

    def ready(self):
        from . import notify  # noqa: F401 Connects the sign-in notification.
