let pageTreeItems = [];
let searchIndexPromise;
let searchRenderVersion = 0;

const normalize = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/\s+/g, ' ')
  .trim();

function getRouteState() {
  const raw = location.hash.slice(1) || '/';
  const queryAt = raw.indexOf('?');
  const encodedPath = queryAt === -1 ? raw : raw.slice(0, queryAt);
  let path = encodedPath;
  try {
    path = decodeURIComponent(encodedPath);
  } catch {
    path = encodedPath;
  }
  return {
    path,
    params: new URLSearchParams(queryAt === -1 ? '' : raw.slice(queryAt + 1))
  };
}

function buildSearchHash(query, type) {
  const params = new URLSearchParams();
  if (query.trim()) params.set('q', query.trim());
  if (type) params.set('type', type);
  const suffix = params.toString();
  return '#/search' + (suffix ? '?' + suffix : '');
}

function replaceSearchUrl(query, type) {
  const url = new URL(location.href);
  url.hash = buildSearchHash(query, type);
  history.replaceState(history.state, '', url);
}

function updatePageTreeCurrent() {
  if (!pageTreeItems.length) return;
  const current = [...pageTreeItems].reverse().find(({ heading }) => heading.getBoundingClientRect().top <= 120) || pageTreeItems[0];
  pageTreeItems.forEach(({ link }) => link.removeAttribute('aria-current'));
  current.link.setAttribute('aria-current', 'location');
}

function buildPageTree() {
  document.querySelector('.page-tree')?.remove();
  document.body.classList.remove('has-page-tree');
  pageTreeItems = [];

  const route = getRouteState().path;
  const article = document.querySelector('.markdown-section');
  if (!route.startsWith('/content/') || !article) return;

  const headings = [...article.querySelectorAll('h1[id],h2[id],h3[id]')];
  if (!headings.length) return;

  const nav = document.createElement('nav');
  nav.className = 'page-tree';
  nav.setAttribute('aria-label', 'En esta página');

  const details = document.createElement('details');
  details.open = matchMedia('(min-width: 1200px)').matches;
  const summary = document.createElement('summary');
  summary.textContent = 'En esta página';
  const list = document.createElement('ol');

  headings.forEach((heading) => {
    const item = document.createElement('li');
    item.className = 'page-tree__level-' + heading.tagName.slice(1);
    const link = document.createElement('a');
    link.href = heading.querySelector('a.anchor')?.getAttribute('href') || '#' + heading.id;
    link.textContent = heading.textContent.trim();
    item.append(link);
    list.append(item);
    pageTreeItems.push({ heading, link });
  });

  details.append(summary, list);
  nav.append(details);
  article.insertBefore(nav, article.querySelector('h1') || article.firstChild);
  document.body.classList.add('has-page-tree');
  updatePageTreeCurrent();
}

function filterGuides() {
  const library = document.querySelector('.guide-library');
  if (!library) return;
  const query = normalize(document.querySelector('#guide-filter')?.value.trim() || '');
  const tag = normalize(document.querySelector('#guide-tag')?.value || '');
  let visible = 0;
  library.querySelectorAll('.library-card').forEach((card) => {
    const matchesText = !query || normalize(card.dataset.search || '').includes(query);
    const matchesTag = !tag || (card.dataset.tags || '').split('|').some((value) => normalize(value) === tag);
    card.hidden = !(matchesText && matchesTag);
    if (!card.hidden) visible += 1;
  });
  const count = document.querySelector('#guide-count');
  const empty = document.querySelector('.library-empty');
  if (count) count.textContent = visible + ' ' + (visible === 1 ? 'resultado' : 'resultados');
  if (empty) empty.hidden = visible !== 0;
}

