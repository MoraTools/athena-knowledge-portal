import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';

const handlers = {};
const readerShell = {};
let outlineResize;
let outlineObserved;
const context = vm.createContext({
  URL,
  URLSearchParams,
  console,
  location: { hash: '#/', href: 'https://athena.moratechnology.com/#/', pathname: '/', origin: 'https://athena.moratechnology.com' },
  history: { state: null, replaceState(_state, _title, url) {
    context.location.href = url.href;
    context.location.hash = url.hash;
  } },
  matchMedia: () => ({ matches: false }),
  ResizeObserver: class {
    constructor(handler) { outlineResize = handler; }
    observe(target) { outlineObserved = target; }
  },
  navigator: { clipboard: { writeText() {} } },
  setTimeout() {}, clearTimeout() {}, Element: class {},
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  document: {
    addEventListener(name, handler) { handlers[name] = handler; },
    querySelector(selector) { return selector === 'div#main' ? readerShell : null; },
    querySelectorAll() { return []; },
    getElementsByTagName() { return []; },
    head: {}, documentElement: {}, readyState: 'loading', currentScript: null,
    body: {
      clientWidth: 1000,
      append() {},
      classList: { add() {}, remove() {}, toggle() {} }
    }
  },
  window: { addEventListener() {} }
});

context.window.document = context.document;
context.window.location = context.location;
vm.runInContext(readFileSync(new URL('../node_modules/docsify/dist/docsify.min.js', import.meta.url), 'utf8'), context);
assert.equal(context.window.Docsify.version, '5.0.0');
vm.runInContext(readFileSync(new URL('../src/config.js', import.meta.url), 'utf8'), context);
assert.equal(context.window.$docsify.skipLink, false, 'Athena supplies its own accessible skip link.');
vm.runInContext(readFileSync(new URL('../src/app.js', import.meta.url), 'utf8'), context);
assert.equal(outlineObserved, readerShell, 'Reader width changes must observe the content area beside the rail.');

const duplicateIds = context.docsifyHeadingIds('Repeated', [
  { level: 4, title: 'Detail', text: '' },
  { level: 2, title: 'Repeated', text: '' },
  { level: 3, title: 'Detail', text: '' }
]);
assert.equal(duplicateIds.map(({ level, id }) => level + ':' + id).join(','), '2:repeated-1,3:detail-1');

// Compare parsed heading sequences with the actual shipped compiler.
const readerCases = [
  '# Intro\n\n## Guide\n\nneedle',
  '# Guide\n\n```sh\n## Deploy\n```\n\n~~~\n## Deploy\n~~~\n\n## Deploy\n\nneedle',
  '# Intro\n\n## **Guide** and [Help](https://example.test)\n\nneedle\n\nGuide\n-----\n\nneedle',
  '# Intro\n\n> ## Guide\n>\n> needle\n\n#### Guide\n\n## Guide\n\nneedle',
  '## _Deploy_ `code` &amp; [Guide][ref]\n\nneedle\n\n[ref]: https://example.test',
  '# Intro\n\n## Café 👩‍💻  Guide--end\n\nneedle\n\n## Cafe\u0301 👩‍💻  Guide--end\n\nneedle',
  '# Intro\n\n## Guide :id=custom-anchor\n\nneedle'
];
const root = fileURLToPath(new URL('..', import.meta.url));
let readerEntries = { entries: [], pages: [] };
if (process.argv.includes('--reader-integration')) {
  const dataDir = mkdtempSync(join(tmpdir(), 'athena-reader-search-'));
  try {
    const result = spawnSync(join(root, '.venv/bin/python'), ['-c', `
import json, sys
from datetime import date, datetime, timezone
from types import SimpleNamespace
sys.path.insert(0, 'server')
import django
django.setup()
from athena.views import article_body, search_entry
from django.template.loader import render_to_string
from athena.models import Article
entries = []
for body in json.load(sys.stdin):
    article = SimpleNamespace(title='Guide', slug='guide', kind='guide', summary='Summary', author='Author',
                              date=date(2026, 10, 9), tags=[], body=body, pdf_name='', published=True, format='markdown',
                              updated_at=datetime(2026, 10, 9, 12, tzinfo=timezone.utc))
    entries.append(search_entry(article) | {'markdown': article_body(article)})
pages = []
sample = Article(title='Guide', slug='guide', kind='guide', summary='Summary', author='Author',
                 date=date(2026, 10, 9), tags=['RPA'], body='# Guide', published=True,
                 updated_at=datetime(2026, 10, 9, 12, tzinfo=timezone.utc))
for authenticated in (False, True):
    user = SimpleNamespace(is_authenticated=authenticated, get_username=lambda: 'Reader', last_login=None)
    for template in ('search.md', 'home.md', 'not-found.md', 'account.md'):
        pages.append({'name': template, 'authenticated': authenticated, 'markdown': render_to_string(template, {
            'user': user, 'has_articles': True, 'show_contribute': True, 'keys': [], 'is_admin': False
        })})
    for section in ('guides', 'tools', 'updates'):
        pages.append({'name': 'library.md', 'section': section, 'authenticated': authenticated,
                      'markdown': render_to_string('library.md', {
                          'user': user, 'section': section, 'articles': [sample], 'tags': ['RPA']
                      })})
pages.append({'name': 'downloads.md', 'markdown': render_to_string('downloads.md', {
    'sections': [('framework', 'Framework', [SimpleNamespace(title='File', filename='file.zip', size=100,
                                                          slug='file', note='Download note')]),
                 ('previous', 'Versiones anteriores', [SimpleNamespace(title='Old', filename='old.zip', size=10, slug='old', note='')])],
    'latest_url': 'https://athena.test/downloads/framework/latest'
})})
print(json.dumps({'entries': entries, 'pages': pages}))
  `], { cwd: root, input: JSON.stringify(readerCases), encoding: 'utf8', env: {
      ...process.env, DJANGO_SETTINGS_MODULE: 'athena.settings', ATHENA_SECRET_KEY: 'local-test-only-secret',
      ATHENA_DEBUG: '1', ATHENA_DATA_DIR: dataDir
    } });
    assert.equal(result.status, 0, result.stderr);
    readerEntries = JSON.parse(result.stdout);
  } finally {
    rmSync(dataDir, { recursive: true });
  }
}
const router = {
  getBasePath: () => '/', getCurrentPath: () => '/content/guide',
  parse: () => ({ file: '/content/guide.md' }), toURL: path => '#' + path
};
const legacySource = readFileSync(new URL('./build.ps1', import.meta.url), 'utf8');
const legacyParser = legacySource.match(/\$parser = @'\r?\n([\s\S]*?)\r?\n'@/)[1];
for (const body of readerCases) {
  const markdown = '# Migrated guide\n\n' + body;
  const html = new context.window.DocsifyCompiler(context.window.$docsify, router).compile(markdown);
  const renderedIds = [...html.matchAll(/<h([23]) id="([^"]+)"/g)].map((match) => match[2]);
  assert.doesNotMatch(html, /class="anchor"/, 'Headings keep their ids without a self-link tab stop.');
  const legacy = spawnSync(process.execPath, ['--input-type=module', '--eval', legacyParser,
    join(root, 'node_modules/marked/lib/marked.esm.js')], { input: JSON.stringify(markdown), encoding: 'utf8' });
  assert.equal(legacy.status, 0, legacy.stderr);
  const legacyHeadings = context.docsifyHeadingIds('Migrated guide', JSON.parse(legacy.stdout));
  assert.equal(legacyHeadings.map((heading) => heading.id).join(','), renderedIds.join(','), markdown);
}
for (const entry of readerEntries.entries) {
  const compiler = new context.window.DocsifyCompiler(context.window.$docsify, router);
  const html = compiler.compile(entry.markdown);
  const renderedIds = [...html.matchAll(/<h([23]) id="([^"]+)"/g)].map((match) => match[2]);
  const prepared = context.prepareSearchEntry(entry);
  assert.equal(prepared.headings.map((heading) => heading.id).join(','), renderedIds.join(','), entry.markdown);
  const snippet = context.findSnippet(prepared, context.searchTerms('needle'));
  assert.match(snippet.text, /needle/, entry.markdown);
  // The first section is the top of the article: no "Ir a" link to it.
  assert.ok(snippet.heading ? renderedIds.includes(snippet.heading.id) && snippet.heading !== prepared.headings[0] : true, entry.markdown);
}
for (const page of readerEntries.pages) {
  const compiler = new context.window.DocsifyCompiler(context.window.$docsify, router);
  const html = compiler.compile(page.markdown);
  assert.ok(!/<pre><code[^>]*>\s*&lt;/.test(html), `${page.name}: ${html}`);
  if (page.name === 'search.md') {
    for (const id of ['athena-search-type', 'search-result-count', 'search-results']) {
      assert.ok(html.includes(`id="${id}"`), `${page.name}: missing ${id}`);
    }
    assert.ok(html.includes('<option value="pdf">PDF</option>'));
    assert.equal(html.includes('<option value="download">Descargas</option>'), page.authenticated);
  }
  if (page.name === 'library.md') {
    assert.ok(html.includes(page.section === 'guides' ? '<article class="guide-row' : 'class="library-card'), `${page.name}: ${html}`);
    if (page.section === 'guides') {
      assert.ok(html.includes('<div id="guide-source" hidden>'));
      assert.ok(html.includes('<div id="guide-topics" class="guide-topics"></div>'));
      for (const removed of ['guide-index', 'guide-table', 'guide-scroll-hint', 'data-guide-view']) assert.ok(!html.includes(removed));
    }
  }
  if (page.name === 'home.md') assert.ok(!html.includes('home-search-slot'), 'Home keeps no second search field.');
  if (page.name === 'account.md') assert.ok(html.includes('action="/accounts/logout/"'), `${page.name}: ${html}`);
  if (page.name === 'downloads.md') {
    assert.ok(html.includes('href="/downloads/file"'), `${page.name}: ${html}`);
    // The section row links survive the sanitizer and name the section ids; the archive summary has both states.
    for (const key of ['framework', 'previous']) {
      assert.ok(html.includes(`href="#/downloads?id=download-${key}" data-download-jump="${key}"`), `${page.name}: ${html}`);
      // Section names are interface text: the row is not .guide-topic-jumps (author topics that suite-i18n.js skips).
      assert.ok(html.includes('<nav class="download-jumps"'), html);
      assert.ok(html.includes(`id="download-${key}"`), `${page.name}: ${html}`);
    }
    assert.ok(html.includes('<summary><span class="archive-closed">Mostrar 1 archivo</span><span class="archive-open">Ocultar archivos</span></summary>'), html);
    assert.ok(!html.includes('download-section"><option'), 'The section select is gone.');
    // Contract 3: each file row has an id, so a "Ver en Descargas" link can name it.
    for (const slug of ['file', 'old']) assert.ok(html.includes(`<article class="catalog-item" id="download-file-${slug}"`), html);
  }
}

const filler = 'relleno '.repeat(60);
const fold = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const excerptEntry = context.prepareSearchEntry({
  kind: 'guide',
  title: 'Ejemplo',
  summary: 'Resumen breve',
  author: 'Test',
  tags: ['Solución de problemas'],
  text: 'de ' + filler + 'problemas importantes y solución comprobada',
  prose: 'de ' + filler + 'problemas importantes y solución comprobada',
  headings: [{ level: 2, title: 'Introducción', text: 'de ' + filler, prose: 'de ' + filler }]
});
const excerpt = context.findSnippet(excerptEntry, context.searchTerms('Solución de problemas'));
assert.match(fold(excerpt.text), /problemas/);
assert.equal(excerpt.source, '');

const headingEntry = context.prepareSearchEntry({
  kind: 'guide',
  title: 'Resolver problemas',
  summary: 'Resumen breve',
  author: 'Test',
  tags: ['Solución de problemas'],
  text: 'de detalles adicionales',
  prose: 'de detalles adicionales',
  headings: [{ level: 2, title: 'Solución', text: 'de detalles adicionales', prose: 'de detalles adicionales' }]
});
const headingExcerpt = context.findSnippet(headingEntry, context.searchTerms('Solución de problemas'));
assert.match(fold(headingExcerpt.text), /solucion/);

