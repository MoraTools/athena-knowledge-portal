import hashlib
from datetime import timedelta

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.cache import patch_cache_control

from .models import LoginAttempt


class AccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        login = path in ('/accounts/login/', '/admin/login/') and request.method == 'POST'
        if login:
            now = timezone.now()
            # The proxy overwrites this header; the app listens on loopback only.
            ip = request.META.get('HTTP_X_REAL_IP', request.META.get('REMOTE_ADDR', 'unknown'))
            keys = [hashlib.sha256(value.encode()).hexdigest() for value in
                    ['ip:' + ip, 'user:' + request.POST.get('username', '').casefold()]]
            with transaction.atomic():
                LoginAttempt.objects.filter(started_at__lt=now - timedelta(minutes=15)).delete()
                for key in keys:
                    attempt, _ = LoginAttempt.objects.get_or_create(key=key)
                    if attempt.count >= 10:
                        return HttpResponse('Demasiados intentos. Intente de nuevo en 15 minutos.', status=429,
                                            headers={'Retry-After': '900'})
                    attempt.count += 1
                    attempt.save()
        response = self.get_response(request)
        if login and response.status_code == 302:
            LoginAttempt.objects.filter(key__in=keys).delete()
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
