import hashlib
import re
import secrets
from datetime import timedelta
from pathlib import PurePath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models, transaction
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify


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
    locked_until = models.DateTimeField(null=True, blank=True)
    lockouts = models.PositiveIntegerField(default=0)


class KeepNameStorage(FileSystemStorage):
    """Keep the uploaded file name (spaces, '+') so a download arrives with its original name."""

    def get_valid_name(self, name):
        name = ''.join(char for char in PurePath(name).name if char.isprintable())
        return name if name.strip(' .') else super().get_valid_name(name or 'archivo')


def download_slug(name):
    return slugify(name.replace('.', '-'))[:170].strip('-_') or 'archivo'


class Download(models.Model):
    SECTIONS = [('framework', 'Framework'), ('packages', 'Paquetes'), ('exercises', 'Ejercicios'),
                ('previous', 'Versiones anteriores')]
    title = models.CharField('título', max_length=240)
    slug = models.SlugField('dirección', max_length=180, unique=True, editable=False)
    section = models.CharField('sección', max_length=20, choices=SECTIONS, default='framework')
    file = models.FileField('archivo', upload_to='downloads/', max_length=300, storage=KeepNameStorage())
    size = models.PositiveBigIntegerField('tamaño', default=0, editable=False)
    sha256 = models.CharField('SHA-256', max_length=64, editable=False)
    note = models.CharField('nota', max_length=300, blank=True)
    published = models.BooleanField('publicado', default=True)
    created_at = models.DateTimeField('creado', auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['section', '-created_at']
        verbose_name = 'descarga'
        verbose_name_plural = 'descargas'

    def __str__(self):
        return self.title

    @property
    def filename(self):
        return PurePath(self.file.name).name

    def save(self, *args, **kwargs):
        if not self.file._committed:  # A new or replaced file: measure it before storage copies it.
            digest = hashlib.sha256()
            for chunk in self.file.chunks():
                digest.update(chunk)
            self.size, self.sha256 = self.file.size, digest.hexdigest()
            old = Download.objects.filter(pk=self.pk).values_list('file', flat=True).first() if self.pk else None
            if old:
                transaction.on_commit(lambda: self.file.storage.delete(old))
        if not self.slug:
            base = self.slug = download_slug(self.filename)
            number = 1
            while Download.objects.filter(slug=self.slug).exists():
                number += 1
                self.slug = f'{base}-{number}'
        super().save(*args, **kwargs)


@receiver(models.signals.post_delete, sender=Download)
def delete_download_file(sender, instance, **kwargs):
    name, storage = instance.file.name, instance.file.storage
    transaction.on_commit(lambda: storage.delete(name))