// Code and paths are never the excerpt: a match only in code links its section with no excerpt line.
const codeEntry = context.prepareSearchEntry({
  kind: 'guide', title: 'Lectura de archivos', summary: 'Pasos para leer archivos', author: 'Test', tags: [],
  text: 'Abra el proceso. Guarde la evidencia en evidencias/excel-1 y revise. $ruta = "C:\\Bots\\excel"',
  prose: 'Abra el proceso. Guarde la evidencia en … y revise.',
  headings: [
    { level: 2, title: 'Antes de empezar', text: 'Abra el proceso.', prose: 'Abra el proceso.' },
    { level: 2, title: 'Pasos', text: 'Guarde la evidencia en evidencias/excel-1 y revise. $ruta = "C:\\Bots\\excel"', prose: 'Guarde la evidencia en … y revise.' }
  ]
});
const codeOnly = context.findSnippet(codeEntry, context.searchTerms('excel'));
assert.equal(codeOnly.text, '', 'A match only in code shows no excerpt.');
assert.equal(codeOnly.heading.title, 'Pasos');
const prosePick = context.findSnippet(codeEntry, context.searchTerms('evidencia'));
assert.equal(prosePick.text, 'Pasos. Guarde la evidencia en … y revise.', 'The excerpt is the prose of the matched section.');
assert.equal(context.findSnippet(codeEntry, context.searchTerms('abra')).heading, null, 'The first section gets no "Ir a" link.');
const shownOnly = context.findSnippet(codeEntry, context.searchTerms('archivos'));
assert.deepEqual([shownOnly.text, shownOnly.heading, shownOnly.source], ['', null, ''], 'Terms the title and summary show need no excerpt.');

const metadataEntry = context.prepareSearchEntry({
  kind: 'guide',
  title: 'Ejemplo',
  summary: 'Resumen breve',
  author: 'Test',
  tags: ['Especial'],
  text: 'Contenido sin la etiqueta',
  headings: []
});
const metadata = context.findSnippet(metadataEntry, context.searchTerms('Especial'));
assert.equal(metadata.text, '');
assert.equal(metadata.source, 'Coincidencia en: etiqueta');

// Round 4 #10: the excerpt never joins two text blocks (each "\n" line of the index prose is one block).
const blockEntry = context.prepareSearchEntry({ kind: 'guide', title: 'Bloques', summary: 'Resumen', author: 'Test', tags: [], text: '',
  prose: 'Primer bloque sin el término.\nSegundo bloque con aguja en medio.\nTercer bloque aparte.', headings: [] });
assert.equal(context.findSnippet(blockEntry, context.searchTerms('aguja')).text, 'Segundo bloque con aguja en medio.',
  'The excerpt is the block that holds the match, not its neighbours.');
// Round 4 #10, contract 2: an HTML article's sections keep the element ids of the index; "Ir a" only for a later section.
const htmlEntry = context.prepareSearchEntry({ kind: 'guide', route: '#/content/demos', title: 'Demos', summary: 'Resumen', author: 'Test', tags: [],
  text: 'Inicio de la página. Lee la cola de cuotas vencidas.', prose: 'Inicio de la página.\nLee la cola de cuotas vencidas.',
  headings: [{ level: 2, raw: 'Inicio', title: 'Inicio', text: 'Inicio de la página.', prose: 'Inicio de la página.', id: 'inicio' },
    { level: 3, raw: 'Cobranzas automáticas', title: 'Cobranzas automáticas', text: 'Lee la cola de cuotas vencidas.', prose: 'Lee la cola de cuotas vencidas.', id: 'demo-cobranzas' }] });
assert.deepEqual(htmlEntry.headings.map((heading) => heading.id), ['inicio', 'demo-cobranzas'], 'HTML sections keep their element ids.');
const htmlSnippet = context.findSnippet(htmlEntry, context.searchTerms('vencidas'));
assert.deepEqual([htmlSnippet.heading?.id, htmlSnippet.text], ['demo-cobranzas', 'Cobranzas automáticas. Lee la cola de cuotas vencidas.']);
assert.equal(context.findSnippet(htmlEntry, context.searchTerms('pagina')).heading, null, 'The first section gets no "Ir a" link.');
// A route to a frame section (#/content/demos?id=<id>) scrolls to it and focuses it once the frame reports its outline
// and its height, in either order (the bridge can send the outline first, while the page is still too short to scroll).
{
  const posted = [];
  const scrolls = [];
  const classes = new Set();
  vm.runInContext('htmlFrame = { isConnected: true, style: {}, classList: frameClasses, getBoundingClientRect: () => ({ top: 300 }), contentWindow: { postMessage: (data) => postedFrame.push(data) } }',
    Object.assign(context, { postedFrame: posted, frameClasses: { add: (name) => classes.add(name), contains: (name) => classes.has(name) } }));
  Object.assign(context.window, { scrollY: 0, scrollTo: (options) => scrolls.push(options.top) });
  context.requestAnimationFrame = () => 0;
  context.location.hash = '#/content/demos?id=demo-cobranzas';
  const outline = [{ id: 'inicio', text: 'Inicio', level: 1, top: 40 }, { id: 'demo-cobranzas', text: 'Cobranzas automáticas', level: 2, top: 900 }];
  context.updateHtmlOutline(outline);
  assert.equal(scrolls.length, 0, 'No scroll before the frame has its height.');
  const frame = vm.runInContext('htmlFrame', context);
  for (const value of [2400, 2600]) context.handleHtmlFrameMessage({ source: frame.contentWindow, data: { type: 'athena:height', value } });
  context.updateHtmlOutline(outline);
  assert.deepEqual(JSON.parse(JSON.stringify([scrolls, posted.filter(({ type }) => type === 'athena:focus')])), [[1200 - 16], [{ type: 'athena:focus', value: 'demo-cobranzas' }]],
    'The section shows below the command bar and takes focus, once.');
  vm.runInContext('htmlFrame = null; htmlOutline = []; htmlViewportPending = false', context);
  delete context.requestAnimationFrame;
  context.location.hash = '#/';
}

// One copy flow for page, link and code: copied state, the status line, the accessible name, then back after 2 s.
{
  const status = { textContent: '' };
  const label = { textContent: 'Copiar' };
  const classes = new Set();
  const attributes = new Map([['aria-label', 'Copiar código']]);
  const button = {
    isConnected: true, querySelector: () => label,
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name), contains: (name) => classes.has(name) },
    getAttribute: (name) => attributes.get(name) ?? null, setAttribute: (name, value) => attributes.set(name, value)
  };
  const copied = [];
  const timers = [];
  const querySelector = context.document.querySelector;
  context.navigator.clipboard.writeText = async (text) => { copied.push(text); };
  context.setTimeout = (callback) => timers.push(callback);
  context.document.querySelector = (selector) => (selector === '#copy-status' ? status : null);
  await context.copyWith(button, async () => 'code text', 'Copiar', 'Código copiado');
  assert.deepEqual([copied, label.textContent, classes.has('copied'), attributes.get('aria-label'), status.textContent],
    [['code text'], 'Copiado', true, 'Código copiado', 'Código copiado']);
  await context.copyWith(button, async () => 'again', 'Copiar', 'Código copiado');
  assert.equal(copied.length, 1, 'A second press while the button shows Copiado does nothing.');
  timers.forEach((callback) => callback());
  assert.deepEqual([label.textContent, classes.has('copied'), attributes.get('aria-label'), status.textContent], ['Copiar', false, 'Copiar código', '']);
  await context.copyWith(button, async () => { throw new Error('denied'); }, 'Copiar', 'Código copiado');
  assert.deepEqual([label.textContent, status.textContent], ['No se pudo copiar', 'No se pudo copiar']);
  context.setTimeout = () => {};
  context.navigator.clipboard.writeText = () => {};
  context.document.querySelector = querySelector;
}

// Crumb parents come from the article kind, not from the current section.
for (const [kind, parent] of [['guide', '#/guides'], ['tool', '#/tools'], ['announcement', '#/updates'], ['release', '#/updates'], ['page', undefined]]) {
  const levels = context.commandLevels('/content/example', '<Exact title>', kind);
  assert.equal(levels.at(-2).href, parent);
  assert.equal(levels.at(-1).label, '<Exact title>');
  // Biblioteca has no page, so it is text; every other level above the current one is a link.
  assert.ok(levels.slice(0, -1).every((level) => Boolean(level.href) === (level.label !== 'Biblioteca')));
  assert.equal(levels[1].label, 'Biblioteca');
  assert.ok(!levels.at(-1).href);
}
assert.equal(context.commandLevels('/content/private', 'Artículo no disponible', 'guide', true).length, 2, 'Unavailable content must disclose no section.');
// The phone back link goes to the nearest page; the home has none (round 4 #13).
{
  const back = { hidden: false, href: '', label: { textContent: '' }, querySelector() { return this.label; } };
  const box = { replaceChildren() {}, append() {} };
  const [querySelector, createElement] = [context.document.querySelector, context.document.createElement];
  context.document.querySelector = (selector) => ({ '.command-crumbs': box, '.command-parent': back })[selector] || null;
  context.document.createElement = () => ({ dataset: {}, setAttribute() {}, append() {} });
  context.updateCommand('/');
  assert.equal(back.hidden, true, 'The home has no back link.');
  context.updateCommand('/guides');
  assert.ok(!back.hidden && back.href === '#/' && back.label.textContent === 'Athena', 'A section goes back to the home.');
  Object.assign(context.document, { querySelector, createElement });
}
// A Descargas section link: when Docsify focuses the section, the focus moves to its heading (round 4 #6).
{
  const heading = { focused: 0, focus(options) { this.focused += 1; this.preventScroll = options.preventScroll; } };
  const section = { matches: (selector) => selector === '.download-section', querySelector: (selector) => (selector === 'h2' ? heading : null) };
  handlers.focusin({ target: section });
  handlers.focusin({ target: { matches: () => false } });
  handlers.focusin({ target: context.document });
  assert.deepEqual([heading.focused, heading.tabIndex, heading.preventScroll], [1, -1, true], 'Only a focused Descargas section hands its focus to the heading.');
}

// Query typing, filtering and submitting all update the sign-in return target without a hashchange.
const signIn = { href: '/accounts/login/' };
const input = { value: 'first', matches: (selector) => selector === '#athena-search-input' };
const filter = { value: '', matches: (selector) => selector === '#athena-search-type' };
context.document.querySelector = (selector) => ({ '#athena-search-input': input, '#athena-search-type': filter })[selector] || null;
context.document.querySelectorAll = (selector) => selector.startsWith('a[href') ? [signIn] : [];
context.location.href = 'https://athena.moratechnology.com/#/search?q=first';
context.location.hash = '#/search?q=first';
context.updateSignInLinks();
input.value = 'new query & café';
handlers.input({ target: input });
const returnTarget = () => new URL(signIn.href, context.location.href).searchParams.get('next');
assert.equal(returnTarget(), '/#/search?q=new+query+%26+caf%C3%A9');
filter.value = 'guide';
handlers.change({ target: filter });
assert.equal(returnTarget(), '/#/search?q=new+query+%26+caf%C3%A9&type=guide');
input.value = 'submitted';
handlers.submit({ preventDefault() {}, target: { matches: () => true, querySelector: () => input } });
assert.equal(returnTarget(), '/#/search?q=submitted&type=guide');

// A pause in typing on another page opens search with the typed words, while the field keeps focus.
const typingTimers = [];
context.setTimeout = (callback, delay) => typingTimers.push([callback, delay]);
context.location.hash = '#/guides';
input.value = 'typed words';
handlers.input({ target: input });
context.document.activeElement = null;
typingTimers[0][0]();
assert.equal(context.location.hash, '#/guides', 'Typing that lost focus does not change the page.');
context.document.activeElement = input;
handlers.input({ target: input });
assert.equal(typingTimers[1][1], 250);
typingTimers[1][0]();
assert.equal(context.location.hash, '#/search?q=typed+words');
// On an article a pause in typing keeps the reader on it; Enter opens search.
vm.runInContext("searchScope = ''", context);
context.location.hash = '#/content/example';
handlers.input({ target: input });
typingTimers.at(-1)[0]();
assert.equal(context.location.hash, '#/content/example', 'Typing on an article does not change the route.');
handlers.submit({ preventDefault() {}, target: { matches: () => true, querySelector: () => input } });
assert.equal(context.location.hash, '#/search?q=typed+words', 'Enter on an article opens search.');
context.setTimeout = () => {};
context.document.activeElement = undefined;

