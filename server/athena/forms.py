import json
import re

from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm, UsernameField
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.db.models import Q

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
                  'status', 'url', 'download_file', 'published', 'pdf_only']
        widgets = {'body': forms.Textarea(attrs={'rows': 24, 'cols': 90}),
                   'summary': forms.Textarea(attrs={'rows': 3, 'cols': 80})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and 'slug' in self.fields:  # A view-only change form has no fields.
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


def user_managers():
    """Active accounts that can manage users: superusers and staff with auth.change_user."""
    return User.objects.filter(Q(is_superuser=True) | Q(is_staff=True, user_permissions__codename='change_user',
                                                        user_permissions__content_type__app_label='auth'), is_active=True)


def protect_admin(user, *, actor, active=True, admin=True, deleting=False):
    """admin: whether the account keeps the right to manage users after the change."""
    if user.pk == actor.pk and (deleting or not active or not admin):
        raise ValidationError('No puede quitar su propio acceso de administrador.')
    if (deleting or not active or not admin) and user_managers().filter(pk=user.pk).exists():
        if not user_managers().exclude(pk=user.pk).exists():
            raise ValidationError('Debe conservar al menos un administrador activo.')


class SafeUserChangeForm(UserChangeForm):
    def clean(self):
        data = super().clean()
        if self.instance.pk:
            original = User.objects.get(pk=self.instance.pk)
            permissions = data.get('user_permissions', Permission.objects.none())
            manages = data.get('is_superuser', False) or permissions.filter(
                codename='change_user', content_type__app_label='auth').exists()
            protect_admin(original, actor=self.actor, active=data.get('is_active', False),
                          admin=data.get('is_staff', False) and manages)
        return data


# Edit areas an administrator can hold; the first permission of each decides whether the area shows as checked.
EDIT_AREAS = {
    'articles': ['athena.change_article', 'athena.add_article', 'athena.delete_article'],
    'downloads': ['athena.change_download', 'athena.add_download', 'athena.delete_download'],
    'users': ['auth.change_user', 'auth.add_user', 'auth.delete_user', 'auth.view_user',
              'athena.add_apikey', 'athena.change_apikey', 'athena.delete_apikey', 'athena.view_apikey'],
}
ADMIN_VIEW = ['athena.view_article', 'athena.view_download']


def held_areas(user):
    """Edit areas a non-superuser holds directly (a superuser holds every area)."""
    held = {f'{app}.{codename}' for app, codename in user.user_permissions.values_list('content_type__app_label', 'codename')}
    return {area for area, names in EDIT_AREAS.items() if names[0] in held}


def permissions(names):
    query = Q(pk__in=[])
    for name in names:
        app_label, codename = name.split('.')
        query |= Q(content_type__app_label=app_label, codename=codename)
    return Permission.objects.filter(query)


class DirectoryUserForm(forms.ModelForm):
    role = forms.ChoiceField(label='Acceso', choices=[('admin', 'Administrador'), ('reader', 'Lector')],
                             widget=forms.RadioSelect)
    edits = forms.MultipleChoiceField(label='Permisos de edición', required=False, widget=forms.CheckboxSelectMultiple,
                                      choices=[('articles', 'Artículos'), ('downloads', 'Descargas'),
                                               ('users', 'Usuarios y claves de API')])

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active']
        field_classes = {'username': UsernameField}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        user = self.instance
        self.initial.setdefault('role', 'admin' if user.is_staff else 'reader')
        if user.is_superuser:
            self.initial.setdefault('edits', list(EDIT_AREAS))
        elif user.pk:
            self.initial.setdefault('edits', sorted(held_areas(user)))
        for name in ['first_name', 'last_name', 'email']:
            self.fields[name].widget.attrs['placeholder'] = 'Opcional'
        self.fields['username'].help_text = self.fields['is_active'].help_text = ''

    def clean(self):
        data = super().clean()
        if self.instance.pk:
            protect_admin(User.objects.get(pk=self.instance.pk), actor=self.actor, active=data.get('is_active', False),
                          admin=data.get('role') == 'admin' and 'users' in data.get('edits', []))
        if not self.actor.is_superuser and set(data.get('edits', [])) - held_areas(self.actor):
            raise ValidationError('Solo puede otorgar los permisos de edición que usted tiene.')
        return data

    def save(self, commit=True):
        admin = self.cleaned_data['role'] == 'admin'
        self.instance.is_staff = admin
        self.instance.is_superuser = admin and set(self.cleaned_data['edits']) == set(EDIT_AREAS)
        return super().save(commit)

    def _save_m2m(self):
        # Runs for commit=True and for a later save_m2m(), so the permissions follow the user row.
        super()._save_m2m()
        user = self.instance
        names = [] if user.is_superuser or not user.is_staff else ADMIN_VIEW + [
            name for area in self.cleaned_data['edits'] for name in EDIT_AREAS[area]]
        user.user_permissions.set(permissions(names))


class DirectoryUserCreationForm(DirectoryUserForm, UserCreationForm):
    pass
