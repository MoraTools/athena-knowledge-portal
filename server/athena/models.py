import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def token_expiry():
    return timezone.now() + timedelta(days=90)


class Article(models.Model):
    KINDS = [('guide', 'Guía'), ('page', 'Página'), ('tool', 'Herramienta'),
             ('announcement', 'Anuncio'), ('release', 'Versión')]
    title = models.CharField('título', max_length=240)
    slug = models.SlugField('dirección', max_length=180, unique=True,
                            help_text='Se conserva después de crear el artículo para mantener sus enlaces.')
    kind = models.CharField('tipo', max_length=20, choices=KINDS, default='guide')
    summary = models.CharField('resumen', max_length=1000)
    author = models.CharField('autor', max_length=240)
    date = models.DateField('fecha', default=timezone.localdate)
    tags = models.JSONField('etiquetas', default=list, blank=True)
    body = models.TextField('contenido Markdown', blank=True)
    status = models.CharField('estado de herramienta', max_length=20, blank=True,
                              choices=[('stable', 'Estable'), ('alpha', 'Alfa'), ('coming-soon', 'Próximamente')])
    url = models.URLField('sitio oficial', blank=True)
    download_file = models.CharField('descarga aprobada', max_length=240, blank=True)
    published = models.BooleanField('publicado', default=False)
    pdf = models.BinaryField(blank=True, default=bytes)
    pdf_name = models.CharField(max_length=240, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'title']
        verbose_name = 'artículo'
        verbose_name_plural = 'artículos'

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', self.slug or ''):
            errors['slug'] = 'Use letras minúsculas, números y guiones.'
        if not isinstance(self.tags, list) or len(self.tags) > 30 or any(
            not isinstance(tag, str) or not tag.strip() or len(tag) > 80 for tag in self.tags
        ):
            errors['tags'] = 'Use hasta 30 etiquetas de texto, con un máximo de 80 caracteres cada una.'
        if len(self.body.encode('utf-8')) > 1024 * 1024:
            errors['body'] = 'El contenido no puede superar 1 MiB.'
        if not self.body.strip() and not self.pdf:
            errors['body'] = 'Escriba contenido o adjunte un PDF.'
        if self.kind == 'tool' and not self.status:
            errors['status'] = 'Seleccione el estado de la herramienta.'
        if self.kind != 'tool' and self.status:
            errors['status'] = 'Solo las herramientas tienen este estado.'
        if self.url and not self.url.startswith('https://'):
            errors['url'] = 'Use una dirección HTTPS.'
        if errors:
            raise ValidationError(errors)

    def get_absolute_url(self):
        return '/#/content/' + self.slug


class ApiKey(models.Model):
    name = models.CharField('nombre', max_length=100)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='usuario')
    scope = models.CharField('permiso', max_length=10, default='read',
                            choices=[('read', 'Lectura'), ('articles', 'Administrar artículos'), ('admin', 'Administrar usuarios y artículos')])
    digest = models.CharField(max_length=64, unique=True, editable=False)
    password_digest = models.CharField(max_length=64, editable=False)
    expires_at = models.DateTimeField('vence', default=token_expiry)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'clave de API'
        verbose_name_plural = 'claves de API'

    def __str__(self):
        return self.name

    def issue(self):
        raw = 'athena_' + secrets.token_urlsafe(32)
        self.digest = hashlib.sha256(raw.encode()).hexdigest()
        self.password_digest = hashlib.sha256(self.user.password.encode()).hexdigest()
        return raw


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