if (process.argv.includes('--reader-integration')) {
  const schema = JSON.parse(readFileSync(new URL('../server/openapi.json', import.meta.url), 'utf8'));
  const [apiMajor, apiMinor] = schema.info.version.split('.').map(Number);
  assert.ok(apiMajor > 1 || (apiMajor === 1 && apiMinor >= 6), 'The API must not regress below its existing 1.6.0 version.');
  assert.equal(schema.components.schemas.ArticleInput.properties.is_public.type, 'boolean');
  assert.ok(schema.components.schemas.ArticleImage.properties.content_type.enum.includes('image/gif'));
  assert.ok(schema.paths['/article-images/{id}/'].get.responses['200'].content['image/gif']);
}

// An unavailable article is not a document outline; its heading is nested inside a section.
vm.runInContext(`
  location.hash = '#/content/private';
  document.querySelector = (selector) => selector === '.markdown-section'
    ? { querySelector: () => ({}) }
    : null;
  buildPageTree();
`, context);
// A small DOM exercises the sorter without adding a browser or DOM dependency.
class Element {
  constructor(tag, text = '') {
    this.tagName = tag.toUpperCase();
    this.childNodes = text ? [{ textContent: text, parentElement: this }] : [];
    this.dataset = {};
    this.attributes = new Map();
    this.listeners = {};
    this.colSpan = this.rowSpan = 1;
  }
  get textContent() { return this.childNodes.map((child) => child.textContent).join(''); }
  set textContent(text) { this.childNodes = [{ textContent: text, parentElement: this }]; }
  get children() { return this.childNodes; }
  get rows() { return this.childNodes.filter((child) => child.tagName === 'TR'); }
  get cells() { return this.childNodes.filter((child) => ['TD', 'TH'].includes(child.tagName)); }
  setAttribute(name, value) { this.attributes.set(name, value); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); if (name === 'tabindex') delete this.tabIndex; }
  get previousElementSibling() {
    const siblings = this.parentElement?.childNodes.filter((node) => node.tagName) || [];
    return siblings[siblings.indexOf(this) - 1] || null;
  }
  append(...children) {
    children.forEach((child) => {
      if (typeof child === 'string') child = { textContent: child };
      if (child.parentElement) child.parentElement.childNodes = child.parentElement.childNodes.filter((node) => node !== child);
      child.parentElement = this;
      this.childNodes.push(child);
    });
  }
  prepend(...children) {
    this.append(...children);
    this.childNodes = [...children, ...this.childNodes.filter((child) => !children.includes(child))];
  }
  cloneNode(deep) {
    const copy = new Element(this.tagName);
    copy.attributes = new Map(this.attributes);
    copy.dataset = { ...this.dataset };
    copy.className = this.className;
    if (deep) copy.append(...this.childNodes.map((child) => child.cloneNode ? child.cloneNode(true) : { textContent: child.textContent }));
    return copy;
  }
  closest(tag) { return this.tagName.toLowerCase() === tag ? this : this.parentElement?.closest(tag) || null; }
  querySelector(selector) {
    const tags = selector.split(',').map((part) => part.split('[')[0].toUpperCase());
    for (const child of this.childNodes) {
      if (tags.includes(child.tagName)) return child;
      const nested = child.querySelector?.(selector);
      if (nested) return nested;
    }
    return null;
  }
  // Descendants by the tag of the last simple selector ('.tag-list span' finds every SPAN).
  querySelectorAll(selector) {
    const tag = selector.trim().split(/\s+/).at(-1).split(/[.[]/)[0].toUpperCase();
    return this.childNodes.flatMap((child) => child.tagName ? [...(child.tagName === tag ? [child] : []), ...child.querySelectorAll(selector)] : []);
  }
  remove() { this.parentElement.childNodes = this.parentElement.childNodes.filter((node) => node !== this); }
  addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
  click() { (this.listeners.click || []).forEach((handler) => handler({ target: this })); }
}

// The outline uses the width beside the rail and retains its native details toggle.
let pageTree;
const outlineHeading = new Element('h1', 'Reader guide');
outlineHeading.id = 'reader-guide';
outlineHeading.getBoundingClientRect = () => ({ top: 0 });
const outlineSection = new Element('h2', 'Steps');
outlineSection.id = 'steps';
outlineSection.getBoundingClientRect = () => ({ top: 400 });
let outlineHeadings = [outlineHeading];
const outlineArticle = {
  parentElement: { clientWidth: 1000 },
  querySelector: () => null,
  querySelectorAll: () => outlineHeadings,
  before(nav) { nav.parentElement = this.parentElement; nav.remove = () => { pageTree = null; }; pageTree = nav; }
};
context.document.createElement = (tag) => new Element(tag);
context.document.querySelector = (selector) => ({ '.markdown-section': outlineArticle, '.page-tree': pageTree })[selector] || null;
context.getComputedStyle = () => ({ position: outlineArticle.parentElement.clientWidth >= 900 ? 'sticky' : 'static' });
context.location.hash = '#/content/guide';
context.buildPageTree();
assert.equal(pageTree, undefined, 'A page with only its title gets no outline.');
outlineHeadings = [outlineHeading, outlineSection];
for (const width of [700, 899, 900, 1320]) {
  outlineArticle.parentElement.clientWidth = width;
  context.buildPageTree();
  const details = pageTree.children[0];
  assert.equal(details.open, width >= 900, 'The outline opens only when the content area supports a side column.');
  assert.equal(details.children[0].tagName, 'SUMMARY');
  const link = details.children[1].children[0].children[0];
  assert.equal(link.href, '#/content/guide?id=reader-guide', 'Tree links use the reader route of the heading id.');
  assert.equal(link.getAttribute('aria-current'), 'location');
  details.open = !details.open;
  context.updatePageTreeCurrent();
  assert.equal(details.open, width < 900, 'Scroll tracking preserves the reader toggle.');
  details.open = true;
  link.closest = (selector) => selector === 'details' ? details : pageTree;
  await handlers.click({ target: { closest: (selector) => selector === '.page-tree a' ? link : null } });
  assert.equal(details.open, width >= 900, 'Following an outline link closes only the inline tree.');
}
const responsiveDetails = pageTree.children[0];
responsiveDetails.open = false;
outlineArticle.parentElement.clientWidth = 1294;
outlineResize();
assert.equal(responsiveDetails.open, false, 'A reader choice stays when a compact rail keeps the outline beside the article.');
outlineArticle.parentElement.clientWidth = 886;
outlineResize();
assert.equal(pageTree.dataset.layout, 'inline', 'Expanding the rail can move the outline above the article.');
assert.equal(responsiveDetails.open, false);
responsiveDetails.open = true;
outlineArticle.parentElement.clientWidth = 800;
outlineResize();
assert.equal(responsiveDetails.open, true, 'A reader choice stays through width changes within the inline layout.');
outlineArticle.parentElement.clientWidth = 1320;
outlineResize();
assert.equal(responsiveDetails.open, true, 'Returning to the side layout opens its default outline.');
outlineArticle.parentElement.clientWidth = 640;
outlineResize();
assert.equal(responsiveDetails.open, false, 'Resizing a wide article to mobile closes the inline outline.');
pageTree = null;
outlineResize();

// The actual legacy sidebar must produce populated groups through the reader parser.
const legacySidebar = legacySource.match(/\$sidebar = @'\r?\n([\s\S]*?)\r?\n'@/)[1];
const rail = new Element('div');
context.document.createElement = (tag) => new Element(tag);
context.document.querySelector = (selector) => selector === '.rail-nav' ? rail : null;
context.document.querySelectorAll = () => [];
context.fetch = async (url) => {
  assert.equal(url, '/_sidebar.md');
  return { ok: true, text: async () => legacySidebar };
};
await context.buildRail();
assert.equal(rail.children.length, 2);
assert.equal(rail.children.map((group) => group.children[0].textContent).join(','), 'Biblioteca,Participar');
const railLinks = rail.children.flatMap((group) => group.children[1].children.map((entry) => entry.children[0]));
assert.equal(railLinks.length, 7);
assert.ok(rail.children.every((group) => group.children[1].children.length));
assert.equal(railLinks.map((link) => link.href).join(','), '#/,#/guides,#/updates,#/tools,#/downloads,#/archive,#/content/contributing');

// Only the marked current article attachment becomes a viewer. Citations stay links.
context.location.hash = '#/content/guide';
let viewer;
let citationsReplaced = 0;
const pdfLink = (href, replaceWith) => ({
  getAttribute: () => href,
  closest: () => ({ replaceWith }),
  replaceWith
});
const externalPdf = pdfLink('https://example.test/reference.pdf', () => { citationsReplaced += 1; });
const crossArticlePdf = pdfLink('/pdf/other.pdf', () => { citationsReplaced += 1; });
const ownPdf = pdfLink('/pdf/guide.pdf', (value) => { viewer = value; });
context.document.querySelector = (selector) => selector === '.markdown-section .pdf-viewer' ? viewer : null;
context.document.querySelectorAll = (selector) => selector === '.markdown-section .article-pdf a[href]'
  ? [externalPdf, crossArticlePdf, ownPdf] : [];
context.buildPdfViewer();
assert.equal(citationsReplaced, 0);
assert.equal(viewer.className, 'pdf-viewer');
assert.equal(viewer.children[1].src, '/pdf/guide.pdf#zoom=page-width&pagemode=none&view=FitH&navpanes=0', 'The viewer opens at page width.');
assert.deepEqual(viewer.children[0].children.map((link) => [link.textContent, link.href, link.target, link.className]),
  [['Descargar PDF original', '/pdf/guide.pdf?download=1', undefined, 'download-link'], ['Abrir PDF original', '/pdf/guide.pdf', '_blank', 'pdf-link']],
  'Both actions name the original; Descargar PDF original is the gold primary, Abrir PDF original the secondary.');
