from django.contrib import admin, messages
from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.template.defaultfilters import filesizeformat
from django.utils import formats, timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .forms import ArticleForm, DirectoryUserCreationForm, DirectoryUserForm, SafeUserChangeForm
from .models import ApiKey, Article, Download

admin.site.site_header = 'Athena · Administración'
admin.site.site_title = 'Athena'
admin.site.index_title = 'Administrar conocimiento y acceso'
admin.site.site_url = '/'
admin.site.unregister(Group)
admin.site.unregister(User)


def since(moment, now):
    if not moment:
        return 'nunca'
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 1:
        return 'ahora'
    if minutes < 60:
        return f'hace {minutes} min'
    if minutes < 24 * 60:
        return f'hace {minutes // 60} h'
    days = minutes // (24 * 60)
    return 'ayer' if days == 1 else f'hace {days} días'


def pill(user):
    if not user.is_active:
        return 'Inactivo'
    return 'Admin' if user.is_staff and user.is_superuser else 'Lector'


def flag(value, yes, no):
    # Text pills replace Django's boolean icons; same markup as the directory pills.
    return format_html('<span class="pill {}">{}</span>', 'gold' if value else 'off', yes if value else no)


@admin.register(User)
class AthenaUserAdmin(UserAdmin):
    form = SafeUserChangeForm
    list_display = ['username', 'email', 'active', 'superuser', 'last_login']

    @admin.display(description='Activa', ordering='is_active')
    def active(self, obj):
        return flag(obj.is_active, 'Activa', 'Inactiva')

    @admin.display(description='Admin', ordering='is_superuser')
    def superuser(self, obj):
        return flag(obj.is_superuser, 'Admin', 'Lector')

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and (obj is None or obj.pk != request.user.pk)

    def get_actions(self, request):
        return {}  # User removal is individual so the acting admin cannot be removed in a batch.

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.actor = request.user
        return form

    # The directory replaces the change and add pages; Django's native pages remain for related-field popups.
    def is_popup(self, request):
        return IS_POPUP_VAR in request.GET or IS_POPUP_VAR in request.POST

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if self.is_popup(request):
            return super().change_view(request, object_id, form_url, extra_context)
        return redirect(reverse('admin:auth_user_changelist') + f'?user={object_id}')

    def add_view(self, request, form_url='', extra_context=None):
        if self.is_popup(request):
            return super().add_view(request, form_url, extra_context)
        return redirect(reverse('admin:auth_user_changelist') + '?new=1')

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        creating = 'new' in request.GET
        selected = None if creating else self.get_object(request, request.GET.get('user', request.user.pk))
        if not creating and selected is None:
            raise Http404
        form_class = DirectoryUserCreationForm if creating else DirectoryUserForm
        if request.method == 'POST':
            form = form_class(request.POST, instance=selected, actor=request.user)
            with transaction.atomic():
                saved = form.save() if form.is_valid() else None
            if saved:
                message = self.construct_change_message(request, form, None, creating)
                (self.log_addition if creating else self.log_change)(request, saved, message)
                messages.success(request, 'Usuario guardado.')
                return redirect(request.path + f'?user={saved.pk}')
        else:
            form = form_class(instance=selected, actor=request.user)
        now = timezone.now()
        # ponytail: whole user list in one page; paginate or search server-side past a few hundred accounts.
        users = [(user, since(user.last_login, now), pill(user)) for user in User.objects.order_by('username')]
        return TemplateResponse(request, 'admin/auth/user/directory.html', {
            **self.admin_site.each_context(request), **(extra_context or {}),
            'title': 'Directorio', 'opts': self.opts, 'form': form, 'selected': selected, 'users': users,
            'api_keys': ApiKey.objects.filter(user=selected).count() if selected else 0,
        })


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    form = ArticleForm
    list_display = ['title', 'kind', 'state', 'author', 'date', 'last_updated']
    list_filter = ['published', 'kind']
    search_fields = ['title', 'summary', 'author', 'body']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['last_updated', 'current_pdf']
    fieldsets = [
        (None, {'fields': ['title', 'slug', 'kind', 'summary', 'author', 'tags']}),
        ('Contenido', {'fields': ['markdown_file', 'body', 'pdf_file', 'current_pdf', 'remove_pdf']}),
        ('Publicación', {'fields': ['published', 'date', 'last_updated']}),
        ('Herramientas', {'fields': ['status', 'url', 'download_file'], 'classes': ['collapse']}),
    ]
    save_on_top = True

    @admin.display(description='Estado', ordering='published')
    def state(self, obj):
        return flag(obj.published, 'Publicado', 'Borrador')

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {'title': 'Artículos', **(extra_context or {})})

    def add_view(self, request, form_url='', extra_context=None):
        return super().add_view(request, form_url, {'title': 'Nuevo artículo', **(extra_context or {})})

    def change_view(self, request, object_id, form_url='', extra_context=None):
        article = self.get_object(request, object_id)
        title = f'Editar artículo · {article.title}' if article else 'Editar artículo'
        return super().change_view(request, object_id, form_url, {'title': title, 'subtitle': None, **(extra_context or {})})

    def get_prepopulated_fields(self, request, obj=None):
        return {} if obj else self.prepopulated_fields

    def get_changeform_initial_data(self, request):
        return {'author': request.user.get_full_name() or request.user.username}

    @admin.display(description='Última modificación', ordering='updated_at')
    def last_updated(self, obj):
        return formats.localize(timezone.localtime(obj.updated_at)) if obj.updated_at else 'Sin guardar'

    @admin.display(description='PDF actual')
    def current_pdf(self, obj):
        if obj.pdf_name:
            return format_html('<a href="/pdf/{}.pdf" target="_blank" rel="noopener">{}</a>', obj.slug, obj.pdf_name)
        return 'Sin PDF adjunto.'


