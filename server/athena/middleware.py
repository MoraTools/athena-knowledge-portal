import hashlib
import math
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import patch_cache_control

from .models import LoginAttempt


WINDOW = timedelta(minutes=15)
MAX_FAILURES = 5


def locked_response(request, remaining):
    """The normal login page, with the wait as a form error, instead of a bare 429."""
    minutes = math.ceil(remaining.total_seconds() / 60)
    form = AuthenticationForm(request, initial={'username': request.POST.get('username', '')})
    form.cleaned_data = {}  # Unbound, so the password is never checked; add_error expects this attribute.
    form.add_error(None, f'Demasiados intentos. Intente de nuevo en {minutes} minuto{"" if minutes == 1 else "s"}.')
    context = {'form': form, 'next': request.POST.get('next', '')}
    template = 'registration/login.html'
    if request.path.startswith('/admin/'):
        context.update(admin.site.each_context(request), title='Iniciar sesión', app_path=request.get_full_path())
        template = 'admin/login.html'
    response = render(request, template, context, status=429)
    response['Retry-After'] = str(math.ceil(remaining.total_seconds()))
    return response


class AccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        login = path in ('/accounts/login/', '/admin/login/') and request.method == 'POST'
        response = None
        if login:
            now = timezone.now()
            # The proxy overwrites this header; the app listens on loopback only.
            ip = request.META.get('HTTP_X_REAL_IP', request.META.get('REMOTE_ADDR', 'unknown'))
            keys = [hashlib.sha256(value.encode()).hexdigest() for value in
                    ['ip:' + ip, 'user:' + request.POST.get('username', '').casefold()]]
            with transaction.atomic():
                # Rows remember past lockouts, so each further lockout doubles, until a day passes quietly.
                LoginAttempt.objects.filter(started_at__lt=now - timedelta(hours=24)).delete()
                attempts = [LoginAttempt.objects.get_or_create(key=key)[0] for key in keys]
                locked_until = max((a.locked_until for a in attempts if a.locked_until and a.locked_until > now), default=None)
                if locked_until:
                    response = locked_response(request, locked_until - now)
                else:
                    for attempt in attempts:
                        if attempt.started_at < now - WINDOW:
                            attempt.count, attempt.started_at = 0, now
                        attempt.count += 1  # Counted before the view runs, so parallel guesses cannot skip the limit.
                        if attempt.count >= MAX_FAILURES:
                            attempt.locked_until = now + min(WINDOW * 2 ** min(attempt.lockouts, 7), timedelta(hours=24))
                            attempt.lockouts += 1
                            attempt.count, attempt.started_at = 0, now
                        attempt.save()
        if response is None:
            response = self.get_response(request)
        if login and response.status_code == 302:
            LoginAttempt.objects.filter(key__in=keys).update(count=0, locked_until=None)
        if not path.startswith(('/static/', '/assets/', '/fonts/', '/vendor/')):
            patch_cache_control(response, private=True, no_store=True)
        # Docsify needs inline styles, but article scripts and remote scripts stay blocked.
        # Private portal: never let search engines index or cache any page, including the login page.
        response.headers.setdefault('X-Robots-Tag', 'noindex, nofollow, noarchive')
        response.headers.setdefault('Content-Security-Policy', (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        ))
        return response
