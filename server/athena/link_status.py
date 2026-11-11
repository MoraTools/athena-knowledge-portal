"""Live status of the links an HTML article marks with data-athena-status (the reader shows it; API.md)."""
import fcntl
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.conf import settings

MAX_LINKS = 20
TIMEOUT = 5
MAX_AGE = 5 * 60


class MarkedLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        url = (attrs.get('href') or '').strip()
        if tag == 'a' and 'data-athena-status' in attrs and url not in self.urls and len(self.urls) < MAX_LINKS:
            try:
                parts = urlsplit(url)
                parts.port  # A port that is not a number raises here.
            except ValueError:
                return
            if parts.scheme in ('http', 'https') and parts.hostname and len(url) <= 2000:
                self.urls.append(url)


def marked_links(body):
    """The http(s) hrefs of a[data-athena-status], in document order, without repeats, at most MAX_LINKS."""
    parser = MarkedLinks()
    parser.feed(body)
    return parser.urls


def check(url):
    """'online', 'offline', or None when Athena refuses the host. One GET, no redirects, public addresses only."""
    parts = urlsplit(url)
    secure = parts.scheme == 'https'
    port = parts.port or (443 if secure else 80)
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)}
    except (OSError, UnicodeError):
        return 'offline'
    # Loopback, private, link-local and reserved addresses are never requested: they are the server's own network.
    if not addresses or not all(ipaddress.ip_address(address.split('%')[0]).is_global for address in addresses):
        return None
    connection = http.client.HTTPConnection(parts.hostname, port, timeout=TIMEOUT)
    try:
        # The checked address is the one used (IPv4 first), so a second DNS answer cannot move the request.
        connection.sock = socket.create_connection((sorted(addresses, key=lambda a: ':' in a)[0], port), timeout=TIMEOUT)
        if secure:
            connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=parts.hostname)
        connection.request('GET', (parts.path or '/') + ('?' + parts.query if parts.query else ''),
                           headers={'Host': parts.netloc.rpartition('@')[2], 'User-Agent': 'Athena-status',
                                    'Accept': '*/*', 'Connection': 'close'})
        # A redirect is an answer (demos send 302 or 303 to their login page); it is not followed.
        return 'online' if connection.getresponse().status < 500 else 'offline'
    except (OSError, http.client.HTTPException):
        return 'offline'
    finally:
        connection.close()


def cache_file(url):
    folder = settings.DATA_DIR / 'link-status'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (hashlib.sha256(url.encode()).hexdigest() + '.json')


def read(file):
    try:
        entry = json.loads(file.read())
        return entry if entry['state'] in ('online', 'offline', None) and isinstance(entry['time'], (int, float)) else None
    except (ValueError, KeyError, TypeError):
        return None


def cached(url):
    try:
        with cache_file(url).open(encoding='utf-8') as file:
            return read(file)
    except OSError:
        return None


def fresh(entry):
    return bool(entry) and 0 <= time.time() - entry['time'] < MAX_AGE


def refresh(url):
    """The state and time of one URL, from the cache for MAX_AGE. The file lock keeps it to one check at a time in all workers."""
    entry = cached(url)
    if fresh(entry):
        return entry
    with cache_file(url).open('a+', encoding='utf-8') as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        file.seek(0)
        entry = read(file)
        if not fresh(entry):
            entry = {'state': check(url), 'time': time.time()}
            file.seek(0)
            file.truncate()
            file.write(json.dumps(entry))
        return entry


def statuses(body):
    """{url: {state, checked_at}} for the marked links of an HTML body. A refused or unfinished URL is left out."""
    urls = marked_links(body)
    if not urls:
        return {}
    pool = ThreadPoolExecutor(max_workers=len(urls))
    futures = {pool.submit(refresh, url): url for url in urls}
    # The reader waits about one timeout. A slower check ends in its thread; until then the last result is the answer.
    wait(futures, timeout=TIMEOUT + 1)
    pool.shutdown(wait=False)
    result = {}
    for future, url in futures.items():
        try:
            entry = future.result(timeout=0)
        except Exception:  # Not finished, or the cache file could not be written.
            entry = cached(url)
        if entry and entry['state']:
            result[url] = {'state': entry['state'],
                           'checked_at': datetime.fromtimestamp(entry['time'], timezone.utc).isoformat(timespec='seconds')}
    return result
