from django import template
from django.utils import timezone

from ..admin import since as _since
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
