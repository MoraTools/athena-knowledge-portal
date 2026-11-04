from django import template
from django.utils import timezone

from ..admin import since as _since
from ..models import Article, DownloadEvent, readable_articles
from ..views import sidebar_links

register = template.Library()


@register.filter
def since(moment):
    return _since(moment, timezone.now())


@register.inclusion_tag('admin/portal_sidebar.html', takes_context=True)
def portal_sidebar(context):
    path = context['request'].path
    # Reader routes live in Docsify; here only the dashboard, the open model, or Mi cuenta (on /accounts/) is current.
    current = {'/admin/': path == '/admin/', '/#/account': path.startswith('/accounts/')}
    groups = [(group, [(label, href, current.get(href, False)) for label, href in links])
              for group, links in sidebar_links(context['request'].user)]
    sections = [(model['name'], model['admin_url'], path.startswith(model['admin_url']))
                for app in context.get('available_apps', []) for model in app['models'] if model['admin_url']]
    for group, links in groups:
        if group == 'Administración':
            links += sections
    return {'groups': groups}


@register.filter
def readable_log(entries, user):
    """Última actividad without entries of restricted articles the user may not read."""
    from django.contrib.contenttypes.models import ContentType
    entries = list(entries)
    kind = ContentType.objects.get_for_model(Article).pk
    ids = {entry.object_id for entry in entries if entry.content_type_id == kind}
    existing = Article.objects.filter(pk__in=ids)
    hidden = {str(pk) for pk in existing.exclude(pk__in=readable_articles(user, existing).values('pk')).values_list('pk', flat=True)}
    return [entry for entry in entries if entry.content_type_id != kind or entry.object_id not in hidden]


@register.simple_tag
def recent_activity(user, limit=15):
    """Última actividad: readable admin log entries and, for view_downloadevent holders, downloads; newest first."""
    from django.contrib.admin.models import LogEntry
    items = [(entry.action_time, entry) for entry in
             readable_log(LogEntry.objects.select_related('content_type', 'user')[:limit], user)]
    if user.has_perm('athena.view_downloadevent'):
        items += [(event.downloaded_at, event) for event in DownloadEvent.objects.all()[:limit]]
    return [item for _, item in sorted(items, key=lambda pair: pair[0], reverse=True)[:limit]]