function filterDownloads() {
  const input = document.querySelector('#download-filter');
  if (!input) return;
  const query = normalize(input.value);
  const section = document.querySelector('#download-section')?.value || '';
  let visible = 0;
  document.querySelectorAll('.download-section').forEach((block) => {
    let shown = 0;
    block.querySelectorAll('.catalog-item').forEach((item) => {
      item.hidden = !((!query || normalize(item.dataset.search || '').includes(query)) && (!section || block.dataset.section === section));
      if (!item.hidden) shown += 1;
    });
    block.hidden = shown === 0;
    // Versiones anteriores opens when a match is inside it.
    const archive = block.querySelector('.download-archive');
    if (archive && (query || section)) archive.open = shown > 0;
    visible += shown;
  });
  const count = document.querySelector('#download-count');
  const empty = document.querySelector('.download-empty');
  if (count) count.textContent = visible + ' ' + (visible === 1 ? 'archivo' : 'archivos');
  if (empty) empty.hidden = visible !== 0;
}

let railPromise;

// The portal rail comes from /_sidebar.md: "- Group" lines, then indented "- [Label](href)" links.
function buildRail() {
  const nav = document.querySelector('.rail-nav');
  if (!nav || railPromise) return railPromise;
  railPromise = fetch('/_sidebar.md', { credentials: 'same-origin' })
    .then((response) => (response.ok ? response.text() : Promise.reject(new Error('Sidebar request failed: ' + response.status))))
    .then((markdown) => {
      let list;
      markdown.split('\n').forEach((line) => {
        const link = line.match(/^\s+[-*]\s*\[([^\]]+)\]\(([^\s)]+)/);
        if (link && list) {
          const [, label, href] = link;
          const item = document.createElement('a');
          item.className = 'rail-item';
          item.href = href === '/' ? '#/' : href.endsWith('.md') ? '#' + href.slice(0, -3) : href;
          const text = document.createElement('span');
          text.className = 'rail-label';
          text.textContent = label;
          item.append(text);
          const entry = document.createElement('li');
          entry.append(item);
          list.append(entry);
        } else if (line.startsWith('- ')) {
          const group = document.createElement('div');
          group.className = 'rail-group';
          const heading = document.createElement('h2');
          heading.className = 'rail-group-label';
          heading.id = 'rail-group-' + (nav.children.length + 1);
          heading.textContent = line.slice(2).trim();
          list = document.createElement('ul');
          list.setAttribute('aria-labelledby', heading.id);
          group.append(heading, list);
          nav.append(group);
        }
      });
      window.athenaRail?.decorate(nav);
      markRail();
    })
    .catch(() => {
      railPromise = null;
    });
  return railPromise;
}

