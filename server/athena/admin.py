from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from django.utils import timezone
from django.utils.html import format_html

from .forms import ArticleForm, SafeUserChangeForm
from .models import ApiKey, Article

admin.site.site_header = 'Athena · Administración'
admin.site.site_title = 'Athena'
admin.site.index_title = 'Administrar conocimiento y acceso'
admin.site.site_url = '/'
admin.site.unregister(Group)
admin.site.unregister(User)


@admin.register(User)
class AthenaUserAdmin(UserAdmin):
    form = SafeUserChangeForm
    list_display = ['username', 'email', 'is_active', 'is_superuser', 'last_login']

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


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    form = ArticleForm
    list_display = ['title', 'kind', 'published', 'author', 'date', 'updated_at']
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

    def get_prepopulated_fields(self, request, obj=None):
        return {} if obj else self.prepopulated_fields

    def get_changeform_initial_data(self, request):
        return {'author': request.user.get_full_name() or request.user.username}

    @admin.display(description='Última modificación')
    def last_updated(self, obj):
        return obj.updated_at or 'Sin guardar'

    @admin.display(description='PDF actual')
    def current_pdf(self, obj):
        if obj.pdf_name:
            return format_html('<a href="/pdf/{}.pdf" target="_blank" rel="noopener">{}</a>', obj.slug, obj.pdf_name)
        return 'Sin PDF adjunto.'


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'scope', 'expires_at', 'created_at']
    fields = ['name', 'user', 'scope', 'expires_at']

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission

    def get_readonly_fields(self, request, obj=None):
        return ['user', 'scope'] if obj else []

    def save_model(self, request, obj, form, change):
        raw = obj.issue() if not change else None
        super().save_model(request, obj, form, change)
        if raw:
            messages.warning(request, f'Copie esta clave ahora. No se mostrará otra vez: {raw}')
