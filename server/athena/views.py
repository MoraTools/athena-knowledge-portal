import json
import mimetypes
import re
from html import unescape
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape, strip_tags

from .models import Article


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


@login_required
def search_index(request):
    legacy = json.loads((settings.BASE_DIR / 'dist/search-index.json').read_text(encoding='utf-8-sig'))
    downloads = [entry for entry in legacy if entry['kind'] == 'download']
    return JsonResponse([search_entry(a) for a in Article.objects.filter(published=True).defer('pdf')] + downloads, safe=False)


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
def pdf(request, slug):
    article = get_object_or_404(visible_articles(request.user), slug=slug)
    if not article.pdf:
        raise Http404
    return HttpResponse(bytes(article.pdf), content_type='application/pdf', headers={
        'Content-Disposition': f'inline; filename="{article.slug}.pdf"',
        'Content-Security-Policy': "sandbox; default-src 'none'",
    })


@login_required
def library(request, section):
    kinds = {'guides': ['guide'], 'tools': ['tool'], 'updates': ['guide', 'announcement', 'release']}
    articles = Article.objects.filter(published=True, kind__in=kinds[section]).defer('body', 'pdf')
    tags = sorted({tag for article in articles for tag in article.tags})
    return render(request, 'library.md', {'section': section, 'articles': articles, 'tags': tags},
                  content_type='text/markdown; charset=utf-8')


@login_required
def account(request):
    return render(request, 'account.html')


def health(request):
    Article.objects.exists()
    return JsonResponse({'status': 'ok'})


def api_schema(request):
    return FileResponse((settings.BASE_DIR / 'server/openapi.json').open('rb'), content_type='application/json')


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
        allowed = {'index.html', 'README.md', '_sidebar.md', 'search.md', 'downloads.md',
                   'framework.md', 'packages.md', 'exercises.md', 'archive.md', 'catalog.json'}
        if path not in allowed:
            raise Http404
        file = settings.BASE_DIR / ('src' if path == 'index.html' else 'dist') / path
    root = settings.BASE_DIR.resolve()
    if '..' in Path(path).parts or not file.resolve().is_relative_to(root) or not file.is_file():
        raise Http404
    if path == '_sidebar.md':
        text = file.read_text(encoding='utf-8-sig') + '\n- [Mi cuenta](/accounts/profile/ ":ignore")\n'
        if request.user.is_staff:
            text += '- [Administrar Athena](/admin/ ":ignore")\n'
        return HttpResponse(text, content_type='text/markdown; charset=utf-8')
    return FileResponse(file.open('rb'), content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
