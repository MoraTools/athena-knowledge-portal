import json
import re

from django import forms
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Article


def read_upload(upload, extension, limit):
    if not upload.name.lower().endswith(extension) or upload.size > limit:
        raise ValidationError(f'Use un archivo {extension} de hasta {limit // 1024 // 1024} MiB.')
    data = upload.read(limit + 1)
    if len(data) > limit:
        raise ValidationError('El archivo supera el tamaño permitido.')
    return data


class ArticleForm(forms.ModelForm):
    markdown_file = forms.FileField(label='Subir Markdown', required=False,
                                    help_text='Opcional. Reemplaza el contenido. Máximo 1 MiB.')
    pdf_file = forms.FileField(label='Adjuntar PDF', required=False, help_text='Opcional. Máximo 25 MiB.')
    remove_pdf = forms.BooleanField(label='Quitar PDF actual', required=False)
    tags = forms.CharField(label='Etiquetas', required=False, help_text='Separe las etiquetas con comas.')

    class Meta:
        model = Article
        fields = ['title', 'slug', 'kind', 'summary', 'author', 'date', 'tags', 'body',
                  'status', 'url', 'download_file', 'published']
        widgets = {'body': forms.Textarea(attrs={'rows': 24, 'cols': 90}),
                   'summary': forms.Textarea(attrs={'rows': 3, 'cols': 80})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['slug'].disabled = True
            self.initial['tags'] = ', '.join(self.instance.tags)

    def clean_tags(self):
        return [tag.strip() for tag in self.cleaned_data['tags'].split(',') if tag.strip()]

    def clean(self):
        data = super().clean()
        markdown = data.get('markdown_file')
        if markdown:
            try:
                body = read_upload(markdown, '.md', 1024 * 1024).decode('utf-8-sig')
                body = re.sub(r'\A<!--\s*athena:.*?-->\s*', '', body, count=1, flags=re.S)
                data['body'] = body
            except (ValidationError, UnicodeDecodeError) as error:
                self.add_error('markdown_file', str(error))
        if data.get('remove_pdf'):
            self.instance.pdf, self.instance.pdf_name = b'', ''
        pdf = data.get('pdf_file')
        if pdf:
            try:
                content = read_upload(pdf, '.pdf', 25 * 1024 * 1024)
                if not content.startswith(b'%PDF-'):
                    raise ValidationError('El archivo no contiene un PDF válido.')
                self.instance.pdf, self.instance.pdf_name = content, pdf.name
            except ValidationError as error:
                self.add_error('pdf_file', error)
        return data


def protect_admin(user, *, actor, active=True, admin=True, deleting=False):
    if user.pk == actor.pk and (deleting or not active or not admin):
        raise ValidationError('No puede quitar su propio acceso de administrador.')
    if user.is_active and user.is_superuser and (deleting or not active or not admin):
        if not User.objects.filter(is_active=True, is_superuser=True).exclude(pk=user.pk).exists():
            raise ValidationError('Debe conservar al menos un administrador activo.')


class SafeUserChangeForm(UserChangeForm):
    def clean(self):
        data = super().clean()
        if self.instance.pk:
            original = User.objects.get(pk=self.instance.pk)
            protect_admin(original, actor=self.actor, active=data.get('is_active', False),
                          admin=data.get('is_superuser', False) and data.get('is_staff', False))
        return data
