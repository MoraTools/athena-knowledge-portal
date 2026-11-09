import mimetypes
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, strip_tags
from django.views.decorators.clickjacking import xframe_options_sameorigin
from markdown_it import MarkdownIt

from .models import ApiKey, Article, Download, DownloadEvent, ManagedImage, readable_articles, visible_articles
from .notify import notify_download


def article_image_upload(request):
    from .images import ImageUploadBusy, create_image, image_data
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST para subir una imagen.'}, status=405, headers={'Allow': 'POST'})
    user = request.user
    article_id = request.POST.get('article_id', '')
    permission = 'athena.change_article' if article_id else 'athena.add_article'
    if not user.is_authenticated or not user.is_active or not user.has_perm(permission):
        return JsonResponse({'error': 'Su cuenta no tiene permiso para insertar imágenes en este artículo.'}, status=403)
    if article_id:
        try:
            if not visible_articles(user, include_drafts=True).filter(pk=int(article_id)).exists():
                raise Http404
        except (ValueError, OverflowError):
            return JsonResponse({'error': 'El artículo no es válido.'}, status=400)
    if set(request.POST) - {'article_id'} or set(request.FILES) != {'file'}:
        return JsonResponse({'error': 'Seleccione una imagen PNG, JPEG, WebP o GIF.'}, status=400)
    try:
        return JsonResponse(image_data(create_image(request.FILES['file'], user)), status=201)
    except ImageUploadBusy as error:
        return JsonResponse({'error': ' '.join(error.messages)}, status=503, headers={'Retry-After': '2'})
    except ValidationError as error:
        return JsonResponse({'error': ' '.join(error.messages)}, status=400)


def send_article_image(request, image_id, *, include_drafts=True, allow_preview=True, signed=False):
    from .images import attached_image_ids, can_upload, image_path
    with transaction.atomic():
        image = get_object_or_404(ManagedImage, pk=image_id)
        # A valid signature was issued by a page that could read the image (HTML articles, editor preview).
        if not signed and image.pk not in attached_image_ids(visible_articles(request.user, include_drafts=include_drafts)):
            attached = image.pk in attached_image_ids(Article.objects.all())
            if attached or not allow_preview or image.uploader_id != request.user.pk or not can_upload(request.user):
                raise Http404
        try:
            file = image_path(image).open('rb')
        except (OSError, ValidationError):
            raise Http404
        return FileResponse(file, content_type=image.content_type)


def admin_view_on_site(request, content_type_id, object_id):
    """The admin "Ver en el sitio" redirect, which would otherwise reveal any article's address by its id."""
    from django.contrib import admin
    from django.contrib.contenttypes.models import ContentType
    from django.contrib.contenttypes.views import shortcut
    if content_type_id == ContentType.objects.get_for_model(Article).pk and not (
            object_id.isdigit() and readable_articles(request.user).filter(pk=int(object_id)).exists()):
        raise Http404
    return admin.site.admin_view(shortcut)(request, content_type_id, object_id)


def article_image(request, image_id):
    from .images import valid_image_signature
    if request.method not in ('GET', 'HEAD'):
        return HttpResponse(status=405, headers={'Allow': 'GET, HEAD'})
    return send_article_image(request, image_id, signed=valid_image_signature(image_id, request.GET.get('sig', '')))


