from django import template

from ..views import sidebar_links

register = template.Library()


@register.inclusion_tag('admin/portal_sidebar.html', takes_context=True)
def portal_sidebar(context):
    path = context['request'].path
    # Reader routes live in Docsify; inside the admin only the dashboard or the open model is current.
    groups = [(group, [(label, href, href == '/admin/' and path == '/admin/') for label, href in links])
              for group, links in sidebar_links(context['request'].user)]
    sections = [(model['name'], model['admin_url'], path.startswith(model['admin_url']))
                for app in context.get('available_apps', []) for model in app['models'] if model['admin_url']]
    for group, links in groups:
        if group == 'Administración':
            links += sections
    return {'groups': groups}
