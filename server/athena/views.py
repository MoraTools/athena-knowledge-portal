import mimetypes
import re
from html import unescape
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import filesizeformat
from django.utils.html import escape, strip_tags
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .models import ApiKey, Article, Download


def visible_articles(user):
    articles = Article.objects.all()
    return articles if user.has_perm('athena.change_article') else articles.filter(published=True)


def search_text(body):
    body = re.sub(r'<!--.*?-->', ' ', body, flags=re.S)
    body = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', body)
    return re.sub(r'\s+', ' ', unescape(strip_tags(body)).translate(str.maketrans('', '', '`*~'))).strip()


def search_entry(article):
    headings = list(re.finditer(r'^\s{0,3}(#{2,6})\s+(.+?)\s*#*\s*$', article.body, re.M))
    return {
        'title': article.title, 'kind': article.kind, 'summary': article.summary,
        'author': article.author, 'date': article.date.isoformat(), 'tags': article.tags,
        'route': '#/content/' + article.slug, 'pdf': '/pdf/' + article.slug + '.pdf' if article.pdf_name else '',
        'text': search_text(article.body), 'headings': [
            {'level': len(match[1]), 'title': search_text(match[2]),
             'text': search_text(article.body[match.end():headings[i+1].start() if i+1 < len(headings) else len(article.body)])}
            for i, match in enumerate(headings)
        ],
    }


def download_entry(download):
    section = download.get_section_display()
    return {
        'title': download.title, 'kind': 'download', 'section': section,
        'summary': f'Archivo aprobado de {filesizeformat(download.size)} en {section}.',
        'author': '', 'date': '', 'tags': [section, Path(download.filename).suffix.lstrip('.').upper()],
        'route': '/downloads/' + download.slug, 'pdf': '', 'text': f'{download.filename} {download.note}', 'headings': [],
    }


@login_required
def search_index(request):
    return JsonResponse([search_entry(a) for a in Article.objects.filter(published=True).defer('pdf')]
                        + [download_entry(d) for d in Download.objects.filter(published=True)], safe=False)


@login_required
def article_markdown(request, slug):
    article = get_object_or_404(visible_articles(request.user).defer('pdf'), slug=slug)
    body = article.body
    if not re.match(r'^\s*#\s+', body):
        body = f'# {escape(article.title)}\n\n' + body
    if not article.published:
        body = '> **Borrador.** Solo visible para editores.\n\n' + body
    if article.pdf_name:
        body += f'\n\n[Abrir PDF original](/pdf/{article.slug}.pdf)\n'
    return HttpResponse(body, content_type='text/markdown; charset=utf-8')


@login_required
@xframe_options_sameorigin  # The reader embeds the PDF in an iframe.
def pdf(request, slug):
    article = get_object_or_404(visible_articles(request.user), slug=slug)
    if not article.pdf:
        raise Http404
    disposition = 'attachment' if request.GET.get('download') else 'inline'
    return HttpResponse(bytes(article.pdf), content_type='application/pdf', headers={
        'Content-Disposition': f'{disposition}; filename="{article.slug}.pdf"',
        'Content-Security-Policy': "sandbox; default-src 'none'; frame-ancestors 'self'",
    })


@login_required
def download(request, slug):
    item = get_object_or_404(Download, slug=slug, published=True)
    try:
        file = open(item.file.path, 'rb')
    except FileNotFoundError:
        raise Http404
    # FileResponse sets Content-Length and lets Gunicorn stream the file through wsgi.file_wrapper.
    return FileResponse(file, as_attachment=True, filename=item.filename)


@login_required
def downloads_page(request):
    published = Download.objects.filter(published=True)
    sections = [(key, label, [d for d in published if d.section == key]) for key, label in Download.SECTIONS]
    return render(request, 'downloads.md', {'sections': [s for s in sections if s[2]]},
                  content_type='text/markdown; charset=utf-8')


@login_required
def library(request, section):
    kinds = {'guides': ['guide'], 'tools': ['tool'], 'updates': ['guide', 'announcement', 'release']}
    articles = Article.objects.filter(published=True, kind__in=kinds[section]).defer('body', 'pdf')
    tags = sorted({tag for article in articles for tag in article.tags})
    return render(request, 'library.md', {'section': section, 'articles': articles, 'tags': tags},
                  content_type='text/markdown; charset=utf-8')