const originalViewer = viewer;
context.buildPdfViewer();
assert.equal(viewer, originalViewer, 'Repeated sync keeps one viewer.');
viewer = null;
ownPdf.closest = () => null;
context.buildPdfViewer();
assert.equal(viewer.children[1].src.split('#')[0], '/pdf/guide.pdf', 'A link outside a paragraph cannot stop view sync.');
viewer = null;
context.document.querySelectorAll = () => [externalPdf, crossArticlePdf];
context.buildPdfViewer();
assert.equal(viewer, null, 'An article without its own attachment does not embed another PDF.');
// A PDF-only guide (no text besides its head) has no Copiar página; a guide with text keeps it.
for (const [text, expected] of [['', true], ['Texto de la guía', false]]) {
  let copyRemoved = false;
  const node = (head, content) => ({ matches: () => head, textContent: content });
  const article = { children: [node(true, 'Guía'), node(true, 'Copiar enlace'), node(false, text)],
    querySelector: (selector) => selector === '.article-actions button.copy-page:not(.copy-link)' ? { remove() { copyRemoved = true; } } : null };
  viewer = null;
  context.document.querySelectorAll = () => [ownPdf];
  context.document.querySelector = (selector) => ({ '.markdown-section .pdf-viewer': viewer, '.markdown-section': article })[selector] || null;
  context.buildPdfViewer();
  assert.equal(copyRemoved, expected, text ? 'A guide with text keeps Copiar página.' : 'A PDF-only guide has no Copiar página.');
}
context.document.querySelector = () => null;
context.document.querySelectorAll = () => [];
// Phone article actions (round 4 #1): each icon has a short visible word; round 5 #14: the word is hidden from the accessible
// name, which is the full label alone (it already contains the word, WCAG 2.5.3).
{
  const button = (tagName, classes, label, attributes = []) => {
    const nodes = [{ tagName: 'svg', textContent: '' }];
    const span = { tagName: 'SPAN', className: '', textContent: label, before: (node) => nodes.splice(nodes.indexOf(span), 0, node) };
    nodes.push(span);
    return { tagName, nodes, classList: { contains: (name) => classes.includes(name) }, hasAttribute: (name) => attributes.includes(name),
      querySelector: (selector) => ({ span, '.copy-page__short': nodes.find((node) => node.className === 'copy-page__short') || null })[selector] };
  };
  const actions = [['Copiar', button('BUTTON', ['copy-page'], 'Copiar página')], ['Enlace', button('BUTTON', ['copy-page', 'copy-link'], 'Copiar enlace')],
    ['PDF', button('A', ['copy-page'], 'Exportar PDF', ['download'])], ['Editar', button('A', ['copy-page'], 'Editar artículo')]];
  context.document.querySelectorAll = (selector) => selector === '.markdown-section .article-actions .copy-page' ? actions.map(([, item]) => item) : [];
  context.document.createElement = (tag) => ({ tagName: tag.toUpperCase(), attributes: {}, setAttribute(name, value) { this.attributes[name] = value; } });
  context.labelArticleActions?.();
  context.labelArticleActions?.();
  for (const [word, item] of actions) {
    const full = item.nodes.at(-1).textContent;
    const shorts = item.nodes.filter((node) => node.className === 'copy-page__short');
    assert.equal(shorts.length, 1, full + ': one short visible word, also after a repeated sync.');
    assert.equal(shorts[0].textContent, word);
    const name = item.nodes.filter((node) => node.attributes?.['aria-hidden'] !== 'true').map((node) => node.textContent).filter(Boolean).join(' ');
    assert.equal(name, full, full + ': the accessible name is the full label, with no repeated word.');
    assert.ok(full.toLowerCase().includes(word.toLowerCase()), full + ': the visible word is part of the name.');
  }
  const css = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
  assert.match(css, /^\.copy-page__short\{display:none\}/m, 'Wide readers show the full label only.');
  assert.match(css, /@container reader \(max-width:600px\)\{[^@]*\.article-actions \.copy-page__short\{display:inline\}/, 'A phone reader shows the short word.');
  assert.match(css, /@container reader \(max-width:600px\)\{[^@]*\.article-actions \.copy-page>span:not\(\.copy-page__short\)\{position:absolute/, 'A phone reader hides only the full label, which stays in the name.');
  context.document.querySelectorAll = () => [];
}

function table(headers, data) {
  const result = new Element('table');
  result.tHead = new Element('thead');
  const heading = new Element('tr');
  heading.append(...headers.map((label) => new Element('th', label)));
  result.tHead.append(heading);
  const body = new Element('tbody');
  data.forEach((values) => {
    const row = new Element('tr');
    row.append(...values.map((value) => new Element('td', value)));
    body.append(row);
  });
  result.tBodies = [body];
  result.append(result.tHead, body);
  new Element('article').append(result);
  return result;
}
const records = table(['Nombre', 'Permiso', 'Vence'], [
  ['Clave 10', 'Lectura', '01/02/2027'],
  ['álvaro', 'Administración', '15/12/2026'],
  ['Alvaro', 'Lectura', '15/12/2026'],
  ['Clave 2', 'Administración', '02/01/2027']
]);
const originalRows = [...records.tBodies[0].rows];
originalRows.forEach((row, index) => {
  row.cells[0].dataset.sortValue = row.cells[0].textContent;
  row.cells[0].append(new Element('p', index === 1 ? 'ZZ summary RPA' : 'AA summary Café'));
});
['2027-02-01T00:00:00-05:00', '2026-12-15T00:00:00-05:00', '2026-12-15T00:00:00-05:00', '2027-01-02T00:00:00-05:00']
  .forEach((value, index) => { originalRows[index].cells[2].dataset.sortValue = value; });
// Sorting must move the row and keep its links/forms intact.
const recordLink = new Element('a', 'Ver clave');
recordLink.setAttribute('href', '/api/docs/');
originalRows[0].cells[1].append(recordLink);
const recordForm = new Element('form');
originalRows[3].cells[1].append(recordForm);
const emptyTable = table(['Nombre'], []);
const merged = table(['Nombre'], [['Fila']]);
merged.tBodies[0].rows[0].cells[0].rowSpan = 2;
const multiheader = table(['Nombre'], [['Fila']]);
multiheader.tHead.append(new Element('tr'));
const interactive = table(['Nombre'], [['Fila']]);
interactive.tHead.rows[0].cells[0].append(new Element('a', 'Ayuda'));
const layout = table(['Nombre'], [['Fila']]);
layout.setAttribute('role', 'presentation');
const ragged = table(['Nombre', 'Estado'], [['Fila']]);
const footer = table(['Nombre'], [['2'], ['1'], ['4'], ['3']]);
footer.tFoot = new Element('tfoot');
const footerSummary = new Element('tr');
footerSummary.append(new Element('td', 'Total: 2'));
footer.tFoot.append(footerSummary);
footer.append(footer.tFoot);
const optOut = table(['Nombre'], [['Fila']]);
optOut.dataset.sortable = 'false';
const nested = table(['Nombre'], [['Fila']]);
nested.tBodies[0].rows[0].cells[0].append(table(['Interna'], [['Fila']]));
const nestedChild = nested.querySelector('table');
const noHeader = table(['Nombre'], [['Fila']]);
noHeader.tHead = null;
const skipped = [merged, multiheader, interactive, layout, ragged, optOut, nested, nestedChild, noHeader];
const offsetDates = table(['Fecha'], [['01/01/2027'], ['01/01/2027'], ['01/01/2028'], ['01/01/2029']]);
offsetDates.tBodies[0].rows[2].cells[0].dataset.sortValue = '2028-01-01';
offsetDates.tBodies[0].rows[3].cells[0].dataset.sortValue = '2029-01-01';
offsetDates.tBodies[0].rows[0].cells[0].dataset.sortValue = '2027-01-01T01:00:00-05:00';
const earlierTime = new Element('time', '01/01/2027');
earlierTime.setAttribute('datetime', '2027-01-01T03:00:00+02:00');
offsetDates.tBodies[0].rows[1].cells[0].append(earlierTime);
const earlierRow = offsetDates.tBodies[0].rows[1];
const proseTable = table(['Method', 'Path', 'Result'], [['GET', '/me/', 'The current account, its key, expiry date, and the full set of allowed API operations.']]);
// Only a table wider than its box is a tab stop; it takes the name of the heading before it.
const recordsHeading = new Element('h2', 'Claves de API');
recordsHeading.id = 'claves-de-api';
records.parentElement.prepend(recordsHeading);
Object.assign(records, { scrollWidth: 900, clientWidth: 600, scrollLeft: 0 });
Object.assign(merged, { scrollWidth: 500, clientWidth: 300, scrollLeft: 0 });
// Round 5 #30: a table of three rows or fewer gets no sort buttons (its column floors and header scope stay).
const shortTable = table(['Nombre', 'Descripción'], [['Clave', 'Una clave de lectura para el equipo de soporte'], ['Otra', 'b'], ['Más', 'c']]);
let tables = [records, emptyTable, footer, offsetDates, proseTable, shortTable, ...skipped];
context.document.querySelector = () => null;
context.document.querySelectorAll = (selector) => selector === '.markdown-section table' ? tables : [];
context.document.createElement = (tag) => new Element(tag);
context.buildTableSorting();
context.syncView();
context.buildTableSorting();
assert.deepEqual(records.tBodies[0].rows, originalRows, 'Initialization keeps the author order.');
const columns = records.tHead.rows[0].cells;
const buttons = columns.map((header) => header.querySelector('button'));
buttons.forEach((button, index) => {
  assert.equal(button.tagName, 'BUTTON');
  assert.equal(button.type, 'button', 'Header controls cannot submit a nearby form.');
  assert.equal(button.listeners.click.length, 1, 'Repeated sync must not duplicate handlers.');
  assert.equal(columns[index].getAttribute('aria-sort'), 'none');
  assert.equal(columns[index].childNodes.length, 1, 'Repeated sync must not nest controls.');
});
assert.ok(skipped.every((item) => !item.dataset.sortReady), 'Structural and interactive tables stay intact.');
assert.ok([shortTable, emptyTable, proseTable].every((item) => item.tHead.rows[0].cells.every((cell) => !cell.querySelector('button') && cell.getAttribute('aria-sort') === null)),
  'Three rows or fewer: nothing to sort.');
assert.deepEqual(shortTable.tHead.rows[0].cells.map((cell) => cell.getAttribute('scope')), ['col', 'col']);
assert.equal(shortTable.tBodies[0].rows[0].cells[1].dataset.width, 'long', 'A short table keeps its column floors.');
assert.equal(records.tabIndex, 0, 'A table that scrolls in its own box takes keyboard focus.');
assert.equal(records.getAttribute('aria-labelledby'), 'claves-de-api', 'The scroll region is named by the heading before it.');
assert.equal(records.getAttribute('aria-label'), null);
// The right-edge cue is a scroll-shadow background, so no mask clips the focus ring or fades the last column.
const readerCss = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
// Phone tag targets (round 4 #7): at least 24 px tall (WCAG 2.5.8) and no overlap with the chip row above.
{
  const rule = readerCss.match(/@media\(pointer:coarse\)\{\.article-meta>\.article-meta__tags\{row-gap:var\(--space-1\)\}\.article-meta__tags a\{min-height:0;padding-block:(\d+)px;margin-block:-(\d+)px\}\}/);
  assert.ok(rule, 'Touch tag links pad their target with an equal negative margin, in rows 8 px (--space-1) apart.');
  const [padding, margin] = [Number(rule[1]), Number(rule[2])];
  const chip = 10 * 1.3 + 2 * 2 + 2; // --chip-size 10px at line-height 1.3, 2 px padding, 1 px border
  assert.equal(padding, margin, 'The negative margin keeps the chip rows where they are.');
  assert.ok(chip + 2 * padding >= 24, 'A tag target is at least 24 px tall: ' + (chip + 2 * padding) + ' px.');
  assert.ok(2 * padding <= 8, 'Tag targets of two rows do not overlap: ' + 2 * padding + ' px of padding in an 8 px gap.');
}
// The article action row starts at the h1 edge on every article type (round 4 #4).
assert.match(readerCss, /^\.article-actions\{display:flex;flex-wrap:wrap;justify-content:flex-start;/m);
// The sort button holds its absolute visually hidden name parts, so they stay in the table scroll box (round 5 check: page overflow).
assert.match(readerCss, /^\.markdown-section \.table-sort\{position:relative;/m);
assert.doesNotMatch(readerCss, /article-actions\{[^}]*flex-end/);
// Round 4 #3: list rows use the article meta voice: mono 13 px, tabular figures, the same " · " separators.
assert.match(readerCss, /\.markdown-section \.item-meta\{display:flex;flex-wrap:wrap;align-items:baseline;[^}]*font:13px\/1\.5 var\(--font-mono\);font-variant-numeric:tabular-nums/);
assert.match(readerCss, /:is\(\.article-meta,\.search-result__meta,\.item-meta\)>\*::before\{content:'·'/);
// Round 4 #31: Herramientas card titles in the Inter row voice; underline on hover and focus only.
assert.match(readerCss, /\.markdown-section \.library-card h2\{margin:0;font:650 18px\/24px var\(--font-ui\)\}/);
assert.match(readerCss, /\.markdown-section :is\(\.timeline-card,\.library-card\) :is\(h2,h3\) a\{color:var\(--text\);text-decoration:none\}/);
// Round 4 #37: no results offer the rail sections in rail order and, under a type, the same words in all of Athena.
{
  const createElement = context.document.createElement;
  const querySelector = context.document.querySelector;
  context.document.createElement = (tag) => new Element(tag);
  context.document.querySelector = (selector) => (selector === '.rail-nav a[href="#/downloads"]' ? {} : null);
  const links = (state) => state.children.at(-1).children.map((link) => [link.textContent, link.href]);
  assert.deepEqual(links(context.noResultsState('zzz', '')), [['Guías', '#/guides'], ['Actualizaciones', '#/updates'], ['Herramientas', '#/tools'], ['Descargas', '#/downloads']]);
  assert.deepEqual(links(context.noResultsState('zzz', 'pdf'))[0], ['Buscar en todo Athena', '#/search?q=zzz'], 'A type filter can be cleared in one step.');
  context.document.querySelector = () => null;
  assert.ok(!links(context.noResultsState('zzz', '')).some(([, href]) => href === '#/downloads'), 'Descargas only where the rail offers it.');
  Object.assign(context.document, { createElement, querySelector });
  assert.match(readerCss, /\.markdown-section :is\(\.post-summary,\.library-card>p:not\(\[class\]\)\)\{max-width:70ch[;}]/);
}
// Round 4 #38: a code copy button names its language ("Copiar código python"); the visible word stays first.
{
  const createElement = context.document.createElement;
  const querySelectorAll = context.document.querySelectorAll;
  context.document.createElement = (tag) => new Element(tag);
  const pre = new Element('pre');
  pre.dataset.lang = 'python';
  pre.before = () => {};
  const plain = new Element('pre');
  plain.before = () => {};
  context.document.querySelectorAll = (selector) => (selector === '.markdown-section pre:not(.code-block > pre)' ? [pre, plain] : []);
  context.buildCodeCopy();
  const names = [pre, plain].map((block) => block.parentElement.children[0].children.at(-1).getAttribute('aria-label'));
  assert.deepEqual(names, ['Copiar código python', 'Copiar código']);
  Object.assign(context.document, { createElement, querySelectorAll });
}
// Round 4 #38: file sizes follow the interface number format (the server writes the bytes in <data value>).
{
  const sizes = [426, 9011, 1153434].map((value) => ({ value: String(value), textContent: '' }));
  const querySelectorAll = context.document.querySelectorAll;
  context.document.querySelectorAll = (selector) => (selector === '.markdown-section data.file-size' ? sizes : []);
  context.document.documentElement.lang = 'en';
  context.formatFileSizes();
  assert.deepEqual(sizes.map((size) => size.textContent), ['426 bytes', '8.8 KB', '1.1 MB']);
  context.document.documentElement.lang = 'es';
  context.formatFileSizes();
  assert.deepEqual(sizes.map((size) => size.textContent), ['426 bytes', '8,8 KB', '1,1 MB']);
  delete context.document.documentElement.lang;
  context.document.querySelectorAll = querySelectorAll;
}
// Round 4 #40: on a wide reader the actions are the first child of the article, before the h1, so Tab follows the drawn order.
{
  const heading = { tagName: 'H1', parentElement: null };
  const meta = { matches: (selector) => selector.includes('.article-meta') };
  heading.nextElementSibling = meta;
  const actions = {};
  const article = { firstElementChild: heading, querySelector: (selector) => ({ h1: heading, ':scope > .article-actions': actions })[selector] || null,
    prepend(node) { this.firstElementChild = node; } };
  heading.parentElement = article;
  const main = { clientWidth: 1200 };
  const querySelector = context.document.querySelector;
  context.document.querySelector = (selector) => ({ '.markdown-section': article, 'div#main': main })[selector] || null;
  const getComputedStyle = context.getComputedStyle;
  context.getComputedStyle = () => ({ paddingLeft: '0px', getPropertyValue: () => '' });
  context.placeArticleHead();
  assert.equal(article.firstElementChild, actions, 'Wide reader: the actions come before the h1 in the DOM.');
  let after;
  meta.after = (node) => { after = node; };
  meta.nextElementSibling = null;
  main.clientWidth = 600;
  context.placeArticleHead();
  assert.equal(after, actions, 'Narrow reader: the actions follow the title and meta line, where they are drawn.');
  Object.assign(context, { getComputedStyle });
  context.document.querySelector = querySelector;
}
// Advisor review: the Guías page lists only guides, so its rows drop the kind; the line starts with the author.
// Home rows and Herramientas cards keep it.
assert.match(readerCss, /\.guide-library \.item-meta__kind\{display:none\}/);
assert.doesNotMatch(readerCss, /(^|[},])\s*\.item-meta__kind\{display:none\}/);

// Round 4 #29, round 5 #10 (contract 1): short inline code stays on one line; a value over 24 characters may wrap anywhere,
// as in the PDF export, so it fits a 320 px reader. The inline box is tight, with no gap before punctuation.
{
  const codes = ['run-tests', 'x'.repeat(25), 'y'.repeat(24)].map((text) => ({ textContent: text, classes: new Set(),
    classList: { toggle(name, on) { on ? codes.find((code) => code.classList === this).classes.add(name) : codes.find((code) => code.classList === this).classes.delete(name); } } }));
  const querySelectorAll = context.document.querySelectorAll;
  context.document.querySelectorAll = (selector) => (selector === '.markdown-section :not(pre) > code' ? codes : []);
  context.markLongCode?.();
  assert.deepEqual(codes.map((code) => code.classes.has('long')), [false, true, false], 'Only inline code over 24 characters is long.');
  context.document.querySelectorAll = querySelectorAll;
  assert.match(readerCss, /\.markdown-section :not\(pre\)>code\{white-space:nowrap\}\.markdown-section :not\(pre\)>code\.long\{white-space:normal;overflow-wrap:anywhere\}/);
  assert.match(readerCss, /\n\.markdown-section code\{margin:0;padding:1px 3px;/, 'A tight inline code box.');
}
// Round 4 #30: a Markdown figure is a button that opens the image viewer with its caption.
// Round 5 #15: its name comes from parts (the interface words in the interface language, then the Spanish alt of the image);
// #16: an image alone in its paragraph and the caption line under it become one figure with a figcaption.
{
  const src = context.location.origin + '/article-images/0b0e5f3a-1111-4222-8333-944455556666/';
  const em = { tagName: 'EM', textContent: 'Figura 1. Flujo de un proceso.' };
  const caption = { matches: (selector) => selector === 'p', children: [em], firstElementChild: em, textContent: ' Figura 1. Flujo de un proceso. ',
    remove() { this.removed = true; } };
  const img = { alt: 'Flujo de cinco pasos', getAttribute: (name) => (name === 'src' ? src : null), replaceWith(node) { this.replacedBy = node; } };
  const paragraph = { children: [img], textContent: '', nextElementSibling: caption, replaceWith(node) { this.replacedBy = node; } };
  img.parentElement = paragraph;
  const created = [];
  const createElement = context.document.createElement;
  context.document.createElement = (tag) => {
    const node = { tagName: tag.toUpperCase(), attributes: {}, listeners: {}, children: [], setAttribute(name, value) { this.attributes[name] = value; },
      append(...nodes) { this.children.push(...nodes); }, addEventListener(name, handler) { this.listeners[name] = handler; } };
    created.push(node);
    return node;
  };
  const querySelectorAll = context.document.querySelectorAll;
  context.document.querySelectorAll = (selector) => (selector === '.markdown-section p > img[src*="/article-images/"]' ? [img] : []);
  const opened = [];
  const openViewer = context.openViewer;
  context.openViewer = (...args) => opened.push(args);
  context.buildFigureZoom?.();
  const button = img.replacedBy;
  assert.ok(button && button.tagName === 'BUTTON' && button.type === 'button' && button.className === 'figure-zoom' && button.children[1] === img,
    'The image sits in a button in its place.');
  const [name] = button.children;
  assert.deepEqual([button.attributes['aria-label'], name.className, name.lang, name.textContent], [undefined, 'visually-hidden', 'es', 'Ampliar imagen: '],
    'No aria-label: the name is a hidden part in the interface language, then the image alt.');
  const figure = paragraph.replacedBy;
  assert.ok(figure?.tagName === 'FIGURE' && figure.children[0] === button && figure.children[1]?.tagName === 'FIGCAPTION', 'One figure holds the image and its caption.');
  assert.ok(figure.children[1].children[0] === em && caption.removed, 'The caption line moves into the figcaption.');
  button.listeners.click();
  assert.equal(opened.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(opened[0].slice(1))), [[{ src: '/article-images/0b0e5f3a-1111-4222-8333-944455556666/', caption: 'Figura 1. Flujo de un proceso.', alt: 'Flujo de cinco pasos' }], 0],
    'One item: the managed image path, the caption line and the alt text.');
  assert.equal(opened[0][0], button, 'Closing the viewer returns the focus to the figure button.');
  context.document.documentElement.lang = 'en';
  context.setZoomName(name, img.alt);
  assert.deepEqual([name.lang, name.textContent], ['en', vm.runInContext("t('Ampliar imagen')", context) + ': '], 'A language change relabels the interface part only.');
  delete context.document.documentElement.lang;
  // An image with text beside it, or with no caption line, stays where it is.
  const lone = { alt: '', getAttribute: (key) => (key === 'src' ? src : null), replaceWith(node) { this.replacedBy = node; } };
  const plain = { children: [lone], textContent: '', nextElementSibling: null, replaceWith(node) { this.replacedBy = node; } };
  lone.parentElement = plain;
  context.document.querySelectorAll = (selector) => (selector === '.markdown-section p > img[src*="/article-images/"]' ? [lone] : []);
  context.buildFigureZoom();
  assert.ok(lone.replacedBy && !plain.replacedBy, 'No caption: no figure.');
  assert.equal(lone.replacedBy.children[0].textContent, 'Ampliar imagen', 'No alt: no colon.');
  Object.assign(context, { openViewer });
  context.document.createElement = createElement;
  context.document.querySelectorAll = querySelectorAll;
  assert.match(readerCss, /\.markdown-section figure\{margin:1\.2em 0\}/);
  assert.match(readerCss, /\.figure-zoom\{[^}]*cursor:zoom-in/);
}
// The active Guías topic has a shape cue, not only gold text (round 4 #23): the editor tabs' 2 px accent bottom rule.
assert.match(readerCss, /\.guide-topic-jumps a\[aria-current\]\{box-shadow:inset 0 -2px 0 var\(--accent\)/);
assert.doesNotMatch(readerCss, /mask-image/, 'No reader table is masked.');
// Round 5 #12: the signed-in chip states a fact ("Sesión iniciada"), in the quiet label colour, not gold like a link.
{
  const indexHtml = readFileSync(new URL('../src/index.html', import.meta.url), 'utf8');
  assert.match(indexHtml, /<span class="access-label">\{% if user\.is_authenticated %\}Sesión iniciada\{% else %\}Biblioteca pública\{% endif %\}<\/span>/);
  assert.match(readerCss, /\.access-label\{[^}]*color:var\(--text-muted\)/);
}
// Round 5 #24: every list summary (Guías and home rows, Actualizaciones, Herramientas cards) uses one muted token;
// the olive row colour, which read as a second gold in dark, is gone.
assert.doesNotMatch(readerCss, /--guide-muted/);
assert.match(readerCss, /\.markdown-section \.guide-summary\{[^}]*color:var\(--text-muted\)/);
assert.match(readerCss, /\.markdown-section :is\(\.post-summary,\.library-card>p:not\(\[class\]\)\)\{max-width:70ch;color:var\(--text-muted\)\}/);
// Round 5 #9: Herramientas and Actualizaciones count their items; "resultados" only while the filter has text.
{
  const querySelector = context.document.querySelector;
  const card = (text) => ({ dataset: { search: text }, closest: () => null, hidden: false });
  const input = { value: '' };
  for (const [updates, single, plural] of [[false, 'herramienta', 'herramientas'], [true, 'actualización', 'actualizaciones']]) {
    const count = { textContent: '' };
    const empty = { hidden: true, querySelector: () => null };
    const cards = [card('Cola de facturas'), card('Monitor de bots')];
    const list = { matches: (selector) => updates && selector === '.timeline', nextElementSibling: empty,
      querySelectorAll: (selector) => (selector === '.library-card' ? cards : []) };
    context.document.querySelector = (selector) => ({ '.markdown-section .library-grid, .markdown-section .timeline': list, '#library-count': count, '#athena-search-input': input })[selector] || null;
    vm.runInContext(`searchScope = '${updates ? 'update' : 'tool'}'`, context);
    input.value = '';
    context.filterLibrary();
    assert.equal(count.textContent, '2 ' + plural);
    cards.pop();
    context.filterLibrary();
    assert.equal(count.textContent, '1 ' + single);
    input.value = 'facturas';
    context.filterLibrary();
    assert.equal(count.textContent, '1 resultado');
  }
  input.value = '';
  vm.runInContext("searchScope = ''", context);
  context.document.querySelector = querySelector;
}
// Round 5 #13: at 360 px and below the article h1 is 28/34; nothing else in the phone head changes.
assert.match(readerCss, /@container reader \(max-width:360px\)\{body\.article-view \.markdown-section h1\{font-size:28px;line-height:34px\}\}/);
// Round 5 #7 (regression of round 4 #22): the right-edge cue is the round 4 width (a 48 px cover, opaque over its right half,
// so a table that does not scroll shows no cue, #30) with a stronger 24 px shadow; table headers are 12 px.
{
  const table = readerCss.match(/\.markdown-section table\{[^}]*\}/)[0];
  assert.match(table, /linear-gradient\(to left,var\(--surface\) 50%,transparent\) right\/48px 100% no-repeat/, 'The cover hides the whole shadow at the end and on a table that fits.');
  assert.match(table, /linear-gradient\(to left,color-mix\(in oklab,var\(--text\) 24%,transparent\),transparent\) right\/24px 100% no-repeat/, 'A visible 24 px shadow.');
  assert.match(readerCss, /\.markdown-section th\{[^}]*font:600 12px\/1\.4 var\(--font-mono\)/, 'Table headers are 12 px.');
}
assert.match(readerCss, /\.markdown-section table\{[^}]*background-attachment:local,scroll/, 'The cue moves off at the end of the scroll.');
records.clientWidth = 900;
context.syncTableScroll(records);
assert.equal(records.tabIndex, undefined, 'A table that fits again is no tab stop.');
assert.equal(records.listeners.scroll, undefined, 'The cue needs no scroll listener.');
assert.equal(merged.tabIndex, 0, 'Tables that cannot sort still scroll by keyboard.');
assert.ok([emptyTable, footer, proseTable].every((item) => item.tabIndex === undefined), 'Tables that fit take no focus.');
assert.ok(layout.tabIndex === undefined && nestedChild.tabIndex === undefined, 'Layout and nested tables take no focus.');
assert.deepEqual(proseTable.tBodies[0].rows[0].cells.map((cell) => cell.dataset.width), [undefined, undefined, 'long'],
  'A long-text column gets the wide floor; short columns keep their natural width.');
assert.deepEqual(records.tBodies[0].rows.map((row) => row.cells[2].dataset.width), [undefined, undefined, undefined, undefined]);
assert.ok(records.tBodies[0].rows.every((row) => row.cells[0].dataset.width === 'text'), 'A medium text column gets the text floor.');
const order = () => records.tBodies[0].rows.map((row) => originalRows.indexOf(row)).join(',');
context.document.activeElement = buttons[0];
buttons[0].click();
assert.equal(order(), '1,2,3,0', 'Explicit names ignore other cell metadata and use Spanish, accent-insensitive and numeric-aware comparison.');
assert.equal(columns[0].getAttribute('aria-sort'), 'ascending');
// Round 4 #38: the sort name is built from its parts: the interface words in the interface language, the column name in Spanish.
const sortName = (button) => button.children.filter((node) => node.getAttribute?.('aria-hidden') !== 'true').map((node) => node.textContent).join('');
assert.equal(buttons[0].getAttribute('aria-label'), null, 'No aria-label that mixes two languages.');
assert.equal(sortName(buttons[0]), 'Ordenar ' + buttons[0].children[1].textContent + ' en orden descendente');
context.document.documentElement.lang = 'en';
context.setSortName(buttons[0], false);
assert.deepEqual(buttons[0].children.slice(0, 3).map((node) => node.lang), ['en', 'es', 'en']);
delete context.document.documentElement.lang;
context.setSortName(buttons[0], true);
assert.equal(context.document.activeElement, buttons[0], 'Moving body rows preserves header focus.');
context.syncView();
buttons[0].click();
assert.equal(order(), '0,3,1,2', 'Descending preserves the original order of equal values.');
assert.equal(columns[0].getAttribute('aria-sort'), 'descending');
buttons[1].click();
assert.equal(order(), '1,3,2,0');
assert.equal(columns[0].getAttribute('aria-sort'), 'none');
assert.equal(columns[1].getAttribute('aria-sort'), 'ascending');
buttons[1].click();
assert.equal(order(), '0,2,1,3');
buttons[2].click();
assert.equal(order(), '1,2,3,0', 'Machine date values sort chronologically across months and years.');
buttons[2].click();
assert.equal(order(), '0,3,1,2');
assert.equal(originalRows[0].cells[1].querySelector('a'), recordLink);
assert.equal(originalRows[3].cells[1].querySelector('form'), recordForm);
assert.equal(recordLink.getAttribute('href'), '/api/docs/');
footer.tHead.rows[0].cells[0].querySelector('button').click();
assert.equal(footer.tBodies[0].rows[0].textContent, '1');
assert.equal(footer.tFoot.rows[0], footerSummary, 'Sorting only moves tbody rows and keeps the footer fixed.');
const dateButton = offsetDates.tHead.rows[0].cells[0].querySelector('button');
dateButton.click();
assert.equal(offsetDates.tBodies[0].rows[0], earlierRow, 'ISO machine dates compare their time values across offsets.');
dateButton.click();
assert.equal(offsetDates.tBodies[0].rows.at(-1), earlierRow);
tables = [table(['New render'], [['2'], ['1'], ['4'], ['3']])];
context.syncView();
tables[0].tHead.rows[0].cells[0].querySelector('button').click();
assert.equal(tables[0].tBodies[0].rows[0].textContent, '1', 'A new Docsify render initializes independently.');

// The article meta line comes from the reader's own index record of the current route.
{
  const title = new Element('h1', 'Guide');
  const section = new Element('div');
  section.append(title);
  section.querySelectorAll = (selector) => selector === '.article-meta' ? section.children.filter((node) => node.className === 'article-meta') : [];
  context.document.createElement = (tag) => Object.assign(new Element(tag), { remove() { section.childNodes = section.childNodes.filter((node) => node !== this); } });
  title.after = (node) => section.childNodes.splice(section.childNodes.indexOf(title) + 1, 0, node);
  title.isConnected = true;
  context.location.hash = '#/content/guide';
  context.document.querySelector = (selector) => selector === '.markdown-section h1' ? title : null;
  context.fetch = async (url) => ({ ok: url === '/search-index.json', json: async () => [
    { route: '#/content/other', kind: 'tool', title: 'Other', author: 'X', date: '2026-01-01', tags: [] },
    { route: '#/content/guide', kind: 'guide', title: 'Guide', author: 'Ana Pérez', date: '2026-11-15', tags: ['primeros-pasos', 'RPA', 'Colas'] },
    { route: '#/content/tool', kind: 'tool', title: 'Tool', author: 'X', date: '2026-01-01', tags: ['Colas'] }
  ] });
  vm.runInContext('searchIndexPromise = undefined', context);
  await context.buildArticleMeta();
  await context.buildArticleMeta();
  const metas = section.children.filter((node) => node.className === 'article-meta');
  assert.equal(metas.length, 1, 'Repeated syncs keep one meta line.');
  assert.equal(section.children[1], metas[0], 'The meta line follows the article title.');
  // Separators are drawn by CSS, so a wrapped line never starts or ends with one.
  assert.ok(metas[0].childNodes.every((node) => node.tagName), 'The meta line holds items only, no separator text.');
  const [kind, author, updated, tagLinks] = metas[0].children;
  assert.equal(kind.textContent, 'Guía');
  assert.equal(author.textContent, 'Ana Pérez');
  assert.equal(author.lang, 'es');
  const [label, , date] = updated.children;
  assert.equal(label.textContent, 'Actualizado');
  assert.equal(date.dateTime, '2026-11-15');
  // A guide's tag links always open Guías filtered to that tag, also when no guide lists it first (Colas).
  assert.deepEqual(tagLinks.children.map((link) => link.href), ['#/guides?id=guide-topic-rpa', '#/guides?id=guide-topic-colas']);
  assert.deepEqual(tagLinks.children.map((link) => link.children[0].textContent), ['RPA', 'Colas'], 'Each tag link holds its chip; the placement tag is none.');
  context.location.hash = '#/content/tool';
  section.childNodes = [title];
  await context.buildArticleMeta();
  assert.deepEqual(section.children[1].children.at(-1).children.map((link) => link.href), ['#/search?q=Colas'], 'Other kinds keep the search link.');
  // Search results use the same meta order as the article head.
  context.document.createTextNode = (text) => ({ textContent: text });
  const result = context.createSearchResult(context.prepareSearchEntry({ route: '#/content/guide', kind: 'guide', title: 'Guide', summary: 'S',
    author: 'Ana Pérez', date: '2026-11-15', tags: [], text: '', prose: '', headings: [] }), ['guide']);
  const resultMeta = result.children.find((node) => node.className === 'search-result__meta');
  assert.deepEqual(resultMeta.children.map((node) => node.textContent), ['Guía', 'Ana Pérez', 'Actualizado ' + vm.runInContext("formatDate('2026-11-15')", context)]);
  context.location.hash = '#/content/draft';
  section.childNodes = [title];
  await context.buildArticleMeta();
  assert.equal(section.children.length, 1, 'An article missing from the index (a draft) gets no meta line.');
  context.document.querySelector = () => null;
  vm.runInContext('searchIndexPromise = undefined', context);
}

if (process.argv.includes('--reader-integration')) {
  const directoryInput = { value: '', addEventListener(name, handler) { this[name] = handler; } };
  const directoryRows = [{ dataset: { search: 'álvaro María' } }, { dataset: { search: 'beta' } }];
  const directoryEmpty = {};
  const directoryLinks = ['username', 'role', 'status', 'session'].map((sort) => ({ href: '?user=7&sort=' + sort + '&direction=desc&q=old' }));
  vm.runInNewContext(readFileSync(new URL('../server/athena/static/athena/admin-directory.js', import.meta.url), 'utf8'), {
    URL,
    location: { href: 'https://athena.example/admin/auth/user/?user=7' },
    document: {
      getElementById: () => directoryInput,
      querySelector: () => directoryEmpty,
      querySelectorAll: (selector) => selector === '.directory-sort' ? directoryLinks : directoryRows
    }
  });
  directoryInput.value = ' ALVARO ';
  directoryInput.input();
  assert.deepEqual(directoryRows.map((row) => row.hidden), [false, true]);
  assert.equal(directoryEmpty.hidden, true);
  directoryLinks.forEach((link) => {
    const params = new URL(link.href, 'https://athena.example').searchParams;
    assert.equal(params.get('q'), 'ALVARO');
    assert.equal(params.get('user'), '7');
    assert.equal(params.get('direction'), 'desc');
  });
  directoryInput.value = 'no match';
  directoryInput.input();
  assert.equal(directoryEmpty.hidden, false);
  directoryInput.value = '';
  directoryInput.input();
  assert.deepEqual(directoryRows.map((row) => row.hidden), [false, false]);
  assert.ok(directoryLinks.every((link) => !new URL(link.href, 'https://athena.example').searchParams.has('q')));
}

// Topic copies are made once from hidden server rows and never increase the result count.
function guidePage(entries, legacy = false) {
  const grid = new Element('div');
  const source = new Element('div');
  source.hidden = true;
  const topics = new Element('div');
  topics.hidden = false;
  const count = new Element('p');
  const empty = new Element('p');
  const query = { value: '', matches: (selector) => selector === '#athena-search-input' };
  const tag = { value: '', matches: (selector) => selector === '#guide-tag' };
  const rows = entries.map((entry, i) => {
    const row = new Element('article');
    row.className = legacy ? 'library-card' : 'guide-row';
    row.dataset.search = [entry.title, entry.author, entry.summary, ...entry.tags].join(' ');
    const detail = new Element('div');
    detail.className = 'guide-detail';
    const link = new Element('a', entry.title);
    link.setAttribute('href', '#/content/guide-' + i);
    const summary = new Element('p', entry.summary);
    const tags = entry.tags.map((value) => new Element('span', value));
    const tagList = new Element('p');
    tagList.append(...tags);
    const pdf = new Element('a', 'Abrir PDF original');
    pdf.setAttribute('href', '/pdf/guide-' + i + '.pdf');
    const site = new Element('a', 'Sitio oficial');
    site.setAttribute('href', 'https://example.test/guide-' + i);
    const download = new Element('a', 'Descarga aprobada');
    download.setAttribute('href', '#/downloads');
    const status = new Element('p', 'Estable');
    detail.append(link, summary, tagList, status, pdf, site, download);
    // The server meta line (contract 1): kind, author, Actualizado <date>.
    const meta = new Element('p');
    meta.className = 'item-meta';
    const kind = new Element('span', 'Guía');
    kind.className = 'item-meta__kind';
    const author = new Element('span', entry.author);
    author.className = 'item-meta__author guide-author';
    const date = new Element('span');
    date.className = 'item-meta__date';
    const time = new Element('time', entry.date);
    time.setAttribute('datetime', entry.date);
    date.append('Actualizado ', time);
    meta.append(kind, author, date);
    row.append(detail, meta);
    const queryRow = row.querySelector.bind(row);
    row.querySelector = (selector) => ({ '.guide-detail': detail, '.item-meta': meta })[selector] || queryRow(selector);
    row.querySelectorAll = (selector) => selector === '.tag-list span' ? tags : [];
    return row;
  });
  if (legacy) grid.append(...rows);
  else {
    source.append(...rows);
    grid.append(source, topics);
  }
  grid.querySelectorAll = () => rows;
  grid.querySelector = (selector) => legacy ? null : ({ '#guide-source': source, '#guide-topics': topics })[selector] || null;
  return { grid, source, topics, rows, count, empty, query, tag };
}
let guides;
delete context.localStorage;
context.location.hash = '#/guides';
context.document.querySelector = (selector) => ({
  '.guide-library': guides?.grid, '#athena-search-input': guides?.query,
  '#guide-count': guides?.count, '.library-empty': guides?.empty
})[selector] || null;
context.document.querySelectorAll = () => [];
const entries = [
  { title: 'Álvaro', author: 'Jeiser Vargas', summary: 'ZZ solución de problemas', date: '2026-01-02', tags: ['Primeros-Pasos', 'RPA', 'Café', 'CAFE', 'A|B <tema> "x"', 'Helios', 'Seguridad'] },
  { title: 'Alvaro', author: 'Other author', summary: 'AA resumen', date: '2026-10-13', tags: ['café', 'RPA avanzado'] },
  { title: 'Sin tema', author: 'Another author', summary: 'Sin etiquetas', date: '2025-01-01', tags: [] },
  { title: 'Tema vacío', author: 'Another author', summary: 'Sin etiquetas útiles', date: '2026-01-03', tags: ['  '] }
];
guides = guidePage(entries);
vm.runInContext("searchScope = 'guide'", context);
context.syncView();
// Round 5 #9: with no filter the count names the page's items; "resultados" only while a filter (text or topic) is on.
assert.equal(guides.count.textContent, '4 guías', 'Multi-tag guides count once.');
assert.equal(guides.source.hidden, true, 'Source records stay hidden while filters update them.');
assert.equal(guides.topics.hidden, false, 'Topics are the only view, with no storage available.');
assert.equal('view' in context.prepareGuideLibrary(guides.grid), false, 'The library no longer holds a view choice.');
const topicSections = guides.topics.children.slice(1);
const groupFor = (label) => topicSections.find((section) => section.children[0].textContent === label);
const rowsOf = (section) => section.children.filter((node) => node.className === 'guide-topic-row');
const shownSections = () => topicSections.filter((section) => !section.hidden);
assert.deepEqual(shownSections().map((section) => section.children[0].textContent), ['café', 'RPA', 'Sin etiqueta'],
  'One shown section per first topic tag, alphabetical with Spanish rules, Sin etiqueta last; the placement tag is no topic.');
assert.deepEqual(shownSections().map((section) => rowsOf(section).filter((row) => !row.hidden).length), [1, 1, 2],
  'Each guide is listed once, so the sections add up to the result count.');
assert.deepEqual(shownSections().map((section) => section.children[0].id), ['guide-topic-cafe', 'guide-topic-rpa', 'guide-untagged'],
  'Section ids come from the tag, so article tag links can name them.');
assert.equal(vm.runInContext("guideTopicId(normalize('Plantilla  Básica'))", context), 'guide-topic-plantilla-basica');
// Round 4 #5: the topic counts are guides with the tag; a section that lists fewer ends with one link to the topic filter.
const checkTopicCounts = (why) => shownSections().forEach((section) => {
  const label = section.children[0].textContent;
  const jump = guides.topics.children[0].children[1].children.find((item) => item.href === '#/guides?id=' + section.children[0].id);
  const count = jump.children.at(-1).textContent;
  const rows = String(rowsOf(section).filter((row) => !row.hidden).length);
  const more = section.children.find((node) => node.className === 'guide-topic-more');
  if (rows === count) assert.ok(!more || more.hidden, why + ': ' + label + ' lists all its ' + count + ' guides, so it has no link.');
  else {
    assert.ok(more && !more.hidden && section.children.at(-1) === more, why + ': ' + label + ' lists ' + rows + ' of its ' + count + ' guides and ends with the link.');
    assert.equal(more.children[0].textContent, 'Ver las ' + count + ' guías de ' + label);
    assert.equal(more.children[0].href, jump.href, 'The link opens the topic filter, as the topic row does.');
  }
});
checkTopicCounts('Unfiltered');
assert.ok(groupFor('café').children.at(-1).children[0].textContent === 'Ver las 2 guías de café', 'café lists 1 of its 2 guides.');
const copiedDetail = groupFor('RPA').children[1].children[0];
const copiedTags = copiedDetail.querySelectorAll('.tag-list span').map((tag) => tag.textContent);
assert.deepEqual(copiedTags, ['Café', 'CAFE', 'A|B <tema> "x"', 'Helios', 'Seguridad'],
  'Other tags stay chips as literal text; the placement tag and the chip that repeats the section topic (round 4 #3) are no chips.');
assert.deepEqual(groupFor('café').children.filter((node) => node.className === 'guide-topic-row')
  .map((row) => row.children[0].querySelectorAll('.tag-list span').map((tag) => tag.textContent)), [['RPA', 'A|B <tema> "x"', 'Helios', 'Seguridad'], ['RPA avanzado']],
  'Under café no row repeats the café chip, in any spelling.');
assert.equal(guides.rows[0].querySelectorAll('.tag-list span').length, 7, 'The hidden source record keeps every tag.');
assert.deepEqual(copiedDetail.children.filter((child) => child.tagName === 'A').map((link) => link.getAttribute('href')),
  ['#/content/guide-0', '/pdf/guide-0.pdf', 'https://example.test/guide-0', '#/downloads'], 'Topic copies keep every rendered conditional action.');
assert.match(copiedDetail.textContent, /Estable/);
assert.notEqual(copiedDetail, guides.rows[0].children[0], 'Topic details are copies of the source record.');
// Round 4 #3: a topic row copies the server meta line (kind · author · Actualizado <date>) instead of building its own.
const copiedMeta = groupFor('RPA').children[1].children[1];
assert.equal(copiedMeta.className, 'item-meta', 'A topic row carries the item-meta line.');
assert.notEqual(copiedMeta, guides.rows[0].children[1], 'The meta line is a copy of the source record.');
assert.deepEqual(copiedMeta.children.map((node) => node.textContent), ['Guía', entries[0].author, 'Actualizado ' + entries[0].date]);
assert.equal(copiedMeta.children[2].children.find((node) => node.tagName === 'TIME').getAttribute('datetime'), entries[0].date);
assert.deepEqual(rowsOf(groupFor('Sin etiqueta')).map((row) => row.children[0].children[0].textContent),
  entries.slice(2).map((entry) => entry.title), 'Topic rows retain the server order.');
const firstCopies = topicSections.map((section) => [...section.children]);
context.syncView();
context.syncView();
topicSections.forEach((section, i) => assert.deepEqual(section.children, firstCopies[i], 'Repeated Docsify sync keeps the same groups and rows.'));
guides.query.value = ' SOLUCION ';
const scopedTimers = [];
context.setTimeout = (callback) => scopedTimers.push(callback);
context.document.activeElement = guides.query;
handlers.input({ target: guides.query });
scopedTimers.forEach((callback) => callback());
context.setTimeout = () => {};
context.document.activeElement = undefined;
assert.equal(context.location.hash, '#/guides', 'With the page-scope chip, typing filters the page and stays on it.');
assert.equal(guides.count.textContent, '1 resultado');
assert.ok(rowsOf(groupFor('Sin etiqueta')).every((row) => row.hidden), 'A query hides every copy of unmatched guides.');
assert.ok(!groupFor('RPA').children[1].hidden && groupFor('café').hidden, 'A matching guide stays visible in its topic; a topic with no match hides.');
checkTopicCounts('Text filter');
const picker = guides.topics.children[0];
assert.equal(picker.tagName, 'DETAILS', 'The topic row sits in a native box that phones show closed.');
const jumps = picker.children[1];
assert.deepEqual(jumps.children.filter((jump) => !jump.hidden).map((jump) => jump.children[0].textContent), ['A|B <tema> "x"', 'café', 'Helios', 'RPA', 'Seguridad'],
  'A text filter offers every topic tag of a visible guide (round 4 #5); All topics hides without a topic filter.');
assert.equal(picker.children[0].textContent, 'Temas (5)', 'The box summary counts the visible topics.');
assert.equal(jumps.children.find((jump) => jump.textContent.startsWith('RPA ')).children.at(-1).textContent, '1', 'A topic jump counts its visible guides.');
const activeJump = jumps.children.find((jump) => jump.textContent.startsWith('RPA '));
assert.equal(activeJump.href, '#/guides?id=guide-topic-rpa', 'A topic jump is a route: it filters the page to its tag.');
const boxPicker = { dataset: { layout: 'box' }, open: true };
let jumpPrevented = false;
await handlers.click({
  target: { closest: (selector) => selector === '.guide-topic-picker a' ? { closest: () => boxPicker } : null },
  preventDefault() { jumpPrevented = true; }
});
assert.ok(!boxPicker.open && !jumpPrevented, 'The phone box closes and the link changes the route.');
const activeHeading = groupFor('RPA').children[0];
let jumpFocused = false;
let jumpScrolled = false;
activeHeading.focus = ({ preventScroll }) => { jumpFocused = preventScroll; };
activeHeading.scrollIntoView = ({ block }) => { jumpScrolled = block === 'start'; };
context.location.hash = activeJump.href;
context.syncView();
assert.ok(jumpFocused && jumpScrolled, 'The filtered topic heading takes focus and scrolls to the top.');
assert.equal(activeJump.getAttribute('aria-current'), 'true', 'The topic row marks the current filter.');
context.location.hash = '#/guides';
context.syncView();
assert.equal(activeJump.getAttribute('aria-current'), null);
assert.equal(guides.source.hidden, true, 'Filtering never exposes the source records.');
for (const query of ['jeiser', 'seguridad', 'alvaro']) {
  guides.query.value = query;
  handlers.input({ target: guides.query });
  assert.equal(guides.count.textContent, query === 'alvaro' ? '2 resultados' : '1 resultado', 'Author, tag, and title are searchable.');
}
guides.query.value = 'no existe';
handlers.input({ target: guides.query });
assert.equal(guides.count.textContent, '0 resultados');
assert.equal(guides.empty.hidden, false);
const emptyActions = guides.empty.children.at(-1);
assert.equal(emptyActions.children[0].href, '#/search?q=no+existe', 'An empty filter offers the same words in all of Athena.');
assert.equal(emptyActions.children[0].textContent, 'Buscar «no existe» en todo Athena');
assert.ok('clearFilter' in emptyActions.children[1].dataset, 'An empty filter can be removed in one step.');
assert.ok(topicSections.every((section) => section.hidden));
assert.ok(jumps.children.every((jump) => jump.hidden));
const oldTopics = guides.topics;
const storageCalls = [];
context.localStorage = {
  getItem(key) { storageCalls.push(['get', key]); return 'index'; },
  setItem(key, value) { storageCalls.push(['set', key, value]); }
};
// An article tag link arrives at #/guides?id=<topic>: the new section is focused and scrolled to, once.
context.location.hash = '#/guides?id=guide-topic-rpa';
guides = guidePage(entries);
const arrivals = [];
const createElement = context.document.createElement;
context.document.createElement = (tag) => Object.assign(createElement(tag), {
  focus(options) { arrivals.push([this.id, 'focus', options.preventScroll]); },
  scrollIntoView(options) { arrivals.push([this.id, 'scroll', options.block]); }
});
context.syncView();
context.syncView();
context.document.createElement = createElement;
assert.deepEqual(arrivals, [['guide-topic-rpa', 'focus', true], ['guide-topic-rpa', 'scroll', 'start']]);
// A topic link filters Guías to every guide with that tag: Seguridad is only the first guide's fifth tag.
context.location.hash = '#/guides?id=guide-topic-seguridad';
guides = guidePage(entries);
context.document.createElement = (tag) => Object.assign(createElement(tag), { focus() {}, scrollIntoView() {} });
context.syncView();
context.document.createElement = createElement;
const filteredSections = guides.topics.children.slice(1);
const seguridad = filteredSections.find((section) => section.children[0].id === 'guide-topic-seguridad');
assert.ok(seguridad && !seguridad.hidden, 'The tag link shows its topic.');
assert.deepEqual(rowsOf(seguridad).filter((row) => !row.hidden).map((row) => row.children[0].children[0].textContent), ['Álvaro'],
  'A guide whose tag is not its first tag is visible after following that tag link.');
assert.ok(filteredSections.every((section) => section === seguridad || section.hidden), 'Other topics hide while a topic filter is on.');
assert.ok(filteredSections.every((section) => section.children.every((node) => node.className !== 'guide-topic-more' || node.hidden)),
  'A topic filter lists every guide of its topic, so no section has the link.');
assert.equal(guides.count.textContent, '1 resultado');
const filterJumps = guides.topics.children[0].children[1];
assert.equal(filterJumps.children[0].href, '#/guides', 'A topic filter has a way back to all topics.');
assert.equal(filterJumps.children[0].textContent, 'Todos los temas');
assert.equal(guides.topics.children[0].children[0].textContent, 'Tema: Seguridad (1)', 'The closed phone box names the active topic.');
assert.equal(filterJumps.children[0].hidden, false);
assert.equal(filterJumps.children.find((jump) => jump.textContent.startsWith('café ')).children.at(-1).textContent, '2', 'A topic counts the guides with its tag.');
context.location.hash = '#/guides';
context.syncView();
assert.equal(filterJumps.children[0].hidden, true, 'All topics shows only while a topic filter is on.');
assert.ok(seguridad.hidden, 'Without a filter each guide shows once, under its first topic.');
assert.match(guides.topics.children[0].children[0].textContent, /^Temas \(\d+\)$/);
assert.equal(guides.count.textContent, '4 guías');
context.location.hash = '#/guides';
guides = guidePage([entries[2]]);
context.syncView();
assert.equal(guides.count.textContent, '1 guía');
assert.notEqual(guides.topics, oldTopics);
assert.ok(!guides.topics.textContent.includes('Jeiser'), 'A new access-filtered page contains no previous private rows.');
assert.equal(guides.topics.hidden, false, 'A saved index choice cannot restore the removed view.');
assert.equal(guides.topics.children.length, 2, 'Route re-entry builds the current topic records.');
assert.equal(guides.query.value, '');
assert.equal(guides.tag.value, '');
assert.deepEqual(storageCalls, [], 'Guides do not read or write browser preferences.');
context.localStorage = { getItem() { throw new Error('disabled'); }, setItem() { throw new Error('disabled'); } };
guides = guidePage([entries[2]]);
context.syncView();
assert.equal(guides.topics.hidden, false, 'Disabled storage cannot prevent the topic view.');
assert.equal(guides.count.textContent, '1 guía');
guides = guidePage([], false);
context.syncView();
assert.equal(guides.count.textContent, '0 guías');
assert.equal(guides.empty.hidden, false);
assert.equal(guides.topics.children.length, 1, 'An empty library has no topic sections.');
context.syncView();
assert.equal(guides.topics.children.length, 1, 'An empty library initializes once.');
guides = guidePage([entries[0], entries[2]], true);
context.syncView();
guides.query.value = 'Helios';
handlers.input({ target: guides.query });
assert.equal(guides.count.textContent, '1 resultado', 'The documented legacy card library keeps its filter behavior.');
assert.equal(context.prepareGuideLibrary(guides.grid).groups, null, 'Legacy cards do not build topic copies.');
context.document.querySelector = () => null;
context.document.querySelectorAll = () => [];

function railViewport(width, preference, storedWidth = null) {
  const events = {};
  const windowEvents = {};
  const style = new Map();
  const root = { dataset: {}, style: { setProperty: (name, value) => style.set(name, value) }, classList: new Set() };
  root.classList.remove = root.classList.delete;
  const media = { addEventListener(_name, handler) { this.change = handler; } };
  const writes = [];
  const fake = () => {
    const attributes = new Map();
    const listeners = {};
    return {
      attributes, listeners, classList: { remove() {} },
      setAttribute: (name, value) => attributes.set(name, String(value)), getAttribute: (name) => attributes.get(name) ?? null,
      addEventListener: (name, handler) => { listeners[name] = handler; },
      setPointerCapture() { this.captured = true; }, hasPointerCapture() { return this.captured; }
    };
  };
  const created = [];
  const railElement = { after(node) { this.next = node; }, contains: () => false };
  const context = {
    innerWidth: width,
    matchMedia(query) { media.matches = context.innerWidth <= Number(query.match(/max-width: (\d+)px/)[1]); return media; },
    localStorage: { getItem: (key) => key === 'athena.rail' ? preference : storedWidth, setItem(key, value) { writes.push([key, value]); } },
    document: {
      documentElement: root, body: { append() {} }, createElement: () => { const element = fake(); created.push(element); return element; },
      querySelector: (selector) => selector === '.rail' ? railElement : null, querySelectorAll: () => [], addEventListener(name, handler) { events[name] = handler; }
    },
    addEventListener(name, handler) { windowEvents[name] = handler; },
    window: {}
  };
  vm.runInNewContext(readFileSync(new URL('../src/assets/rail.js', import.meta.url), 'utf8'), context);
  const handle = created.find((element) => element.className === 'rail-resize');
  const click = (selector) => events.click({ target: { closest: () => ({ matches: (candidate) => candidate === selector }) } });
  const key = (name, shiftKey = false) => handle.listeners.keydown({ key: name, shiftKey, preventDefault() {} });
  const resize = (next) => { context.innerWidth = next; windowEvents.resize(); };
  return { root, media, writes, click, handle, key, resize, events, railElement, document: context.document, body: context.document.body, width: () => style.get('--rail-drag') };
}
for (const width of [320, 768, 1024]) {
  const drawer = railViewport(width, 'compact');
  assert.equal(drawer.root.dataset.rail, 'hidden', 'Narrow screens start with the content width available.');
  drawer.click('.rail-reveal');
  assert.equal(drawer.root.dataset.rail, 'expanded');
  drawer.click('.rail-toggle');
  assert.equal(drawer.root.dataset.rail, 'hidden');
  assert.deepEqual(drawer.writes, [], 'Opening and closing a drawer never changes desktop preferences.');
  drawer.media.matches = false;
  drawer.media.change();
  assert.equal(drawer.root.dataset.rail, 'compact', 'Returning to desktop restores the stored preference.');
}
// Round 5 #19: the drawer opens with the focus on the current page item (the first item when none is current).
{
  const drawer = railViewport(390, 'compact');
  const focused = [];
  const item = (name) => ({ focus: () => focused.push(name) });
  let current = item('Guías');
  drawer.document.querySelector = (selector) => ({ '.rail .rail-item[aria-current="page"]': current, '.rail .rail-item[href]': item('Inicio') })[selector] || null;
  drawer.click('.rail-reveal');
  drawer.click('.rail-toggle');
  current = null;
  drawer.click('.rail-reveal');
  assert.deepEqual(focused, ['Guías', 'Inicio']);
}
// The open drawer makes the rest of the page inert (reader and admin), and only while it is open.
const inertDrawer = railViewport(390, 'expanded');
const page = { inert: false };
inertDrawer.body.children = [inertDrawer.railElement, page];
inertDrawer.railElement.parentElement = inertDrawer.body;
inertDrawer.click('.rail-reveal');
assert.deepEqual([page.inert, inertDrawer.railElement.inert], [true, undefined], 'The page behind the drawer is inert.');
inertDrawer.click('.rail-toggle');
assert.equal(page.inert, false, 'Closing the drawer restores the page.');
inertDrawer.click('.rail-reveal');
inertDrawer.media.matches = false;
inertDrawer.media.change();
assert.equal(page.inert, false, 'A desktop width never leaves the page inert.');
const desktopRail = railViewport(1025, 'compact');
assert.equal(desktopRail.root.dataset.rail, 'compact');
desktopRail.click('.rail-toggle');
assert.equal(desktopRail.root.dataset.rail, 'expanded');
assert.deepEqual(desktopRail.writes, [['athena.rail', 'expanded']]);
assert.equal(railViewport(1366, 'hidden').root.dataset.rail, 'hidden');
assert.equal(railViewport(1366, 'invalid').root.dataset.rail, 'expanded');
// Draggable width: restored before the first paint, clamped to 200-420px and 40% of the window, saved on its own key.
assert.equal(railViewport(1440, 'expanded').width(), '256px', 'No stored width keeps the default.');
assert.equal(railViewport(1440, 'expanded', '340').width(), '340px', 'The stored width applies when rail.js runs in the head.');
assert.equal(railViewport(1440, 'expanded', '999').width(), '420px');
assert.equal(railViewport(1440, 'expanded', '20').width(), '200px');
assert.equal(railViewport(1440, 'expanded', 'junk').width(), '256px');
const sized = railViewport(1025, 'expanded', '420');
assert.equal(sized.width(), '410px', 'Never wider than 40% of the window.');
assert.deepEqual(sized.writes, [], 'Restoring a width never rewrites it.');
sized.resize(1440);
assert.equal(sized.width(), '420px', 'A wider window gets the stored preference back.');
const resizer = railViewport(1440, 'expanded');
assert.deepEqual(['role', 'aria-orientation', 'aria-valuemin', 'aria-valuemax', 'aria-valuenow', 'aria-label'].map((name) => resizer.handle.getAttribute(name)),
  ['separator', 'vertical', '200', '420', '256', 'Ajustar el ancho de la navegación']);
assert.equal(resizer.handle.tabIndex, 0);
resizer.events.DOMContentLoaded();
assert.equal(resizer.railElement.next, resizer.handle, 'The handle follows the rail, outside its clipped box.');
resizer.key('ArrowRight');
assert.equal(resizer.width(), '272px');
resizer.key('ArrowLeft', true);
assert.equal(resizer.width(), '208px');
resizer.key('ArrowLeft');
assert.equal(resizer.width(), '200px', 'Keys stop at the minimum and never switch to compact.');
assert.equal(resizer.root.dataset.rail, 'expanded');
resizer.key('End');
assert.equal(resizer.handle.getAttribute('aria-valuenow'), '420');
resizer.key('Home');
assert.equal(resizer.width(), '200px');
resizer.key('Enter');
assert.equal(resizer.width(), '256px', 'Enter resets the width.');
assert.deepEqual(resizer.writes.at(-1), ['athena.rail.width', '256']);
resizer.handle.listeners.pointerdown({ button: 0, pointerId: 1, clientX: 255, preventDefault() {} });
assert(resizer.root.classList.has('rail-resizing'), 'Dragging turns off transitions and selection.');
const writesBeforeDrag = resizer.writes.length;
resizer.handle.listeners.pointermove({ pointerId: 1, clientX: 339 });
assert.equal(resizer.width(), '340px', 'The width follows the pointer live.');
assert.equal(resizer.writes.length, writesBeforeDrag, 'Moves are not stored one by one.');
resizer.handle.listeners.pointermove({ pointerId: 1, clientX: 900 });
assert.equal(resizer.width(), '420px');
resizer.handle.listeners.pointermove({ pointerId: 1, clientX: 50 });
assert.equal(resizer.width(), '200px');
assert.equal(resizer.root.dataset.rail, 'expanded', 'Dragging below the minimum does not switch to compact.');
resizer.handle.listeners.lostpointercapture();
assert(!resizer.root.classList.has('rail-resizing'));
assert.deepEqual(resizer.writes.at(-1), ['athena.rail.width', '200'], 'The drag end stores the width.');
resizer.handle.listeners.dblclick();
assert.deepEqual(resizer.writes.at(-1), ['athena.rail.width', '256'], 'Double-click resets the width.');
// The handle shows only for the expanded rail on wide screens; the narrow drawer keeps the default width.
const railCss = readFileSync(new URL('../src/assets/rail.css', import.meta.url), 'utf8');
assert.match(railCss, /\.rail-resize \{[^}]*display: none/);
assert.match(railCss, /@media \(min-width: 1025px\) \{ html\[data-rail=expanded\] \.rail-resize \{ display: block; \} \}/);
assert.match(railCss, /@media \(max-width: 1024px\) \{\n  :root, html\[data-rail\] \{ --rail-w: 256px; --rail-current: 0px; \}/);
assert.match(railCss, /--rail-w: var\(--rail-drag, 256px\)/);
console.log('Search, guide topics/filters, sign-in, reader compiler/router, navigation, responsive rail/outline, PDF viewer and sorting checks passed.');
