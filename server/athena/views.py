import mimetypes
import os
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.clickjacking import xframe_options_sameorigin
from markdown_it import MarkdownIt

from .admin import role_label
from .forms import SignInForm
from .models import (ApiKey, Article, Download, DownloadEvent, ManagedImage, PLACEMENT_TAGS, download_family,
                     readable_articles, release_key, visible_articles)
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
        return media_response(request, file, image.content_type)


BYTE_RANGE = re.compile(r'bytes=(\d*)-(\d*)')
RANGE_CHUNK = 8 * 1024 * 1024


class FileSlice:
    """The next length bytes of an open file; fileno() lets Gunicorn send them with sendfile."""

    def __init__(self, file, length):
        self.file, self.remaining, self.name = file, length, file.name

    def read(self, size=-1):
        data = self.file.read(self.remaining if size is None or size < 0 else min(size, self.remaining))
        self.remaining -= len(data)
        return data

    def fileno(self):
        return self.file.fileno()

    def close(self):
        self.file.close()


def media_response(request, file, content_type):
    """One byte range per request, which a video needs to seek (and Safari to play). Other Range forms get 200."""
    size = os.fstat(file.fileno()).st_size
    start, end, status = 0, size - 1, 200
    match = BYTE_RANGE.fullmatch(request.headers.get('Range', ''))
    if match and (match[1] or match[2]) and not (match[1] and match[2] and int(match[2]) < int(match[1])):
        if match[1]:
            start = int(match[1])
            # An open range gets one chunk, so a paused video does not hold one of the few server threads.
            end = min(size - 1, int(match[2]) if match[2] else start + RANGE_CHUNK - 1)
        else:
            start = max(0, size - int(match[2]))
        if start >= size or not match[1] and not int(match[2]):
            file.close()
            return HttpResponse(status=416, headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
        status = 206
    headers = {'Accept-Ranges': 'bytes', 'Content-Length': str(end - start + 1)}
    if status == 206:
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    if request.method == 'HEAD':
        file.close()
        return HttpResponse(status=status, content_type=content_type, headers=headers)
    file.seek(start)
    response = FileResponse(FileSlice(file, end - start + 1), status=status, content_type=content_type)
    for name, value in headers.items():
        response[name] = value
    return response


def share_target(slug):
    """The article a share link may describe: published, not restricted, with a share image on disk."""
    from .images import image_path
    article = (Article.objects.filter(slug=slug, published=True, is_restricted=False).exclude(share_image=None)
               .select_related('share_image').defer('body', 'pdf').first())
    try:
        return article if article and image_path(article.share_image).is_file() else None
    except ValidationError:
        return None


def share_page(request, slug):
    """Open Graph tags for link previews. Every other case is one bare redirect, so the route reveals nothing."""
    if request.method not in ('GET', 'HEAD'):
        return HttpResponse(status=405, headers={'Allow': 'GET, HEAD'})
    article = share_target(slug)
    reader = '/#/content/' + slug
    if article is None:
        return HttpResponseRedirect(reader)
    image = article.share_image
    image_url = request.build_absolute_uri(reverse('article_share_image', args=[slug])) + '?v=' + image.sha256[:16]
    return render(request, 'share.html', {'article': article, 'image': image, 'image_url': image_url, 'reader': reader,
                                          'share_url': request.build_absolute_uri(reverse('article_share', args=[slug]))})


def share_image(request, slug):
    """The share image while the share page shows it; a stable URL that never expires, unlike signed image URLs."""
    from django.utils.cache import get_conditional_response
    from .images import image_path
    if request.method not in ('GET', 'HEAD'):
        return HttpResponse(status=405, headers={'Allow': 'GET, HEAD'})
    article = share_target(slug)
    if article is None:
        raise Http404
    image = article.share_image
    # The page links ?v=<sha256 prefix>; only that versioned URL is immutable.
    headers = {'ETag': f'"{image.sha256}"', 'Cache-Control': 'public, max-age=31536000, immutable'
               if request.GET.get('v') == image.sha256[:16] else 'public, max-age=3600'}
    response = get_conditional_response(request, etag=headers['ETag'])
    if response is None:
        try:
            response = FileResponse(image_path(image).open('rb'), content_type=image.content_type)
        except OSError:
            raise Http404
    for name, value in headers.items():
        response[name] = value
    return response


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
    """Readable text of an article: headings and prose, without scripts, styles, templates, controls or hidden text.

    One pass gives two texts: parts (everything readable, for matching) and prose (the same without code blocks
    and with "…" for inline code, the source of result excerpts). With blocks_only (an HTML article, whose cards put
    titles and link labels between sentences), prose keeps only text in paragraph-level blocks, outside links and headings,
    one block per line, and headings records each h2[id] and h3[id] with its place in both texts.
    """
    SKIP = {'script', 'style', 'template', 'noscript', 'title', 'svg', 'button', 'video'}
    CODE = {'pre', 'code'}
    INLINE = {'a', 'abbr', 'b', 'code', 'em', 'i', 'kbd', 'mark', 's', 'small', 'span', 'strong', 'sub', 'sup', 'u'}
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
    BLOCKS = {'p', 'li', 'dd', 'td', 'blockquote', 'figcaption'}
    LABELS = {'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    def __init__(self, blocks_only=False):
        super().__init__(convert_charrefs=True)
        # Open counts of BLOCKS and LABELS elements; None when every text is prose.
        self.open = {'block': 0, 'label': 0} if blocks_only else None
        # skips: open skipped elements as [tag, its open count, text held since it opened, prose held, hides text].
        # A code element holds only prose: its text stays in parts.
        self.parts, self.prose, self.skips = [], [], []
        self.headings, self.heading = [], None

    def out(self):
        text = next((skip[2] for skip in reversed(self.skips) if skip[4]), self.parts)
        return text, self.skips[-1][3] if self.skips else self.prose

    def space(self, tag):
        if tag not in self.INLINE:
            for target in self.out():
                target.append(' ')

    def release(self, depth):
        # A skipped element that never closes hides nothing: its held text goes back in place.
        while len(self.skips) > depth:
            _, _, text, prose, hides = self.skips.pop()
            out_text, out_prose = self.out()
            if hides:
                out_text.extend(text)
            out_prose.extend(prose)

    def count(self, tag, step):
        if step < 0 and tag in self.BLOCKS:
            self.out()[1].append(BLOCK_END)  # In both modes, so an excerpt never joins two blocks.
        if self.open is not None and (tag in self.BLOCKS or tag in self.LABELS):
            key = 'block' if tag in self.BLOCKS else 'label'
            self.open[key] = max(0, self.open[key] + step)  # A stray end tag never goes below zero.

    def handle_starttag(self, tag, attrs):
        self.count(tag, 1)
        # Only outside skipped elements, where both texts grow in place: the recorded offsets stay true.
        if self.open is not None and tag in ('h2', 'h3') and not self.skips and not self.heading and dict(attrs).get('id'):
            self.heading = {'tag': tag, 'id': dict(attrs)['id'], 'start': len(self.parts), 'prose': len(self.prose)}
            self.headings.append(self.heading)
        hides = tag in self.SKIP or ('aria-hidden', 'true') in attrs
        if tag not in self.VOID and (hides or tag in self.CODE):
            if not hides:
                self.space(tag)
            self.skips.append([tag, 1, [], [], hides])
            return
        if self.skips and tag == self.skips[-1][0]:
            self.skips[-1][1] += 1
        self.space(tag)

    def handle_endtag(self, tag):
        self.count(tag, -1)
        if self.heading and tag == self.heading['tag'] and not self.skips:
            self.heading['end'], self.heading = len(self.parts), None
        depth = next((i for i in range(len(self.skips) - 1, -1, -1) if self.skips[i][0] == tag), None)
        if depth is not None:
            self.release(depth + 1)
            self.skips[depth][1] -= 1
            if not self.skips[depth][1]:
                if self.skips.pop()[4]:  # Closed normally: drop what it held.
                    return
                if tag == 'code' and not any(skip[0] == 'pre' for skip in self.skips):
                    self.out()[1].append('…')  # Dropped inline code keeps its place, so the sentence still reads.
        self.space(tag)

    def handle_data(self, data):
        text, prose = self.out()
        text.append(data)
        if self.open is None or self.open['block'] and not self.open['label']:
            prose.append(data)

    def close(self):
        super().close()
        self.release(0)


BLOCK_END = '\ue000'  # Marks a block end in prose; not whitespace, so it outlives the folding and becomes "\n".


def fold(parts):
    return re.sub(r' ?\ue000[\ue000 ]*', '\n', re.sub(r'\s+', ' ', ''.join(parts))).strip()


def parse_html(body, blocks_only=False):
    parser = HtmlText(blocks_only)
    parser.feed(body)
    parser.close()
    return parser


def html_texts(body, blocks_only=False):
    """(text, prose) of an HTML body; see HtmlText."""
    parser = parse_html(body, blocks_only)
    return fold(parser.parts), fold(parser.prose)


def html_headings(parser):
    """Search sections of a blocks_only parse, as Markdown entries give them, plus the element id."""
    headings = [heading for heading in parser.headings if 'end' in heading]  # An unclosed heading has no title.
    ends = [(heading['start'], heading['prose']) for heading in headings[1:]] + [(len(parser.parts), len(parser.prose))]
    sections = []
    for heading, (end, prose_end) in zip(headings, ends):
        title = fold(parser.parts[heading['start']:heading['end']])
        sections.append({'level': int(heading['tag'][1]), 'raw': title, 'title': title,
                         'text': fold(parser.parts[heading['end']:end]),
                         'prose': fold(parser.prose[heading['prose']:prose_end]), 'id': heading['id']})
    return sections


def html_text(body):
    return html_texts(body)[0]


def search_text(body):
    # Rendered, so fence info strings, backslash escapes and Markdown marks never reach an excerpt.
    return html_text(MARKDOWN.render(body))


def search_entry(article):
    if article.format == 'html':
        # Headings live inside the sandboxed frame; their ids let a result open the section.
        parser = parse_html(article.body, blocks_only=True)
        return {'title': article.title, 'kind': article.kind, 'summary': article.summary, 'author': article.author,
                'date': timezone.localdate(article.updated_at).isoformat(), 'tags': article.tags, 'route': '#/content/' + article.slug,
                'pdf': '/pdf/' + article.slug + '.pdf' if article.pdf_name else '', 'text': fold(parser.parts),
                'prose': fold(parser.prose), 'headings': html_headings(parser)}
    # One parse and one render per article: the text is the stored body, the sections come from the reader's body.
    prefix, body, suffix = article_parts(article)
    env = {}
    body_tokens = MARKDOWN.parse(body, env)
    tokens = MARKDOWN.parse(prefix) + body_tokens + MARKDOWN.parse(suffix)
    starts = [i for i, token in enumerate(tokens) if token.type == 'heading_open'] + [len(tokens)]

    def texts(part):
        return html_texts(MARKDOWN.renderer.render(part, MARKDOWN.options, env))

    text, prose = texts(body_tokens)
    sections = [(a, *texts(tokens[a + 3:b])) for a, b in zip(starts, starts[1:])]
    return {
        'title': article.title, 'kind': article.kind, 'summary': article.summary,
        'author': article.author, 'date': timezone.localdate(article.updated_at).isoformat(), 'tags': article.tags,
        'route': '#/content/' + article.slug, 'pdf': '/pdf/' + article.slug + '.pdf' if article.pdf_name else '',
        'text': text, 'prose': prose, 'headings': [
            {'level': int(tokens[a].tag[1:]), 'raw': tokens[a + 1].content, 'title': texts([tokens[a + 1]])[0],
             'text': section_text, 'prose': section_prose}
            for a, section_text, section_prose in sections
        ],
    }


def download_entry(download):
    section = download.get_section_display()
    return {
        'title': download.title, 'kind': 'download', 'section': section,
        # One fixed sentence per section, which suite-i18n.js translates; the reader formats size in its language.
        'summary': f'Archivo aprobado en {section}.', 'size': download.size,
        'author': '', 'date': '', 'tags': [section, Path(download.filename).suffix.lstrip('.').upper()],
        'route': '/downloads/' + download.slug, 'pdf': '', 'text': f'{download.filename} {download.note}',
        'prose': download.note, 'headings': [],
    }


def release_rows():
    """{release_key(title): Descargas row id} of the published files; of two files with one title, the newest."""
    return {release_key(d.title): 'download-file-' + d.slug
            for d in Download.objects.filter(published=True).order_by('created_at', 'pk').only('title', 'slug')}


def search_index(request):
    entries = [search_entry(a) for a in visible_articles(request.user).defer('pdf')]
    if request.user.is_authenticated:
        rows = release_rows()
        for entry in entries:
            if entry['kind'] == 'release' and release_key(entry['title']) in rows:
                entry['download'] = rows[release_key(entry['title'])]
        entries += [download_entry(d) for d in Download.objects.filter(published=True)]
    return JsonResponse(entries, safe=False)


def article_body(article):
    """The article Markdown the reader and the PDF export share: title heading, draft notice, original PDF link."""
    return ''.join(article_parts(article))


def article_parts(article):
    """article_body as (added before, body, added after)."""
    body, prefix, suffix = article.body, '', ''
    if article.format == 'html':
        # src/app.js replaces this marker with the sandboxed frame; DOMPurify drops a literal iframe.
        body = (f'<div class="html-article" data-src="/article-html/{article.slug}/" '
                f'data-source="/article-html/{article.slug}/source" data-title="{escape(article.title)}"></div>')
    if not re.match(r'^\s*#\s+', body):
        prefix = f'# {escape(article.title)}\n\n'
    if not article.published:
        prefix = '> **Borrador.** Solo visible para editores.\n\n' + prefix
    if article.pdf_name:
        suffix = f'\n\n<p class="article-pdf"><a href="/pdf/{article.slug}.pdf">Abrir PDF original</a></p>\n'
    return prefix, body, suffix


# 24px line icons, the stroke style of the "Copiar página" button (src/config.js).
EDIT_ICON = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4"/></svg>'
EXPORT_ICON = ('<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8l-5-5Zm0 0v5h5'
               'M12 11v6m-3-3 3 3 3-3"/></svg>')  # A document, not the Descargas arrow.


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
# Theme A in print: the light tokens and the local Inter and Cormorant files of suite-tokens.css (one source).
SUITE_TOKENS = (settings.BASE_DIR / 'src/assets/suite-tokens.css').read_text(encoding='utf-8')
FONT_DIR = settings.BASE_DIR / 'src/fonts'
PDF_FONTS = {(FONT_DIR / name).as_uri(): FONT_DIR / name for name in re.findall(r"url\('/fonts/([\w.-]+)'\)", SUITE_TOKENS)}
PDF_STYLE = (''.join(re.findall(r'@font-face\{[^}]*\}', SUITE_TOKENS)).replace("url('/fonts/", f"url('{FONT_DIR.as_uri()}/")
             + ':root{' + re.search(r':root:not\(\[data-theme\]\)[^{]*\{([^}]*)\}', SUITE_TOKENS)[1] + '}' + """
@page { size: A4; margin: 2cm;
  /* The share link has a line of its own and never wraps, so it is never broken inside the slug; a longer line is cut. */
  @bottom-left { content: string(title) "\\A" string(address); white-space: pre; overflow: hidden; text-overflow: ellipsis;
    vertical-align: top; padding-top: 6mm; font: 8pt/1.5 "DejaVu Sans Mono", monospace; color: var(--text-muted) }
  @bottom-right { content: counter(page) " / " counter(pages); white-space: pre; vertical-align: top; padding-top: 6mm;
    font: 8pt/1.5 "DejaVu Sans Mono", monospace; color: var(--text-muted); text-align: right } }
body > h1:first-of-type { string-set: title content() }
.article-meta { margin: -.2em 0 1.4em; font: 9pt/1.5 "DejaVu Sans Mono", monospace; color: var(--text-muted) }
body { font: 10.5pt/1.55 Inter, sans-serif; color: var(--text) }
h1, h2, h3, h4, h5, h6 { color: var(--text); font-weight: 650; line-height: 1.3; margin: 1.2em 0 .5em; break-after: avoid }
h1, h2 { font-family: Cormorant, serif; font-weight: 600 }
h1 { font-size: 26pt; line-height: 1.15; margin-top: 0 } h2 { font-size: 18pt } h3 { font-size: 12.5pt } h4, h5, h6 { font-size: 11pt }
a { color: var(--accent-text) }
code, pre { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; background: var(--surface-strong) }
code { padding: 0 .2em }
:not(pre) > code { white-space: nowrap } :not(pre) > code.long { white-space: normal; overflow-wrap: anywhere }
pre { padding: .6em .8em; border: 1px solid var(--border); border-radius: 4px; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid }
pre code { padding: 0 }
img { max-width: 100%; break-inside: avoid }
table { border-collapse: collapse; margin: .8em 0 }
th, td { border: .5pt solid var(--border-strong); padding: .3em .5em; text-align: left; vertical-align: top }
blockquote { margin: .8em 0; padding: 0 1em; border-left: 3pt solid var(--border); color: var(--text-muted) }
""")


def export_href(href, origin):
    """The PDF is read outside the site: reader routes point back to it."""
    if href.startswith('#/'):
        return origin + '/' + href
    if match := re.fullmatch(r'/content/([a-z0-9-]+)(?:\.md)?(\?[^#]*)?', href):
        return f'{origin}/#/content/{match[1]}{match[2] or ""}'
    return href  # Other root-relative links resolve against base_url; absolute links stay.


# A PDF cannot play a video: it becomes a link to the video file, which keeps the article's access rule.
PDF_VIDEO = re.compile(r'<video\b[^>]*>.*?</video\s*>', re.I | re.S)


def video_link(match):
    source = re.search(r'(?<![\w-])src\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', match[0])
    return f'<a href="{escape(unescape(source[1] or source[2] or ""))}">Ver video</a>' if source else ''


# The reader's dates (Intl, es): '14 nov 2026', '27 sept 2026'; Django's Spanish short month for September is 'sep'.
READER_MONTHS = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sept', 'oct', 'nov', 'dic')


def article_html(article, origin):
    body = PDF_VIDEO.sub(video_link, MARKDOWN.render(article_body(article)))
    body = re.sub(r'\bhref="([^"]*)"', lambda m: f'href="{export_href(m[1], escape(origin))}"', body)
    # Short inline code stays on one line, as in the reader; a long value may wrap anywhere.
    # 24 characters: the same number as markLongCode in src/app.js (round 5 contract 1).
    body = re.sub(r'<code>([^<]*)</code>', lambda m: f'<code class="long">{m[1]}</code>' if len(unescape(m[1])) > 24 else m[0], body)
    # The reader's meta line under the h1 (type · author · Actualizado <date> · tags), and the share address in the footer.
    meta = [article.get_kind_display(), article.author]
    if article.updated_at:
        day = timezone.localdate(article.updated_at)
        meta.append(f'Actualizado {day.day} {READER_MONTHS[day.month - 1]} {day.year}')
    meta.append(', '.join(article.topic_tags))
    body = body.replace('</h1>', f'</h1>\n<p class="article-meta">{escape(" · ".join(filter(None, meta)))}</p>', 1)
    address = f'{origin}/s/{article.slug}'
    # A long link gets a smaller footer, so it fits the 170 mm text width (a mono glyph is 0.602 em) down to 5 pt.
    size = max(5, min(8, 170 / 25.4 * 72 / (0.602 * len(address))))
    address = address.replace('\\', '\\\\').replace('"', '\\"')
    return (f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{escape(article.title)}</title>'
            f'<meta name="author" content="{escape(article.author)}"><style>{PDF_STYLE}html {{ string-set: address "{address}" }}'
            f'@page {{ @bottom-left {{ font-size: {size:.2f}pt }} @bottom-right {{ font-size: {size:.2f}pt }} }}'
            f'</style></head><body>{body}</body></html>')


def pdf_fetcher(image_versions=None):
    from weasyprint.urls import URLFetcher, URLFetcherResponse  # Only an export loads Pango.
    from .images import MAX_BYTES, image_id_from_url, image_path
    import hashlib

    # The parent exporter supplies only images in the requesting article, with immutable content hashes.
    allowed = image_versions or {}

    class AllowlistFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            if url in PDF_FONTS:
                return URLFetcherResponse(url, PDF_FONTS[url].read_bytes(), {'Content-Type': 'font/woff2'})
            image_id = image_id_from_url(url)
            if image_id and str(image_id) in allowed:
                image = ManagedImage.objects.filter(pk=image_id, sha256=allowed[str(image_id)]).exclude(format='mp4').first()
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


def article_status(request, slug):
    """Online or offline for the links the article marks with data-athena-status; same access as the article."""
    from .link_status import statuses
    if request.method != 'GET':
        return HttpResponse(status=405, headers={'Allow': 'GET'})
    article = get_object_or_404(visible_articles(request.user, include_drafts=True).defer('pdf'), slug=slug, format='html')
    return JsonResponse(statuses(article.body))


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


def current_framework():
    """The newest published file in Framework, whatever its name or version; Descargas marks it as current."""
    return Download.objects.filter(section='framework', published=True).order_by('-created_at', '-pk').first()


@login_required
def latest_framework(request):
    """Permanent link: the current Framework file."""
    item = current_framework()
    if item is None:
        raise Http404
    return send_download(request, item)


class SignInView(LoginView):
    authentication_form = SignInForm


@login_required
def downloads_page(request):
    published = list(Download.objects.filter(published=True))
    notes = {release_key(title): slug for title, slug in visible_articles(request.user).filter(kind='release')
             .order_by('updated_at', 'pk').values_list('title', 'slug')}
    for item in published:  # Contract 2: the release notes of a file and the family Versiones anteriores groups by.
        item.notes_slug, item.family = notes.get(release_key(item.title), ''), download_family(item.title)
    sections = [(key, label, [d for d in published if d.section == key]) for key, label in Download.SECTIONS]
    current = current_framework()
    return render(request, 'downloads.md', {
        'sections': [s for s in sections if s[2]],
        'current_pk': current.pk if current else None,
        'latest_url': request.build_absolute_uri(reverse(latest_framework)),
    }, content_type='text/markdown; charset=utf-8')


def library(request, section):
    kinds = {'guides': ['guide'], 'tools': ['tool'], 'updates': ['announcement', 'release']}
    articles = list(visible_articles(request.user).filter(kind__in=kinds[section]).defer('body', 'pdf').order_by('-updated_at', 'title'))
    if section == 'updates' and request.user.is_authenticated:
        rows = release_rows()
        for article in articles:  # A Versión card links its file; otherwise the approved download_file, as other cards.
            article.download_row = (article.kind == 'release' and rows.get(release_key(article.title))
                                    or article.download_file and article.download_row_id)
    tags = sorted({tag for article in articles for tag in article.tags})
    return render(request, 'library.md', {'section': section, 'articles': articles, 'tags': tags},
                  content_type='text/markdown; charset=utf-8')


@login_required
def account_markdown(request):
    """Mi cuenta, rendered by Docsify at /#/account; the logout form posts with the token rendered here."""
    user = request.user
    return render(request, 'account.md', {
        'is_admin': user.is_staff,
        'role': role_label(user),
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


def sidebar_markdown(request):
    """The portal rail as nested markdown groups; src/app.js renders it in the reader, sidebar_links in the admin."""
    from django.contrib import admin
    global _sidebar_cache
    user = request.user
    file = settings.BASE_DIR / 'dist/_sidebar.md'
    mtime = file.stat().st_mtime
    if _sidebar_cache[0] != mtime:
        # Archivo is now the "Versiones anteriores" section of Descargas; the feed has one name, as in its h1 and crumbs.
        _sidebar_cache = (mtime, [m[0].replace(f'[{m[1]}]', '[Actualizaciones]', 1) if m[2] == '/updates.md' else m[0]
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
        links += ['[Administración](/admin/ ":ignore")', '[API para agentes](/api.md)']
        # The admin pages the user may open, as the admin lists them: the same items on reader and admin pages.
        links += [f'[{model["name"]}]({model["admin_url"]} ":ignore")'
                  for app in admin.site.get_app_list(request) for model in app['models'] if model['admin_url']]
    groups = {group: [] for group in SIDEBAR_GROUPS}
    for link in links:
        href = SIDEBAR_LINK.match(link)[2]
        groups[SIDEBAR_GROUP.get(href, 'Administración' if href.startswith('/admin/') else 'Biblioteca')].append(link)
    return ''.join(f'- {group}\n' + ''.join(f'  - {link}\n' for link in items)
                   for group, items in groups.items() if items)


def sidebar_links(request):
    """[(group, [(label, href), ...]), ...]; Docsify routes a /page.md link to /#/page."""
    groups = []
    for line in sidebar_markdown(request).splitlines():
        if line.startswith('- '):
            groups.append((line[2:], []))
        else:
            label, href = SIDEBAR_LINK.search(line).groups()
            groups[-1][1].append((label, '/#' + href[:-3] if href.endswith('.md') else href))
    return groups


def robots(request):
    # Some link-preview crawlers obey robots.txt; share pages still carry noindex.
    return HttpResponse('User-agent: *\nAllow: /s/\nDisallow: /\n', content_type='text/plain; charset=utf-8')


def contributing_visible(user):
    return user.is_authenticated or visible_articles(user).filter(slug='contributing').exists()


FIRST_STEPS_TAG = PLACEMENT_TAGS[0]


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
            if request.GET.get('q', '').strip():  # The account pages' search form: a plain GET, as they run no app.js.
                return HttpResponseRedirect('/#/search?q=' + quote(request.GET['q'].strip()))
            return render(request, 'index.html')
        if path == 'README.md':
            # The library's access rule; updated_at, so an edit moves an article to the top (DL-0022).
            readable = visible_articles(request.user).defer('body', 'pdf')
            recent = readable.order_by('-updated_at', 'title')[:5]
            # Primeros pasos: editors tag articles 'primeros-pasos' (any case); the article date, which editors set, orders them.
            tagged = readable.filter(tags__icontains=FIRST_STEPS_TAG).order_by('date', 'title')
            first_steps = [a for a in tagged if FIRST_STEPS_TAG in (tag.lower() for tag in a.tags)][:5]
            return render(request, 'home.md', {
                'has_articles': bool(recent),
                'first_steps': first_steps,
                'recent': recent,
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
        return HttpResponse(sidebar_markdown(request), content_type='text/markdown; charset=utf-8')
    if path == 'api.md':
        return api_docs(request)
    response = FileResponse(file.open('rb'), content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
    if path.startswith('fonts/'):
        # HTML articles run in an opaque-origin frame; their font requests use CORS with Origin: null.
        response['Access-Control-Allow-Origin'] = '*'
    return response