class HtmlText(HTMLParser):
    """Readable text of an HTML article: headings and prose, without scripts, styles, or templates."""
    SKIP = {'script', 'style', 'template', 'noscript', 'title', 'svg'}
    INLINE = {'a', 'abbr', 'b', 'code', 'em', 'i', 'kbd', 'mark', 's', 'small', 'span', 'strong', 'sub', 'sup', 'u'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag not in self.INLINE:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag not in self.INLINE:
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_text(body):
    parser = HtmlText()
    parser.feed(body)
    parser.close()
    return re.sub(r'\s+', ' ', ''.join(parser.parts)).strip()


def search_text(body):
    body = re.sub(r'<!--.*?-->', ' ', body, flags=re.S)
    body = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', body)
    return re.sub(r'\s+', ' ', unescape(strip_tags(body)).translate(str.maketrans('', '', '`*~'))).strip()


def search_entry(article):
    if article.format == 'html':
        # Headings live inside the sandboxed frame; results link to the article itself.
        return {'title': article.title, 'kind': article.kind, 'summary': article.summary, 'author': article.author,
                'date': timezone.localdate(article.updated_at).isoformat(), 'tags': article.tags, 'route': '#/content/' + article.slug,
                'pdf': '/pdf/' + article.slug + '.pdf' if article.pdf_name else '', 'text': html_text(article.body),
                'headings': []}
    body = article_body(article)
    lines = body.splitlines(keepends=True)
    tokens = MARKDOWN.parse(body)
    headings = [(token, tokens[i + 1]) for i, token in enumerate(tokens) if token.type == 'heading_open']
    return {
        'title': article.title, 'kind': article.kind, 'summary': article.summary,
        'author': article.author, 'date': timezone.localdate(article.updated_at).isoformat(), 'tags': article.tags,
        'route': '#/content/' + article.slug, 'pdf': '/pdf/' + article.slug + '.pdf' if article.pdf_name else '',
        'text': search_text(article.body), 'headings': [
            {'level': int(heading.tag[1:]), 'raw': inline.content,
             'title': search_text(MARKDOWN.renderer.render([inline], MARKDOWN.options, {})),
             'text': search_text(''.join(lines[heading.map[1]:headings[i + 1][0].map[0] if i + 1 < len(headings) else len(lines)]))}
            for i, (heading, inline) in enumerate(headings)
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


def search_index(request):
    entries = [search_entry(a) for a in visible_articles(request.user).defer('pdf')]
    if request.user.is_authenticated:
        entries += [download_entry(d) for d in Download.objects.filter(published=True)]
    return JsonResponse(entries, safe=False)


def article_body(article):
    """The article Markdown the reader and the PDF export share: title heading, draft notice, original PDF link."""
    body = article.body
    if article.format == 'html':
        # src/app.js replaces this marker with the sandboxed frame; DOMPurify drops a literal iframe.
        body = (f'<div class="html-article" data-src="/article-html/{article.slug}/" '
                f'data-source="/article-html/{article.slug}/source" data-title="{escape(article.title)}"></div>')
    if not re.match(r'^\s*#\s+', body):
        body = f'# {escape(article.title)}\n\n' + body
    if not article.published:
        body = '> **Borrador.** Solo visible para editores.\n\n' + body
    if article.pdf_name:
        body += f'\n\n<p class="article-pdf"><a href="/pdf/{article.slug}.pdf">Abrir PDF original</a></p>\n'
    return body


# 24px line icons, the stroke style of the "Copiar página" button (src/config.js).
EDIT_ICON = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4"/></svg>'
EXPORT_ICON = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 4v11m-5-4 5 5 5-5M4 20h16"/></svg>'


def article_markdown(request, slug):
    article = get_object_or_404(visible_articles(request.user, include_drafts=True).defer('pdf'), slug=slug)
    body = article_body(article)
    if article.is_restricted:
        # Only people who can read the article get here; the count names nobody.
        count = article.allowed_users.count()
        notice = f'<p class="article-access">Acceso restringido: {count} usuario{"" if count == 1 else "s"}.</p>'
        body = re.sub(r'^[ \t]*#[ \t]+[^\n]*', lambda title: f'{title[0]}\n\n{notice}', body, count=1, flags=re.M)
    body += f'\n\n<span class="article-context" data-article-kind="{escape(article.kind)}" hidden></span>\n'
    tools = []
    if request.user.has_perm('athena.change_article'):
        edit = reverse('admin:athena_article_change', args=[article.pk])
        tools.append(f'<a class="copy-page copy-page--ghost" href="{edit}">{EDIT_ICON}<span>Editar artículo</span></a>')
    if not article.pdf_only and article.format != 'html':
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


def pdf_fetcher(image_versions=None):
    from weasyprint.urls import URLFetcher, URLFetcherResponse  # Only an export loads Pango.
    from .images import MAX_BYTES, image_id_from_url, image_path
    import hashlib

    # The parent exporter supplies only images in the requesting article, with immutable content hashes.
    allowed = image_versions or {}

    class AllowlistFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            image_id = image_id_from_url(url)
            if image_id and str(image_id) in allowed:
                image = ManagedImage.objects.filter(pk=image_id, sha256=allowed[str(image_id)]).first()
                if image:
                    with image_path(image).open('rb') as file:
                        data = file.read(MAX_BYTES + 1)
                    if len(data) <= MAX_BYTES and hashlib.sha256(data).hexdigest() == image.sha256:
                        return URLFetcherResponse(url, data, {'Content-Type': image.content_type})
                raise ValueError('La imagen del artículo ya no está disponible.')
            if not url.startswith(PDF_RESOURCES):
                raise ValueError(f'Recurso no permitido en el PDF: {url}')
            return super().fetch(url, headers)

    # No redirects, so an allowed URL cannot lead to another host.
    return AllowlistFetcher(timeout=10, allow_redirects=False)


def article_export(request, slug):
    from .pdf_export import cached_export, ExportBusy
    # HTML articles have no PDF export; an attached PDF still opens through /pdf/<slug>.pdf.
    article = get_object_or_404(visible_articles(request.user, include_drafts=True).defer('pdf'), slug=slug, format='markdown')
    try:
        file = cached_export(article)
    except ExportBusy:
        return HttpResponse('No se pudo preparar el PDF. Intente de nuevo en unos segundos.', status=503,
                            headers={'Retry-After': '10'})
    if not visible_articles(request.user, include_drafts=True).filter(pk=article.pk, updated_at=article.updated_at).exists():
        file.close()
        raise Http404
    return FileResponse(file, as_attachment=True, filename=f'{article.slug}.pdf', content_type='application/pdf')


ARTICLE_BRIDGE = (Path(__file__).parent / 'static/athena/article-bridge.js').read_text(encoding='utf-8')
HTML_SANDBOX = 'allow-scripts allow-popups allow-popups-to-escape-sandbox'


def html_article_response(request, body, image_ids):
    """An author's HTML document for the reader's sandboxed frame, with signed images and the Athena bridge."""
    from .images import sign_image_urls
    body = sign_image_urls(body, image_ids)
    script = f'<script>{ARTICLE_BRIDGE}</script>'
    end = body.lower().rfind('</body>')
    body = body[:end] + script + body[end:] if end >= 0 else body + script
    # Opaque-origin documents do not match 'self' in every browser, so the origin is listed too.
    own = f"'self' {request.scheme}://{request.get_host()}"
    return HttpResponse(body, content_type='text/html; charset=utf-8', headers={'Content-Security-Policy': (
        f"sandbox {HTML_SANDBOX}; default-src 'none'; script-src 'unsafe-inline'; style-src {own} 'unsafe-inline'; "
        f"img-src {own} data: blob:; font-src {own} data:; media-src {own} data: blob:; connect-src 'none'; "
        "form-action 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; frame-ancestors 'self'"
    )})


@xframe_options_sameorigin
def article_html_document(request, slug):
    from .images import referenced_image_ids
    if request.method not in ('GET', 'HEAD'):
        return HttpResponse(status=405, headers={'Allow': 'GET, HEAD'})
    article = get_object_or_404(visible_articles(request.user, include_drafts=True).defer('pdf'), slug=slug, format='html')
    return html_article_response(request, article.body, referenced_image_ids(article.body, html=True))


def article_html_source(request, slug):
    """The saved HTML for "Copiar página", with the same access as the article."""
    article = get_object_or_404(visible_articles(request.user, include_drafts=True).defer('pdf'), slug=slug, format='html')
    return HttpResponse(article.body, content_type='text/plain; charset=utf-8',
                        headers={'Content-Security-Policy': "sandbox; default-src 'none'"})


@xframe_options_sameorigin
def article_html_preview(request):
    """The editor's live preview: unsaved HTML in the same sandboxed frame as the reader."""
    from .images import referenced_image_ids, usable_image_ids
    if request.method != 'POST':
        return HttpResponse(status=405, headers={'Allow': 'POST'})
    user = request.user
    if not user.is_authenticated or not user.is_active or not user.has_perm('athena.change_article'):
        return HttpResponse('Su cuenta no puede editar artículos HTML.', status=403, content_type='text/plain; charset=utf-8')
    body = request.POST.get('body', '')
    if len(body.encode('utf-8')) > 1024 * 1024:
        return HttpResponse('El contenido no puede superar 1 MiB.', status=400, content_type='text/plain; charset=utf-8')
    return html_article_response(request, body, usable_image_ids(referenced_image_ids(body, html=True), user))


@xframe_options_sameorigin  # The reader embeds the PDF in an iframe.
def pdf(request, slug):
    article = get_object_or_404(visible_articles(request.user, include_drafts=True), slug=slug)
    if not article.pdf:
        raise Http404
    disposition = 'attachment' if request.GET.get('download') else 'inline'
    return HttpResponse(bytes(article.pdf), content_type='application/pdf', headers={
        'Content-Disposition': f'{disposition}; filename="{article.slug}.pdf"',
        'Content-Security-Policy': "sandbox; default-src 'none'; frame-ancestors 'self'",
    })


def send_download(request, item):
    try:
        file = open(item.file.path, 'rb')
    except FileNotFoundError:
        raise Http404
    try:  # The row was read with the path just opened, so the snapshot names the bytes served.
        DownloadEvent.objects.create(user=request.user, username=request.user.get_username(), download=item,
                                     title=item.title, filename=item.filename, size=item.size, sha256=item.sha256,
                                     path=request.path)
        notify_download(request, item)
    except BaseException:
        file.close()
        raise
    # FileResponse sets Content-Length and lets Gunicorn stream the file through wsgi.file_wrapper.
    return FileResponse(file, as_attachment=True, filename=item.filename)


@login_required
def download(request, slug):
    return send_download(request, get_object_or_404(Download, slug=slug, published=True))


@login_required
def latest_framework(request):
    """Permanent link: the newest published file in Framework, whatever its name or version."""
    item = Download.objects.filter(section='framework', published=True).order_by('-created_at', '-pk').first()
    if item is None:
        raise Http404
    return send_download(request, item)


@login_required
def downloads_page(request):
    published = Download.objects.filter(published=True)
    sections = [(key, label, [d for d in published if d.section == key]) for key, label in Download.SECTIONS]
    return render(request, 'downloads.md', {
        'sections': [s for s in sections if s[2]],
        'latest_url': request.build_absolute_uri(reverse(latest_framework)),
    }, content_type='text/markdown; charset=utf-8')


def library(request, section):
    kinds = {'guides': ['guide'], 'tools': ['tool'], 'updates': ['guide', 'announcement', 'release']}
    articles = visible_articles(request.user).filter(kind__in=kinds[section]).defer('body', 'pdf').order_by('-updated_at', 'title')
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


def api_docs(request):
    try:
        return FileResponse((settings.BASE_DIR / 'API.md').open('rb'), content_type='text/markdown; charset=utf-8')
    except FileNotFoundError:
        raise Http404


_sidebar_cache = (None, [])
SIDEBAR_LINK = re.compile(r'\[([^\]]+)\]\(([^\s)]+)[^)]*\)')
# The code owns the grouping; a link that is not listed here falls into Biblioteca.
SIDEBAR_GROUPS = ['Biblioteca', 'Participar', 'Cuenta', 'Administración']
SIDEBAR_GROUP = {'/content/contributing.md': 'Participar', '/account.md': 'Cuenta', '/accounts/login/': 'Cuenta',
                 '/admin/': 'Administración', '/api.md': 'Administración'}


def sidebar_markdown(user):
    """The portal rail as nested markdown groups; src/app.js renders it in the reader, sidebar_links in the admin."""
    global _sidebar_cache
    file = settings.BASE_DIR / 'dist/_sidebar.md'
    mtime = file.stat().st_mtime
    if _sidebar_cache[0] != mtime:
        # Archivo is now the "Versiones anteriores" section of Descargas.
        _sidebar_cache = (mtime, [m[0].replace(f'[{m[1]}]', '[Feed]', 1) if m[2] == '/updates.md' else m[0]
                                 for m in SIDEBAR_LINK.finditer(file.read_text(encoding='utf-8-sig')) if m[1] != 'Archivo'])
    links = list(_sidebar_cache[1])
    if user.is_authenticated:
        links += ['[Mi cuenta](/account.md)']
    else:
        hidden = {'/downloads.md'}
        if not contributing_visible(user):
            hidden.add('/content/contributing.md')
        links = [link for link in links if SIDEBAR_LINK.match(link)[2] not in hidden]
        links += ['[Ingresar](/accounts/login/)']
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


def contributing_visible(user):
    return user.is_authenticated or visible_articles(user).filter(slug='contributing').exists()


def static_portal(request, path='index.html'):
    # An explicit allowlist prevents serving a database, source file, or a removed article.
    assets = path.startswith(('fonts/', 'assets/', 'vendor/')) or path in ('styles.css', 'app.js', 'config.js')
    public_pages = {'index.html', 'README.md', '_sidebar.md', 'search.md', 'not-found.md'}
    if not assets and path not in public_pages and not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    if assets:
        if path.startswith('vendor/'):
            file = settings.BASE_DIR / 'dist' / path
        else:
            file = settings.BASE_DIR / 'src' / path
    else:
        allowed = public_pages | {'catalog.json', 'api.md'}
        if path not in allowed:
            raise Http404
        if path == 'index.html':
            return render(request, 'index.html')
        if path == 'README.md':
            return render(request, 'home.md', {
                'has_articles': visible_articles(request.user).exists(),
                'show_contribute': contributing_visible(request.user),
            }, content_type='text/markdown; charset=utf-8')
        if path in ('search.md', 'not-found.md'):
            return render(request, path, content_type='text/markdown; charset=utf-8')
        file = settings.BASE_DIR / ('src' if path == 'index.html' else 'dist') / path
        if path == 'api.md':
            file = settings.BASE_DIR / 'API.md'  # The repository's API.md, the same file as /api/docs/.
    root = settings.BASE_DIR.resolve()
    if '..' in Path(path).parts or not file.resolve().is_relative_to(root) or not file.is_file():
        raise Http404
    if path == '_sidebar.md':
        return HttpResponse(sidebar_markdown(request.user), content_type='text/markdown; charset=utf-8')
    if path == 'api.md':
        return api_docs(request)
    response = FileResponse(file.open('rb'), content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
    if path.startswith('fonts/'):
        # HTML articles run in an opaque-origin frame; their font requests use CORS with Origin: null.
        response['Access-Control-Allow-Origin'] = '*'
    return response
