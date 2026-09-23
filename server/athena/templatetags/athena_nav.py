from django import template

from ..views import sidebar_links

register = template.Library()


@register.inclusion_tag('admin/portal_sidebar.html', takes_context=True)
def portal_sidebar(context):
    path = context['request'].path
    return {
        # Reader routes live in Docsify, so inside the admin only its own entry is current.
        'links': [(label, href, href == '/admin/') for label, href in sidebar_links(context['request'].user)],
        'sections': [(model['name'], model['admin_url'], path.startswith(model['admin_url']))
                     for app in context.get('available_apps', []) for model in app['models'] if model['admin_url']],
    }