@login_required
def account_markdown(request):
    """Mi cuenta, rendered by Docsify at /#/account; the logout form posts with the token rendered here."""
    user = request.user
    return render(request, 'account.md', {
        'is_admin': user.is_staff,
        'keys': ApiKey.objects.filter(user=user).order_by('expires_at'),
    }, content_type='text/markdown; charset=utf-8')


def health(request):
    Article.objects.exists()
    return JsonResponse({'status': 'ok'})


def api_schema(request):
    return FileResponse((settings.BASE_DIR / 'server/openapi.json').open('rb'), content_type='application/json')


_api_docs_cache = (None, '')


def api_markdown():
    global _api_docs_cache
    file = settings.BASE_DIR / 'API.md'
    mtime = file.stat().st_mtime
    if _api_docs_cache[0] != mtime:
        _api_docs_cache = (mtime, file.read_text(encoding='utf-8'))
    return _api_docs_cache[1]


def api_docs(request):
    return HttpResponse(api_markdown(), content_type='text/markdown; charset=utf-8')


_sidebar_cache = (None, [])
SIDEBAR_LINK = re.compile(r'\[([^\]]+)\]\(([^\s)]+)[^)]*\)')
# The code owns the grouping; a link that is not listed here falls into Biblioteca.
SIDEBAR_GROUPS = ['Biblioteca', 'Participar', 'Cuenta', 'Administración']
SIDEBAR_GROUP = {'/content/contributing.md': 'Participar', '/account.md': 'Cuenta',
                 '/admin/': 'Administración', '/api.md': 'Administración'}


def sidebar_markdown(user):
    """The portal rail as nested markdown groups; src/app.js renders it in the reader, sidebar_links in the admin."""
    global _sidebar_cache
    file = settings.BASE_DIR / 'dist/_sidebar.md'
    mtime = file.stat().st_mtime
    if _sidebar_cache[0] != mtime:
        # Archivo is now the "Versiones anteriores" section of Descargas.
        _sidebar_cache = (mtime, [m[0] for m in SIDEBAR_LINK.finditer(file.read_text(encoding='utf-8-sig')) if m[1] != 'Archivo'])
    links = _sidebar_cache[1] + ['[Mi cuenta](/account.md)']
    if user.is_staff:
        links += ['[Administrar Athena](/admin/ ":ignore")', '[API para agentes](/api.md)']
    groups = {group: [] for group in SIDEBAR_GROUPS}
    for link in links:
        groups[SIDEBAR_GROUP.get(SIDEBAR_LINK.match(link)[2], 'Biblioteca')].append(link)
    return ''.join(f'- {group}\n' + ''.join(f'  - {link}\n' for link in items)
                   for group, items in groups.items() if items)


def sidebar_links(user):
    """[(group, [(label, href), ...]), ...]; Docsify routes a /page.md link to /#/page."""
    groups = []
    for line in sidebar_markdown(user).splitlines():
        if line.startswith('- '):
            groups.append((line[2:], []))
        else:
            label, href = SIDEBAR_LINK.search(line).groups()
            groups[-1][1].append((label, '/#' + href[:-3] if href.endswith('.md') else href))
    return groups


def robots(request):
    return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain; charset=utf-8')


def static_portal(request, path='index.html'):
    # An explicit allowlist prevents serving a database, source file, or a removed article.
    assets = path.startswith(('fonts/', 'assets/', 'vendor/')) or path in ('styles.css', 'app.js', 'config.js')
    if not assets and not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    if assets:
        if path.startswith('vendor/'):
            file = settings.BASE_DIR / 'dist' / path
        else:
            file = settings.BASE_DIR / 'src' / path
    else:
        allowed = {'index.html', 'README.md', '_sidebar.md', 'search.md', 'catalog.json', 'api.md'}
        if path not in allowed:
            raise Http404
        file = settings.BASE_DIR / ('src' if path == 'index.html' else 'dist') / path
        if path == 'api.md':
            file = settings.BASE_DIR / 'API.md'  # The repository's API.md, the same file as /api/docs/.
    root = settings.BASE_DIR.resolve()
    if '..' in Path(path).parts or not file.resolve().is_relative_to(root) or not file.is_file():
        raise Http404
    if path == '_sidebar.md':
        return HttpResponse(sidebar_markdown(request.user), content_type='text/markdown; charset=utf-8')
    if path == 'api.md':
        return HttpResponse(api_markdown(), content_type='text/markdown; charset=utf-8')
    return FileResponse(file.open('rb'), content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
