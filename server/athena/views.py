import mimetypes
import re
from html import unescape
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.html import escape, strip_tags
from django.views.decorators.clickjacking import xframe_options_sameorigin
from markdown_it import MarkdownIt

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


def article_body(article):
    """The article Markdown the reader and the PDF export share: title heading, draft notice, original PDF link."""
    body = article.body
    if not re.match(r'^\s*#\s+', body):
        body = f'# {escape(article.title)}\n\n' + body
    if not article.published:
        body = '> **Borrador.** Solo visible para editores.\n\n' + body
    if article.pdf_name:
        body += f'\n\n[Abrir PDF original](/pdf/{article.slug}.pdf)\n'
    return body


# 24px line icons, the stroke style of the "Copiar página" button (src/config.js).
EDIT_ICON = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4"/></svg>'
EXPORT_ICON = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 4v11m-5-4 5 5 5-5M4 20h16"/></svg>'


@login_required
def article_markdown(request, slug):
    article = get_object_or_404(visible_articles(request.user).defer('pdf'), slug=slug)
    body = article_body(article)
    tools = []
    if request.user.has_perm('athena.change_article'):
        edit = reverse('admin:athena_article_change', args=[article.pk])
        tools.append(f'<a class="copy-page copy-page--ghost" href="{edit}">{EDIT_ICON}<span>Editar artículo</span></a>')
    if not article.pdf_only:
        tools.append(f'<a class="copy-page copy-page--ghost" href="/content/{article.slug}.pdf" download>'
                     f'{EXPORT_ICON}<span>Exportar PDF</span></a>')
    if tools:
        # Raw HTML on one line so Docsify leaves the hrefs alone; the reader moves the links next to "Copiar página".
        body += f'\n\n<div class="article-tools">{"".join(tools)}</div>\n'
    return HttpResponse(body, content_type='text/markdown; charset=utf-8')


# CommonMark is closer to the reader's marked (GFM) than Python-Markdown, e.g. a list right after a paragraph.
MARKDOWN = MarkdownIt('commonmark', {'html': True}).enable(['table', 'strikethrough'])
# The only resources an exported PDF may load; everything else (file:, other hosts, the site itself) is skipped.
PDF_RESOURCES = ('data:', 'https://raw.githubusercontent.com/')
PDF_STYLE = """
@page { size: A4; margin: 2cm;
  @bottom-center { content: counter(page) " / " counter(pages); font: 9pt "DejaVu Sans", sans-serif; color: #555 } }
body { font: 10.5pt/1.5 "DejaVu Sans", sans-serif; color: #111; background: #fff }
h1, h2, h3, h4, h5, h6 { color: #000; font-weight: bold; line-height: 1.25; margin: 1.2em 0 .5em; break-after: avoid }
h1 { font-size: 20pt; margin-top: 0 } h2 { font-size: 15pt } h3 { font-size: 12.5pt } h4, h5, h6 { font-size: 11pt }
a { color: #1a55b0 }
code, pre { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; background: #f2f2f2 }
code { padding: 0 .2em }
pre { padding: .6em .8em; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid }
pre code { padding: 0 }
img { max-width: 100%; break-inside: avoid }
table { border-collapse: collapse; margin: .8em 0 }
th, td { border: .5pt solid #999; padding: .3em .5em; text-align: left; vertical-align: top }
blockquote { margin: .8em 0; padding: 0 1em; border-left: 3pt solid #bbb; color: #333 }
"""


def export_href(href, origin):
    """The PDF is read outside the site: reader routes point back to it."""
    if href.startswith('#/'):
        return origin + '/' + href
    if match := re.fullmatch(r'/content/([a-z0-9-]+)(?:\.md)?(\?[^#]*)?', href):
        return f'{origin}/#/content/{match[1]}{match[2] or ""}'
    return href  # Other root-relative links resolve against base_url; absolute links stay.


def article_html(article, origin):
    body = MARKDOWN.render(article_body(article))
    body = re.sub(r'\bhref="([^"]*)"', lambda m: f'href="{export_href(m[1], escape(origin))}"', body)
    return (f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{escape(article.title)}</title>'
            f'<meta name="author" content="{escape(article.author)}"><style>{PDF_STYLE}</style></head>'
            f'<body>{body}</body></html>')


def pdf_fetcher():
    from weasyprint.urls import URLFetcher  # WeasyPrint loads Pango; only an export pays for it.

    class AllowlistFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            if not url.startswith(PDF_RESOURCES):
                raise ValueError(f'Recurso no permitido en el PDF: {url}')
            return super().fetch(url, headers)

    # No redirects, so an allowed URL cannot lead to another host.
    return AllowlistFetcher(timeout=10, allow_redirects=False)


@login_required
def article_export(request, slug):
    from weasyprint import HTML
    article = get_object_or_404(visible_articles(request.user).defer('pdf'), slug=slug)
    origin = request.build_absolute_uri('/').rstrip('/')
    # The base is this export's URL, not origin + '/': WeasyPrint reads {origin}/#/... as an anchor of its base document.
    pdf = HTML(string=article_html(article, origin), base_url=request.build_absolute_uri(request.path),
               url_fetcher=pdf_fetcher()).write_pdf()
    return HttpResponse(pdf, content_type='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename="{article.slug}.pdf"'})


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


def send_download(item):
    try:
        file = open(item.file.path, 'rb')
    except FileNotFoundError:
        raise Http404
    # FileResponse sets Content-Length and lets Gunicorn stream the file through wsgi.file_wrapper.
    return FileResponse(file, as_attachment=True, filename=item.filename)


@login_required
def download(request, slug):
    return send_download(get_object_or_404(Download, slug=slug, published=True))


@login_required
def latest_framework(request):
    """Permanent link: the newest published file in Framework, whatever its name or version."""
    item = Download.objects.filter(section='framework', published=True).order_by('-created_at', '-pk').first()
    if item is None:
        raise Http404
    return send_download(item)


@login_required
def downloads_page(request):
    published = Download.objects.filter(published=True)
    sections = [(key, label, [d for d in published if d.section == key]) for key, label in Download.SECTIONS]
    return render(request, 'downloads.md', {
        'sections': [s for s in sections if s[2]],
        'latest_url': request.build_absolute_uri(reverse(latest_framework)),
    }, content_type='text/markdown; charset=utf-8')


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