@admin.register(Download)
class DownloadAdmin(admin.ModelAdmin):
    list_display = ['title', 'section_pill', 'human_size', 'created']
    list_filter = ['section', 'published']
    search_fields = ['title', 'slug']
    fields = ['title', 'section', 'file', 'note', 'published', 'human_size', 'sha256', 'created']
    readonly_fields = ['human_size', 'sha256', 'created']

    @admin.display(description='Sección', ordering='section')
    def section_pill(self, obj):
        return format_html('<span class="pill">{}</span>', obj.get_section_display())

    @admin.display(description='Tamaño', ordering='size')
    def human_size(self, obj):
        return filesizeformat(obj.size) if obj.pk else 'Se calcula al guardar'

    @admin.display(description='Creado', ordering='created_at')
    def created(self, obj):
        return formats.localize(timezone.localtime(obj.created_at)) if obj.created_at else 'Sin guardar'

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {'title': 'Descargas', **(extra_context or {})})

    def add_view(self, request, form_url='', extra_context=None):
        return super().add_view(request, form_url, {'title': 'Nueva descarga', **(extra_context or {})})

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return super().change_view(request, object_id, form_url, {'title': 'Editar descarga', 'subtitle': None, **(extra_context or {})})


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'scope', 'expires_at', 'created']
    fields = ['name', 'user', 'scope', 'expires_at']

    @admin.display(description='Creada', ordering='created_at')
    def created(self, obj):
        return obj.created_at

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission

    def get_readonly_fields(self, request, obj=None):
        return ['user', 'scope'] if obj else []

    def changelist_view(self, request, extra_context=None):
        subtitle = mark_safe('Documentación: <a href="/api/docs/">/api/docs/</a> · Verifique una clave con <code>GET /api/v1/me/</code>')
        return super().changelist_view(request, {'title': 'Claves de API', 'subtitle': subtitle, **(extra_context or {})})

    def add_view(self, request, form_url='', extra_context=None):
        return super().add_view(request, form_url, {'title': 'Nueva clave de API', **(extra_context or {})})

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return super().change_view(request, object_id, form_url, {'title': 'Editar clave de API', **(extra_context or {})})

    def save_model(self, request, obj, form, change):
        raw = obj.issue() if not change else None
        super().save_model(request, obj, form, change)
        if raw:
            messages.warning(request, format_html(
                'Copie esta clave ahora. No se mostrará otra vez: <code class="secret">{}</code>'
                '<code class="secret">export ATHENA_API_KEY={}</code>'
                '<code class="secret">curl -H "Authorization: Bearer $ATHENA_API_KEY" https://{}/api/v1/me/</code>'
                '<a href="/api/docs/">Documentación de la API</a>', raw, raw, request.get_host()))
