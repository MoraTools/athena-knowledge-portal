import re

from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm, UsernameField
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import ApiKey, Article


EMAIL_UNAVAILABLE = ('El servicio de correo de Athena aún no está configurado. Por ahora no se pueden ingresar ni guardar correos. '
                     'Para recuperar su contraseña, contacte al administrador.')


def disable_email_field(field):
    field.disabled = True
    field.help_text = EMAIL_UNAVAILABLE
    field.widget.attrs['title'] = EMAIL_UNAVAILABLE
    field.widget.template_name = 'admin/auth/user/disabled_email.html'


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
                  'status', 'url', 'download_file', 'published', 'is_public', 'pdf_only']
        widgets = {'body': forms.Textarea(attrs={'rows': 24, 'cols': 90}),
                   'summary': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
                   'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
                   'is_public': forms.Select(choices=[(False, 'Con cuenta'), (True, 'Público')])}

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor or getattr(type(self), 'actor', None)
        self.instance._image_actor = self.actor
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
        if 'body' in data:
            from .images import check_references
            try:
                check_references(data['body'], actor=self.actor)
            except ValidationError as error:
                self.add_error('body', error.message_dict['body'] if hasattr(error, 'message_dict') else error.messages)
        return data


class AdminArticleForm(ArticleForm):
    loaded_revision = forms.CharField(required=False, max_length=50, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['loaded_revision'] = self.instance.updated_at.isoformat()
        if 'body' not in self.fields:
            self.fields.pop('loaded_revision', None)

    def clean(self):
        data = super().clean()
        if self.instance.pk and 'loaded_revision' in self.fields:
            # Django's native change POST holds this lock until the article and its related rows are saved.
            current = Article.objects.select_for_update().only('updated_at').get(pk=self.instance.pk)
            if data.get('loaded_revision') != current.updated_at.isoformat():
                raise ValidationError('El artículo cambió desde que abrió esta página. Su texto no se guardó. '
                                      'Copie sus cambios y vuelva a abrir el artículo.')
        return data


def user_managers():
    """Active accounts that can manage users: superusers and staff with auth.change_user."""
    return User.objects.filter(Q(is_superuser=True) | Q(is_staff=True) & (
        Q(user_permissions__codename='change_user', user_permissions__content_type__app_label='auth') |
        Q(groups__permissions__codename='change_user', groups__permissions__content_type__app_label='auth')
    ), is_active=True).distinct()


def protect_admin(user, *, actor, active=True, admin=True, deleting=False):
    """admin: whether the account keeps the right to manage users after the change."""
    if user.pk == actor.pk and (deleting or not active or not admin):
        raise ValidationError('No puede quitar su propio acceso de administrador.')
    if (deleting or not active or not admin) and user_managers().filter(pk=user.pk).exists():
        if not user_managers().exclude(pk=user.pk).exists():
            raise ValidationError('Debe conservar al menos un administrador activo.')


class SafeUserChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'email' in self.fields:
            disable_email_field(self.fields['email'])

    def save(self, commit=True):
        if 'email' in self.fields:
            self.instance.email = self.initial.get('email', '') if self.instance.pk else ''
        return super().save(commit)

    def clean(self):
        data = super().clean()
        granted = permission_names(data.get('user_permissions', Permission.objects.none()))
        granted |= permission_names(Permission.objects.filter(group__in=data.get('groups', Group.objects.none())))
        validate_user_grants(self.actor, superuser=data.get('is_superuser', False), granted=granted)
        if self.instance.pk:
            original = User.objects.get(pk=self.instance.pk)
            manages = data.get('is_superuser', False) or 'auth.change_user' in granted
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
    """Edit areas held directly or through groups (a superuser holds every area)."""
    if user.is_superuser:
        return set(EDIT_AREAS)
    held = user_permission_names(user)
    return {area for area, names in EDIT_AREAS.items() if names[0] in held}


def permissions(names):
    query = Q(pk__in=[])
    for name in names:
        app_label, codename = name.split('.')
        query |= Q(content_type__app_label=app_label, codename=codename)
    return Permission.objects.filter(query)


def permission_names(query):
    return {f'{app}.{codename}' for app, codename in query.values_list('content_type__app_label', 'codename')}


def user_permission_names(user):
    # Include inactive accounts' stored grants so reactivation and password resets cannot bypass the ceiling.
    return permission_names(Permission.objects.filter(Q(user=user) | Q(group__user=user)))


def may_manage_user(actor, user):
    return user is None or actor.is_superuser or (
        not user.is_superuser and user_permission_names(user) <= user_permission_names(actor))


def validate_user_grants(actor, *, superuser=False, granted=()):
    if not actor.is_superuser and (superuser or set(granted) - user_permission_names(actor)):
        raise ValidationError('Solo puede otorgar los permisos de edición que usted tiene.')


class ApiKeyForm(forms.ModelForm):
    class Meta:
        model = ApiKey
        fields = ['name', 'user', 'scope', 'expires_at']

    def clean(self):
        data = super().clean()
        owner = data.get('user', self.instance.user if self.instance.pk else None)
        if owner and not may_manage_user(self.actor, owner):
            raise ValidationError('Solo puede administrar claves de usuarios con permisos que usted tiene.')
        return data


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
        disable_email_field(self.fields['email'])
        self.fields['username'].help_text = self.fields['is_active'].help_text = ''

    def clean(self):
        data = super().clean()
        if data.get('role') == 'reader':
            data['edits'] = []
        if self.instance.pk:
            protect_admin(User.objects.get(pk=self.instance.pk), actor=self.actor, active=data.get('is_active', False),
                          admin=data.get('role') == 'admin' and 'users' in data.get('edits', []))
        if not self.actor.is_superuser and set(data.get('edits', [])) - held_areas(self.actor):
            raise ValidationError('Solo puede otorgar los permisos de edición que usted tiene.')
        edits = data.get('edits', []) if data.get('role') == 'admin' else []
        validate_user_grants(self.actor, superuser=data.get('role') == 'admin' and set(edits) == set(EDIT_AREAS),
                             granted=ADMIN_VIEW + [name for area in edits for name in EDIT_AREAS[area]]
                             if data.get('role') == 'admin' else [])
        return data

    def save(self, commit=True):
        self.instance.email = self.initial.get('email', '') if self.instance.pk else ''
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
        allowed = permissions(names)
        user.user_permissions.set(allowed)
        if not user.is_superuser:
            # The directory choices also limit permissions inherited from groups.
            disallowed = Permission.objects.exclude(pk__in=allowed)
            user.groups.remove(*user.groups.filter(permissions__in=disallowed).values_list('pk', flat=True).distinct())


class DirectoryUserCreationForm(DirectoryUserForm, UserCreationForm):
    pass
