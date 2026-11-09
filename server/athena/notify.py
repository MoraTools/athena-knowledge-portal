"""Phone notifications through ntfy for template downloads and sign-ins. The topic lives only in a file."""
import http.client
import logging
from pathlib import Path
from threading import Thread
from urllib.parse import quote, urlencode, urlsplit

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.dispatch import receiver

log = logging.getLogger(__name__)
_off_logged = False


def topic():
    """The topic from ATHENA_NTFY_TOPIC_FILE, or '' (notifications off) when the file is missing or empty."""
    global _off_logged
    try:
        value = Path(settings.ATHENA_NTFY_TOPIC_FILE).read_text(encoding='utf-8').strip()
    except (OSError, ValueError):
        value = ''
    if not value and not _off_logged:
        _off_logged = True
        log.warning('ntfy notifications are off: no readable topic file.')
    return value


def post(server, name, title, body):
    # Title goes in the query string: URL encoding keeps UTF-8 labels safe.
    url = urlsplit(server)
    conn_cls = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
    conn = conn_cls(url.netloc, timeout=5)
    try:
        path = f"{url.path.rstrip('/')}/{quote(name, safe='')}?{urlencode({'title': title, 'priority': 'default'})}"
        conn.request('POST', path, body.encode())
        status = conn.getresponse().status
    finally:
        conn.close()
    if status != 200:
        raise OSError(f'HTTP {status}')


def deliver(title, body):
    try:
        name = topic()
        if name:
            post(settings.ATHENA_NTFY_SERVER, name, title, body)
    except Exception as error:  # Only the type: the message or URL can hold the topic.
        log.warning('ntfy notification failed: %s', type(error).__name__)


def start(title, body):
    try:
        Thread(target=deliver, args=(title, body), daemon=True).start()
    except Exception as error:
        log.warning('ntfy notification failed: %s', type(error).__name__)


def send(title, body):
    """Send after the transaction commits, in a background thread; never slows or breaks the request."""
    transaction.on_commit(lambda: start(title, body))


def notify_download(request, item):
    if item.section == 'framework':
        send('Athena: descarga de plantilla',
             f'{request.user.get_username()} descargó {item.title} ({item.filename})\n{request.path}')


@receiver(user_logged_in, dispatch_uid='athena-ntfy-login')
def notify_login(sender, request, user, **kwargs):
    full_name = user.get_full_name()
    send('Athena: inicio de sesión', f"{user.get_username()}{f' ({full_name})' if full_name else ''} inició sesión")