function markRail() {
  const { path } = getRouteState();
  document.querySelectorAll('.rail-nav .rail-item').forEach((item) => {
    const href = item.getAttribute('href');
    const route = href.startsWith('#') ? href.slice(1) : '';
    const current = route && (route === '/' ? path === '/' : path === route || path.startsWith(route + '/'));
    if (current) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
}

function docsifyHeadingIds(pageTitle, headings) {
  const seen = new Map();
  return [{ title: pageTitle, level: 1 }, ...headings].map((heading) => {
    let id = String(heading.title || '')
      .trim()
      .replace(/[A-Z]+/g, (value) => value.toLowerCase())
      .replace(/<[^>]+>/g, '')
      .replace(/[\u2000-\u206F\u2E00-\u2E7F\\'!"#$%&()*+,./:;<=>?@[\]^\`{|}~]/g, '')
      .replace(/\s/g, '-')
      .replace(/-+/g, '-')
      .replace(/^(\d)/, '_$1');
    const count = seen.get(id) || 0;
    seen.set(id, count + 1);
    if (count) id += '-' + count;
    return { ...heading, level: Number(heading.level) || 2, id };
  }).slice(1).filter((heading) => heading.level === 2 || heading.level === 3);
}

function prepareSearchEntry(entry) {
  const headings = docsifyHeadingIds(entry.title, Array.isArray(entry.headings) ? entry.headings : []);
  const tags = Array.isArray(entry.tags) ? entry.tags.filter(Boolean).map(String) : [];
  const prepared = { ...entry, headings, tags };
  prepared._title = normalize(entry.title);
  prepared._summary = normalize(entry.summary);
  prepared._author = normalize(entry.author);
  prepared._tags = tags.map(normalize);
  prepared._headingTitles = headings.map((heading) => normalize(heading.title));
  prepared._text = normalize(entry.text);
  prepared._all = [
    prepared._title,
    prepared._summary,
    prepared._author,
    prepared._tags.join(' '),
    headings.map((heading) => normalize(heading.title + ' ' + heading.text)).join(' '),
    prepared._text
  ].join(' ');
  return prepared;
}

function loadSearchIndex() {
  if (!searchIndexPromise) {
    searchIndexPromise = fetch('/search-index.json')
      .then((response) => {
        if (!response.ok) throw new Error('Search index request failed: ' + response.status);
        return response.json();
      })
      .then((entries) => {
        if (!Array.isArray(entries)) throw new Error('Search index is not an array.');
        return entries.map(prepareSearchEntry);
      })
      .catch((error) => {
        searchIndexPromise = null;
        throw error;
      });
  }
  return searchIndexPromise;
}

function searchTerms(query) {
  return [...new Set(normalize(query).split(' ').filter(Boolean))];
}

function matchesSearchType(entry, type) {
  if (!type) return true;
  if (type === 'update') return entry.kind === 'announcement' || entry.kind === 'release';
  if (type === 'pdf') return entry.kind === 'pdf' || Boolean(entry.pdf);
  return entry.kind === type;
}

function scoreSearchEntry(entry, terms, query) {
  if (!terms.every((term) => entry._all.includes(term))) return -1;
  let score = entry._title === normalize(query) ? 1000 : entry._title.includes(normalize(query)) ? 500 : 0;
  terms.forEach((term) => {
    if (entry._title.includes(term)) score += 120;
    if (entry._tags.some((tag) => tag.includes(term))) score += 60;
    if (entry._headingTitles.some((heading) => heading.includes(term))) score += 50;
    if (entry._author.includes(term)) score += 40;
    if (entry._summary.includes(term)) score += 20;
    if (entry._text.includes(term)) score += 2;
  });
  return score;
}

function excerptAround(text, terms) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim();
  if (!clean) return '';
  const folded = normalize(clean);
  const pivotTerm = [...terms]
    .filter((term) => folded.includes(term))
    .sort((left, right) => right.length - left.length)[0];
  const pivot = pivotTerm ? folded.indexOf(pivotTerm) : 0;
  let start = Math.max(0, pivot - 75);
  let end = Math.min(clean.length, start + 240);
  if (start) {
    const nextSpace = clean.indexOf(' ', start);
    if (nextSpace > -1 && nextSpace < pivot) start = nextSpace + 1;
  }
  if (end < clean.length) {
    const previousSpace = clean.lastIndexOf(' ', end);
    if (previousSpace > start) end = previousSpace;
  }
  return (start ? '…' : '') + clean.slice(start, end) + (end < clean.length ? '…' : '');
}

function matchStrength(text, terms) {
  const folded = normalize(text);
  return terms.reduce((score, term) => score + (folded.includes(term) ? term.length : 0), 0);
}

function metadataMatchLabel(entry, terms) {
  const sources = [];
  if (terms.some((term) => entry._title.includes(term))) sources.push('título');
  if (terms.some((term) => entry._summary.includes(term))) sources.push('resumen');
  if (terms.some((term) => entry._author.includes(term))) sources.push('autor');
  if (terms.some((term) => entry._tags.some((tag) => tag.includes(term)))) sources.push('etiqueta');
  return sources.length ? 'Coincidencia en: ' + sources.join(', ') : '';
}

function findSnippet(entry, terms) {
  const headingMatch = entry.headings
    .map((heading) => ({ heading, score: matchStrength(heading.title + ' ' + heading.text, terms) }))
    .sort((left, right) => right.score - left.score)[0];
  const bodyScore = matchStrength(entry.text, terms);
  if (bodyScore > (headingMatch?.score || 0)) return { text: excerptAround(entry.text, terms), heading: null, source: '' };
  if (headingMatch?.score) {
    const sectionText = [headingMatch.heading.title, headingMatch.heading.text].filter(Boolean).join('. ');
    return { text: excerptAround(sectionText, terms), heading: headingMatch.heading, source: '' };
  }
  return { text: '', heading: null, source: metadataMatchLabel(entry, terms) };
}

const accentPatterns = {
  a: '[aáàäâãå]',
  e: '[eéèëê]',
  i: '[iíìïî]',
  o: '[oóòöôõ]',
  u: '[uúùüû]',
  n: '[nñ]'
};

function escapePattern(value) {
  return value.replace(/[.*+?^$()|[\]\\{}]/g, '\\$&');
}

function appendHighlighted(target, text, terms) {
  const patterns = [...terms]
    .sort((left, right) => right.length - left.length)
    .map((term) => Array.from(term).map((character) => accentPatterns[character] || escapePattern(character)).join(''));
  if (!patterns.length) {
    target.textContent = text;
    return;
  }
  const pattern = new RegExp('(' + patterns.join('|') + ')', 'giu');
  let lastIndex = 0;
  let match;
  while ((match = pattern.exec(text))) {
    target.append(document.createTextNode(text.slice(lastIndex, match.index)));
    const mark = document.createElement('mark');
    mark.textContent = match[0];
    target.append(mark);
    lastIndex = match.index + match[0].length;
  }
  target.append(document.createTextNode(text.slice(lastIndex)));
}

function searchKindLabel(kind) {
  return {
    guide: 'Guía',
    tool: 'Herramienta',
    announcement: 'Anuncio',
    release: 'Versión',
    page: 'Página',
    download: 'Descarga',
    pdf: 'PDF'
  }[kind] || kind;
}

function createSearchState(title, text) {
  const state = document.createElement('div');
  state.className = 'search-state';
  const heading = document.createElement('strong');
  heading.textContent = title;
  const copy = document.createElement('p');
  copy.textContent = text;
  state.append(heading, copy);
  return state;
}

function createSearchResult(entry, terms) {
  const article = document.createElement('article');
  article.className = 'search-result';

  const meta = document.createElement('div');
  meta.className = 'search-result__meta';
  const kind = document.createElement('p');
  kind.className = 'card-kicker';
  kind.textContent = searchKindLabel(entry.kind);
  meta.append(kind);

  const facts = [entry.date, entry.author].filter(Boolean);
  if (facts.length) {
    const details = document.createElement('small');
    details.textContent = facts.join(' · ');
    meta.append(details);
  }
  if (entry.tags.length) {
    const tags = document.createElement('p');
    tags.className = 'tag-list';
    entry.tags.forEach((value) => {
      const tag = document.createElement('span');
      tag.textContent = value;
      tags.append(tag);
    });
    meta.append(tags);
  }

  const body = document.createElement('div');
  body.className = 'search-result__body';
  const title = document.createElement('h2');
  const titleLink = document.createElement('a');
  titleLink.href = entry.route;
  appendHighlighted(titleLink, entry.title, terms);
  if (entry.kind === 'pdf') {
    titleLink.target = '_blank';
    titleLink.rel = 'noreferrer';
  }
  title.append(titleLink);
  const summary = document.createElement('p');
  summary.className = 'search-result__summary';
  appendHighlighted(summary, entry.summary, terms);
  body.append(title, summary);

  const snippet = findSnippet(entry, terms);
  if (snippet.text) {
    const excerpt = document.createElement('p');
    excerpt.className = 'search-result__excerpt';
    appendHighlighted(excerpt, snippet.text, terms);
    body.append(excerpt);
  }
  if (snippet.source) {
    const source = document.createElement('p');
    source.className = 'search-result__match';
    source.textContent = snippet.source;
    body.append(source);
  }

  const actions = document.createElement('p');
  actions.className = 'search-result__actions';
  if (snippet.heading && entry.route.startsWith('#/')) {
    const section = document.createElement('a');
    section.href = entry.route + '?id=' + encodeURIComponent(snippet.heading.id);
    section.textContent = 'Ir a: ' + snippet.heading.title;
    actions.append(section);
  }
  if (entry.pdf && entry.kind !== 'pdf') {
    const pdf = document.createElement('a');
    pdf.href = entry.pdf;
    pdf.target = '_blank';
    pdf.rel = 'noreferrer';
    pdf.textContent = 'Abrir PDF';
    actions.append(pdf);
  }
  if (actions.childElementCount) body.append(actions);

  article.append(meta, body);
  return article;
}

async function renderSearchPage() {
  const results = document.querySelector('#search-results');
  const count = document.querySelector('#search-result-count');
  const typeSelect = document.querySelector('#athena-search-type');
  if (!results || !count || !typeSelect) return;

  const version = ++searchRenderVersion;
  const { params } = getRouteState();
  const query = params.get('q') || '';
  const requestedType = params.get('type') || '';
  const type = [...typeSelect.options].some((option) => option.value === requestedType) ? requestedType : '';
  const terms = searchTerms(query);
  typeSelect.value = type;

  if (!terms.length) {
    count.textContent = '';
    results.replaceChildren(createSearchState('¿Qué necesita encontrar?', 'Busque una guía, herramienta, actualización, descarga o PDF.'));
    return;
  }

  count.textContent = 'Buscando…';
  results.replaceChildren();
  try {
    const index = await loadSearchIndex();
    if (version !== searchRenderVersion || !results.isConnected) return;
    const matches = index
      .filter((entry) => matchesSearchType(entry, type))
      .map((entry) => ({ entry, score: scoreSearchEntry(entry, terms, query) }))
      .filter((match) => match.score >= 0)
      .sort((left, right) => right.score - left.score
        || String(right.entry.date).localeCompare(String(left.entry.date))
        || left.entry.title.localeCompare(right.entry.title, 'es'));

    count.textContent = matches.length + ' ' + (matches.length === 1 ? 'resultado' : 'resultados');
    if (!matches.length) {
      results.replaceChildren(createSearchState('Sin resultados', 'Pruebe menos palabras, cambie el tipo de contenido o revise la escritura.'));
      return;
    }
    const fragment = document.createDocumentFragment();
    matches.forEach(({ entry }) => fragment.append(createSearchResult(entry, terms)));
    results.replaceChildren(fragment);
  } catch {
    if (version !== searchRenderVersion || !results.isConnected) return;
    count.textContent = '';
    results.replaceChildren(createSearchState('No se pudo cargar la búsqueda', 'Recargue la página para intentarlo de nuevo.'));
  }
}

function placeSearch() {
  let search = document.querySelector('#athena-search');
  if (!search) {
    const template = document.querySelector('#athena-search-template');
    search = template?.content.firstElementChild.cloneNode(true);
    if (!search) return;
    search.hidden = true;
    document.body.append(search);
  }
  const { path, params } = getRouteState();
  const home = path === '/';
  const searchPage = path === '/search';
  const railSlot = document.querySelector('.rail-search-slot');
  const homeSlot = document.querySelector('#home-search-slot');
  const pageSlot = document.querySelector('#search-page-slot');

  let placed = false;
  if (searchPage && pageSlot) {
    if (search.parentElement !== pageSlot) pageSlot.append(search);
    placed = true;
  } else if (home && homeSlot) {
    if (search.parentElement !== homeSlot) homeSlot.append(search);
    placed = true;
  } else if (!home && !searchPage && railSlot) {
    if (search.parentElement !== railSlot) railSlot.append(search);
    placed = true;
  }

  search.hidden = !placed;
  const input = search.querySelector('#athena-search-input');
  if (input) input.value = searchPage ? params.get('q') || '' : '';
}

// The article's "Abrir PDF original" link becomes an in-page viewer. Docsify rewrites the
// link to a #/pdf/... route, so the leading hash is dropped to get the file back.
function buildPdfViewer() {
  if (document.querySelector('.markdown-section .pdf-viewer')) return;
  const link = document.querySelector('.markdown-section a[href$=".pdf"]');
  const src = link?.getAttribute('href').replace(/^#/, '') || '';
  if (!src.startsWith('/pdf/') || !getRouteState().path.startsWith('/content/')) return;
  const viewer = document.createElement('section');
  viewer.className = 'pdf-viewer';
  const actions = document.createElement('p');
  actions.className = 'pdf-viewer__actions';
  [['Descargar PDF', src + '?download=1', ''], ['Abrir en pestaña nueva', src, '_blank']].forEach(([label, href, target]) => {
    const a = document.createElement('a');
    a.className = 'pdf-link';
    a.href = href;
    a.textContent = label;
    if (target) {
      a.target = target;
      a.rel = 'noreferrer';
    }
    actions.append(a);
  });
  const frame = document.createElement('iframe');
  frame.src = src;
  frame.title = 'Documento PDF';
  frame.loading = 'lazy';
  viewer.append(actions, frame);
  link.closest('p').replaceWith(viewer);
}

function syncView() {
  const { path } = getRouteState();
  document.body.classList.toggle('home-view', path === '/');
  buildRail();
  markRail();
  placeSearch();
  filterGuides();
  filterDownloads();
  buildPageTree();
  buildPdfViewer();
  if (path === '/search') renderSearchPage();
}

document.addEventListener('click', async (event) => {
  const pageTreeLink = event.target.closest('.page-tree a');
  if (pageTreeLink && !matchMedia('(min-width: 1200px)').matches) pageTreeLink.closest('details').open = false;

  const copyButton = event.target.closest('button.copy-page');
  if (!copyButton) return;
  const label = copyButton.querySelector('span');
  try {
    const route = getRouteState().path;
    const response = await fetch(route.endsWith('.md') ? route : route + '.md');
    if (!response.ok) throw new Error('Article request failed: ' + response.status);
    await navigator.clipboard.writeText(await response.text());
    copyButton.classList.add('copied');
    label.textContent = 'Copiado';
    setTimeout(() => {
      if (!copyButton.isConnected) return;
      copyButton.classList.remove('copied');
      label.textContent = 'Copiar página';
    }, 2000);
  } catch {
    label.textContent = 'No se pudo copiar';
  }
});

document.addEventListener('submit', (event) => {
  if (!event.target.matches('#athena-search')) return;
  event.preventDefault();
  const query = event.target.querySelector('#athena-search-input').value;
  const { path } = getRouteState();
  const type = path === '/search' ? document.querySelector('#athena-search-type')?.value || '' : '';
  if (path === '/search') {
    replaceSearchUrl(query, type);
    renderSearchPage();
  } else {
    location.hash = buildSearchHash(query, type);
  }
});

document.addEventListener('input', (event) => {
  if (event.target.matches('#guide-filter')) filterGuides();
  if (event.target.matches('#download-filter')) filterDownloads();
  if (event.target.matches('#athena-search-input') && getRouteState().path === '/search') {
    const type = document.querySelector('#athena-search-type')?.value || '';
    replaceSearchUrl(event.target.value, type);
    renderSearchPage();
  }
});

document.addEventListener('change', (event) => {
  if (event.target.matches('#guide-tag')) filterGuides();
  if (event.target.matches('#download-section')) filterDownloads();
  if (event.target.matches('#athena-search-type')) {
    const query = document.querySelector('#athena-search-input')?.value || '';
    replaceSearchUrl(query, event.target.value);
    renderSearchPage();
  }
});

window.athenaSyncView = syncView;
syncView();
window.addEventListener('load', syncView);
window.addEventListener('hashchange', syncView);
window.addEventListener('scroll', updatePageTreeCurrent, { passive: true });
