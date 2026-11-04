const t = (text) => window.AthenaI18n?.t(text) || text;
const currentLang = () => document.documentElement.lang || 'es';
const countLabel = (count, single, plural) => new Intl.NumberFormat(currentLang()).format(count) + ' ' + t(count === 1 ? single : plural);
const sortLabel = (label, descending = false) => t('Ordenar') + ' ' + t(label) + ' ' + t('en orden') + ' ' + t(descending ? 'descendente' : 'ascendente');

let pageTreeItems = [];
let searchIndexPromise;
let searchRenderVersion = 0;
let searchScope = '';
let searchPageNode;
let searchPath;

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
  updateSignInLinks();
}

function updatePageTreeCurrent() {
  if (!pageTreeItems.length) return;
  const current = [...pageTreeItems].reverse().find(({ heading }) => heading.getBoundingClientRect().top <= 120) || pageTreeItems[0];
  pageTreeItems.forEach(({ link }) => link.removeAttribute('aria-current'));
  current.link.setAttribute('aria-current', 'location');
}

function updatePageTreeLayout() {
  const tree = document.querySelector('.page-tree');
  if (!tree) return;
  const layout = getComputedStyle(tree).position === 'sticky' ? 'side' : 'inline';
  if (tree.dataset.layout === layout) return;
  tree.dataset.layout = layout;
  tree.querySelector('details').open = layout === 'side';
}

function buildPageTree() {
  document.querySelector('.page-tree')?.remove();
  document.body.classList.remove('has-page-tree');
  pageTreeItems = [];

  const route = getRouteState().path;
  const article = document.querySelector('.markdown-section');
  // An HTML article's headings are inside its sandboxed frame.
  if (!route.startsWith('/content/') || !article || article.querySelector('.unavailable-page, .html-article, .html-article-frame')) return;

  const headings = [...article.querySelectorAll('h1[id],h2[id],h3[id]')];
  if (!headings.length) return;

  const nav = document.createElement('nav');
  nav.className = 'page-tree';
  nav.setAttribute('aria-label', t('En esta página'));

  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = t('En esta página');
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
  article.before(nav);
  document.body.classList.add('has-page-tree');
  updatePageTreeLayout();
  updatePageTreeCurrent();
}

const guideLibraries = new WeakMap();

function prepareGuideLibrary(library) {
  if (guideLibraries.has(library)) return guideLibraries.get(library);
  const state = {
    rows: [...library.querySelectorAll('.guide-row,.library-card')].map((row) => ({
      row,
      search: normalize(row.dataset.search),
      tags: new Map([...row.querySelectorAll('.tag-list span')]
        .map((tag) => [normalize(tag.textContent), tag.textContent.trim()]).filter(([key]) => key))
    })),
    groups: null
  };
  guideLibraries.set(library, state);
  return state;
}

function buildGuideTopics(library, state) {
  if (state.groups) return;
  const topics = library.querySelector('#guide-topics');
  const jumps = document.createElement('nav');
  jumps.className = 'guide-topic-jumps';
  jumps.tabIndex = 0;
  jumps.setAttribute('aria-label', t('Temas de las guías'));
  state.groups = new Map();
  state.rows.forEach((entry) => {
    const tags = entry.tags.size ? entry.tags : new Map([['', t('Sin etiqueta')]]);
    tags.forEach((label, key) => {
      let group = state.groups.get(key);
      if (!group) {
        const section = document.createElement('section');
        section.className = 'guide-topic';
        const heading = document.createElement('h2');
        heading.id = 'guide-topic-' + (state.groups.size + 1);
        heading.tabIndex = -1;
        heading.textContent = label;
        section.setAttribute('aria-labelledby', heading.id);
        section.append(heading);
        const jump = document.createElement('a');
        jump.href = '#/guides?id=' + heading.id;
        jump.dataset.guideTopic = heading.id;
        jump.textContent = label;
        jumps.append(jump);
        topics.append(section);
        group = { section, jump, entries: [] };
        state.groups.set(key, group);
      }
      const article = document.createElement('article');
      article.className = 'guide-topic-row';
      const detail = entry.row.querySelector('.guide-detail').cloneNode(true);
      const meta = document.createElement('div');
      meta.className = 'guide-topic-meta';
      const author = document.createElement('span');
      author.textContent = entry.row.querySelector('.guide-author').textContent;
      meta.append(author, entry.row.querySelector('time').cloneNode(true));
      article.append(detail, meta);
      group.section.append(article);
      group.entries.push({ entry, article });
    });
  });
  topics.prepend(jumps);
}

function filterGuides() {
  const library = document.querySelector('.guide-library');
  if (!library) return;
  const state = prepareGuideLibrary(library);
  const query = normalize(searchScope === 'guide' ? document.querySelector('#athena-search-input')?.value || '' : '');
  let visible = 0;
  state.rows.forEach((entry) => {
    entry.row.hidden = Boolean(query && !entry.search.includes(query));
    if (!entry.row.hidden) visible += 1;
  });
  if (library.querySelector('#guide-topics')) buildGuideTopics(library, state);
  state.groups?.forEach((group) => {
    let shown = 0;
    group.entries.forEach(({ entry, article }) => {
      article.hidden = entry.row.hidden;
      if (!article.hidden) shown += 1;
    });
    group.section.hidden = group.jump.hidden = !shown;
  });
  const count = document.querySelector('#guide-count');
  const empty = document.querySelector('.library-empty');
  if (count) count.textContent = countLabel(visible, 'resultado', 'resultados');
  if (empty) empty.hidden = visible !== 0;
}

function filterDownloads() {
  if (!document.querySelector('#download-count')) return;
  const query = normalize(searchScope === 'download' ? document.querySelector('#athena-search-input')?.value || '' : '');
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
  if (count) count.textContent = countLabel(visible, 'archivo', 'archivos');
  if (empty) empty.hidden = visible !== 0;
}

function buildTableSorting() {
  const collator = new Intl.Collator(currentLang(), { numeric: true, sensitivity: 'base' });
  document.querySelectorAll('.markdown-section table').forEach((table) => {
    if (table.dataset.sortReady || table.dataset.sortable === 'false' || table.getAttribute('role') === 'presentation'
      || table.parentElement.closest('table') || table.querySelector('table')
      || table.tHead?.rows.length !== 1 || table.tBodies.length !== 1) return;
    const headers = [...table.tHead.rows[0].cells];
    const body = table.tBodies[0];
    const rows = [...body.rows];
    const cells = [...headers, ...rows.flatMap((row) => [...row.cells])];
    if (!headers.length || cells.some((cell) => cell.colSpan !== 1 || cell.rowSpan !== 1)
      || rows.some((row) => row.cells.length !== headers.length)
      || headers.some((header) => header.tagName !== 'TH' || !header.textContent.trim()
        || header.querySelector('a,button,input,select,textarea,summary,[tabindex],[contenteditable]'))) return;
    table.dataset.sortReady = 'true';
    headers.forEach((header, column) => {
      const label = header.textContent.trim();
      // ponytail: infer long text from content; authored column widths if short prose needs a fixed width.
      if (rows.some((row) => row.cells[column].textContent.trim().length > 60)) header.dataset.longText = 'true';
      header.setAttribute('scope', 'col');
      header.setAttribute('aria-sort', 'none');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'table-sort';
      button.setAttribute('aria-label', sortLabel(label));
      const text = document.createElement('span');
      text.append(...header.childNodes);
      const indicator = document.createElement('span');
      indicator.className = 'table-sort-direction';
      indicator.setAttribute('aria-hidden', 'true');
      button.append(text, indicator);
      header.append(button);
      button.addEventListener('click', () => {
        const descending = header.getAttribute('aria-sort') === 'ascending';
        const value = (row) => row.cells[column].dataset.sortValue
          ?? row.cells[column].querySelector('time[datetime]')?.getAttribute('datetime')
          ?? row.cells[column].textContent.trim();
        rows.map((row, index) => {
          const key = value(row);
          const date = /^\d{4}-\d{2}-\d{2}(?:T|$)/.test(key) ? Date.parse(key) : NaN;
          return { row, index, value: key, date };
        })
          .sort((left, right) => {
            const dateOrder = Number.isFinite(right.date) - Number.isFinite(left.date);
            const compared = dateOrder || (Number.isFinite(left.date) ? left.date - right.date : collator.compare(left.value, right.value));
            return (descending ? -1 : 1) * compared || left.index - right.index;
          })
          .forEach(({ row }) => body.append(row));
        headers.forEach((other) => {
          other.setAttribute('aria-sort', 'none');
          other.querySelector('button').setAttribute('aria-label', sortLabel(other.querySelector('button').textContent.trim()));
        });
        header.setAttribute('aria-sort', descending ? 'descending' : 'ascending');
        button.setAttribute('aria-label', sortLabel(label, !descending));
      });
    });
  });
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
      updateSignInLinks();
      window.AthenaI18n?.translate();
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
  // Older migration indexes omit H1; current indexes contain the actual reader sequence.
  const sequence = headings.some((heading) => Number(heading.level) === 1)
    ? headings : [{ title: pageTitle, level: 1 }, ...headings];
  const slugify = window.Docsify.slugify;
  slugify.clear();
  const result = sequence.map((heading) => {
    const raw = heading.raw ?? heading.title ?? '';
    const custom = raw.match(/(?:^|\s):id=([\w-%]+)/);
    return { ...heading, level: Number(heading.level) || 2, id: slugify(custom?.[1] || raw) };
  }).filter((heading) => heading.level === 2 || heading.level === 3);
  slugify.clear();
  return result;
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
  if (terms.some((term) => entry._title.includes(term))) sources.push(t('título'));
  if (terms.some((term) => entry._summary.includes(term))) sources.push(t('resumen'));
  if (terms.some((term) => entry._author.includes(term))) sources.push(t('autor'));
  if (terms.some((term) => entry._tags.some((tag) => tag.includes(term)))) sources.push(t('etiqueta'));
  return sources.length ? t('Coincidencia en:') + ' ' + sources.join(', ') : '';
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
  return t({
    guide: 'Guía',
    tool: 'Herramienta',
    announcement: 'Anuncio',
    release: 'Versión',
    page: 'Página',
    download: 'Descarga',
    pdf: 'PDF'
  }[kind] || kind);
}

function createSearchState(title, text) {
  const state = document.createElement('div');
  state.className = 'search-state';
  const heading = document.createElement('strong');
  heading.textContent = t(title);
  const copy = document.createElement('p');
  copy.textContent = t(text);
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

  const facts = [entry.date ? new Intl.DateTimeFormat(currentLang(), { dateStyle: 'medium' }).format(new Date(entry.date + 'T12:00:00')) : '', entry.author].filter(Boolean);
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
    section.textContent = t('Ir a:') + ' ' + snippet.heading.title;
    actions.append(section);
  }
  if (entry.pdf && entry.kind !== 'pdf') {
    const pdf = document.createElement('a');
    pdf.href = entry.pdf;
    pdf.target = '_blank';
    pdf.rel = 'noreferrer';
    pdf.textContent = t('Abrir PDF');
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

  count.textContent = t('Buscando…');
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

    count.textContent = countLabel(matches.length, 'resultado', 'resultados');
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

function syncSearch() {
  const input = document.querySelector('#athena-search-input');
  const scope = document.querySelector('#search-scope');
  if (!input || !scope) return;
  const { path, params } = getRouteState();
  const page = document.querySelector('.guide-library, #download-count');
  // Docsify syncs before and after rendering, and again when the language changes.
  if (path !== searchPath || page !== searchPageNode) {
    searchScope = path === '/guides' && document.querySelector('.guide-library') ? 'guide'
      : path === '/downloads' && document.querySelector('#download-count') ? 'download' : '';
    if (path !== '/search') input.value = '';
    searchPath = path;
    searchPageNode = page;
  }
  if (path === '/search') input.value = params.get('q') || '';
  scope.hidden = !searchScope;
  scope.querySelector('span').textContent = t(searchScope === 'guide' ? 'En Guías' : 'En Descargas');
  input.placeholder = t(searchScope === 'guide' ? 'Filtrar guías' : searchScope === 'download' ? 'Filtrar descargas' : 'Buscar en Athena');
  document.querySelector('#athena-search kbd').textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘ K' : 'Ctrl K';
}

// The server and legacy build mark the article's attachment, apart from PDF citations.
function buildPdfViewer() {
  const route = getRouteState().path;
  if (!route.startsWith('/content/') || document.querySelector('.markdown-section .pdf-viewer')) return;
  const src = '/pdf/' + route.slice('/content/'.length).replace(/\.md$/, '') + '.pdf';
  const link = [...document.querySelectorAll('.markdown-section .article-pdf a[href]')]
    .reverse().find((item) => item.getAttribute('href').replace(/^#/, '') === src);
  if (!link) return;
  const viewer = document.createElement('section');
  viewer.className = 'pdf-viewer';
  const actions = document.createElement('p');
  actions.className = 'pdf-viewer__actions';
  [['Descargar PDF', src + '?download=1', ''], ['Abrir en pestaña nueva', src, '_blank']].forEach(([label, href, target]) => {
    const a = document.createElement('a');
    a.className = 'pdf-link';
    a.href = href;
    a.textContent = t(label);
    if (target) {
      a.target = target;
      a.rel = 'noreferrer';
    }
    actions.append(a);
  });
  const frame = document.createElement('iframe');
  frame.src = src;
  frame.title = t('Documento PDF');
  frame.loading = 'lazy';
  viewer.append(actions, frame);
  (link.closest('.article-pdf') || link).replaceWith(viewer);
}

// HTML articles: the server leaves a .html-article marker; the document runs in a sandboxed, opaque-origin frame.
// Only that frame's window may send athena:* messages; the frame never gets same-origin access.
let htmlFrame = null;
let htmlViewportPending = false;

function sendHtmlFrame(type, value) {
  htmlFrame?.contentWindow?.postMessage({ type, value }, '*');
}

function htmlFrameViewport() {
  if (!htmlFrame?.isConnected) return;
  const rect = htmlFrame.getBoundingClientRect();
  const top = Math.max(0, -rect.top);
  const bottom = Math.min(rect.height, window.innerHeight - rect.top);
  sendHtmlFrame('athena:viewport', { top, height: Math.max(0, bottom - top) || window.innerHeight });
}

function queueHtmlViewport() {
  if (htmlViewportPending || !htmlFrame?.isConnected) return;
  htmlViewportPending = true;
  requestAnimationFrame(() => {
    htmlViewportPending = false;
    htmlFrameViewport();
  });
}

function syncHtmlFrame() {
  sendHtmlFrame('athena:theme', document.documentElement.dataset.theme);
  sendHtmlFrame('athena:lang', currentLang());
  htmlFrameViewport();
}

function buildHtmlArticle() {
  const marker = document.querySelector('.markdown-section .html-article[data-src]');
  if (!marker || !marker.dataset.src.startsWith('/article-html/')) return;
  const frame = document.createElement('iframe');
  frame.className = 'html-article-frame';
  frame.setAttribute('sandbox', 'allow-scripts allow-popups allow-popups-to-escape-sandbox');
  frame.title = marker.dataset.title || document.querySelector('.markdown-section h1')?.textContent.trim() || 'Athena';
  frame.dataset.source = marker.dataset.source || '';
  const params = new URLSearchParams({ theme: document.documentElement.dataset.theme || 'light', lang: currentLang() });
  frame.src = marker.dataset.src + '?' + params;
  // Shown on the first height report, or on load if the document never reports.
  frame.addEventListener('load', () => frame.classList.add('is-ready'));
  marker.replaceWith(frame);
  htmlFrame = frame;
}

function focusSearch() {
  const input = document.querySelector('#athena-search-input');
  if (!input) return;
  window.athenaRail?.closeDrawer();
  input.focus();
  input.select();
}

// Image viewer for HTML articles: the article calls window.athena.openImages (article-bridge.js) and Athena shows
// the images in a modal dialog over the whole window. The items come from an untrusted frame: every src must be one
// of Athena's managed images on this origin, and captions are text only.
const VIEWER_SRC = /^\/article-images\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/$/i;
const VIEWER_QUERY = /^(?:\?sig=[\w:-]+)?$/;
const VIEWER_MAX_ITEMS = 50;
const VIEWER_MAX_TEXT = 500;
let viewer = null;

function viewerItems(items) {
  if (!Array.isArray(items) || !items.length || items.length > VIEWER_MAX_ITEMS) return null;
  const text = (value) => typeof value === 'string' ? value.slice(0, VIEWER_MAX_TEXT) : '';
  const clean = [];
  for (const item of items) {
    if (typeof item?.src !== 'string') return null;
    let url;
    try { url = new URL(item.src, location.origin); } catch { return null; }
    if (url.origin !== location.origin || !VIEWER_SRC.test(url.pathname) || !VIEWER_QUERY.test(url.search) || url.hash) return null;
    clean.push({ src: url.pathname + url.search, caption: text(item.caption), alt: text(item.alt) });
  }
  return clean;
}

function buildViewer() {
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className;
    if (text) element.textContent = text;
    return element;
  };
  const icon = (path) => '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="' + path + '"/></svg>';
  const button = (className, label, path, text) => {
    const element = node('button', className);
    element.type = 'button';
    if (label) element.setAttribute('aria-label', label);
    element.innerHTML = icon(path) + (text ? '<span class="image-viewer__label">' + text + '</span>' : '');
    return element;
  };
  // Spanish source strings; AthenaI18n translates them with the rest of the interface.
  const v = {
    dialog: node('dialog', 'image-viewer'),
    counter: node('span', 'image-viewer__counter'),
    size: button('image-viewer__action image-viewer__size', '', 'M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7', 'Tamaño real'),
    original: node('a', 'image-viewer__action image-viewer__original'),
    close: button('image-viewer__close', 'Cerrar', 'M18 6 6 18M6 6l12 12'),
    stage: node('div', 'image-viewer__stage'),
    image: node('img', 'image-viewer__image'),
    error: node('p', 'image-viewer__error', 'No se pudo cargar la imagen. Use Abrir imagen original.'),
    prev: button('image-viewer__step image-viewer__prev', 'Imagen anterior', 'm15 18-6-6 6-6'),
    next: button('image-viewer__step image-viewer__next', 'Imagen siguiente', 'm9 18 6-6-6-6'),
    caption: node('p', 'image-viewer__caption'),
    items: [], index: 0, frame: null, real: false, drag: null, swipe: null, tap: 0, touchToggle: 0
  };
  v.dialog.setAttribute('aria-label', 'Visor de imágenes');
  v.size.setAttribute('aria-pressed', 'false');
  v.original.target = '_blank';
  v.original.rel = 'noopener noreferrer';
  v.original.innerHTML = icon('M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6') + '<span class="image-viewer__label">Abrir imagen original</span>';
  v.image.draggable = false;
  v.image.decoding = 'async';
  v.error.hidden = true;
  v.caption.setAttribute('aria-live', 'polite');
  v.bar = node('div', 'image-viewer__bar');
  v.bar.append(v.counter, v.size, v.original, v.close);
  v.stage.append(v.image, v.error);
  v.foot = node('div', 'image-viewer__foot');
  v.foot.append(v.prev, v.caption, v.next);
  v.dialog.append(v.bar, v.stage, v.foot);
  // The scrim and the image area are always dark; the bar and the foot follow the Athena theme.
  v.dialog.dataset.theme = 'dark';
  document.body.append(v.dialog);

  v.prev.addEventListener('click', () => stepViewer(-1));
  v.next.addEventListener('click', () => stepViewer(1));
  v.close.addEventListener('click', () => v.dialog.close());
  v.size.addEventListener('click', () => setViewerReal(!v.real));
  v.image.addEventListener('load', () => { v.stage.classList.remove('is-loading'); });
  v.image.addEventListener('error', () => { v.stage.classList.remove('is-loading'); v.error.hidden = false; });
  v.dialog.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    stepViewer(event.key === 'ArrowLeft' ? -1 : 1);
  });
  // The dialog fills the window, so a click outside the image lands on the dialog or the stage: the scrim.
  v.dialog.addEventListener('click', (event) => {
    if (v.drag?.moved) return;
    if (event.target === v.dialog || event.target === v.stage) v.dialog.close();
  });
  v.dialog.addEventListener('dblclick', (event) => {
    if (event.target !== v.image || Date.now() - v.touchToggle < 600) return;
    setViewerReal(!v.real, event);
  });
  // Mouse and pen drag pan the real-size image; touch scrolls natively there, and swipes and double-taps in fit mode.
  v.stage.addEventListener('pointerdown', (event) => {
    if (event.pointerType === 'touch') {
      v.swipe = { x: event.clientX, y: event.clientY };
    } else if (v.real && event.button === 0) {
      v.drag = { x: event.clientX, y: event.clientY, left: v.stage.scrollLeft, top: v.stage.scrollTop, moved: false };
      v.stage.setPointerCapture?.(event.pointerId);
      v.stage.classList.add('is-dragging');
    }
  });
  v.stage.addEventListener('pointermove', (event) => {
    if (!v.drag) return;
    const dx = event.clientX - v.drag.x;
    const dy = event.clientY - v.drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) v.drag.moved = true;
    v.stage.scrollLeft = v.drag.left - dx;
    v.stage.scrollTop = v.drag.top - dy;
  });
  const endDrag = () => {
    v.stage.classList.remove('is-dragging');
    // The click that ends a drag must not close the viewer; it runs right after pointerup.
    const drag = v.drag;
    setTimeout(() => { if (v.drag === drag) v.drag = null; }, 0);
  };
  v.stage.addEventListener('pointerup', (event) => {
    if (v.drag) return endDrag();
    if (event.pointerType !== 'touch' || !v.swipe) return;
    const dx = event.clientX - v.swipe.x;
    const dy = event.clientY - v.swipe.y;
    v.swipe = null;
    if (!v.real && Math.abs(dx) >= 50 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      stepViewer(dx < 0 ? 1 : -1);
    } else if (Math.abs(dx) < 10 && Math.abs(dy) < 10 && event.target === v.image) {
      const now = Date.now();
      if (now - v.tap < 320) {
        v.tap = 0;
        v.touchToggle = now;
        setViewerReal(!v.real, event);
      } else v.tap = now;
    }
  });
  v.stage.addEventListener('pointercancel', () => { v.swipe = null; if (v.drag) endDrag(); });
  v.dialog.addEventListener('close', () => {
    const { frame, index } = v;
    setViewerReal(false);
    v.image.removeAttribute('src');
    v.frame = null;
    if (!frame?.isConnected) return;
    frame.focus();
    frame.contentWindow?.postMessage({ type: 'athena:images-closed', index }, '*');
  });
  window.AthenaI18n?.translate();
  return v;
}

function syncViewerTheme() {
  if (!viewer) return;
  const theme = document.documentElement.dataset.theme;
  for (const part of [viewer.bar, viewer.foot]) {
    if (theme) part.dataset.theme = theme;
    else delete part.dataset.theme;
  }
}

function renderViewer() {
  const v = viewer;
  const item = v.items[v.index];
  const many = v.items.length > 1;
  v.stage.classList.add('is-loading');
  v.error.hidden = true;
  v.image.src = item.src;
  v.image.alt = item.alt || item.caption;
  v.original.href = item.src;
  v.caption.textContent = item.caption;
  v.caption.hidden = !item.caption;
  v.counter.textContent = (v.index + 1) + ' / ' + v.items.length;
  v.counter.hidden = v.prev.hidden = v.next.hidden = !many;
  v.foot.hidden = !many && !item.caption;
  v.prev.disabled = v.index === 0;
  v.next.disabled = v.index === v.items.length - 1;
  // A step button that just became disabled would drop focus to the page under the dialog.
  if (document.activeElement?.disabled) (v.prev.disabled ? v.next : v.prev).focus();
  v.stage.scrollLeft = v.stage.scrollTop = 0;
  for (const near of [v.items[v.index - 1], v.items[v.index + 1]]) {
    if (near) document.createElement('img').src = near.src;
  }
}

function stepViewer(delta) {
  const index = Math.min(Math.max(viewer.index + delta, 0), viewer.items.length - 1);
  if (index === viewer.index) return;
  viewer.index = index;
  setViewerReal(false);
  renderViewer();
}

// Real size shows the image at 100% in a scrolling stage; the point under the pointer stays in place.
function setViewerReal(real, point) {
  const v = viewer;
  const rect = point && v.image.getBoundingClientRect?.();
  const ratio = rect?.width ? { x: (point.clientX - rect.left) / rect.width, y: (point.clientY - rect.top) / rect.height } : { x: 0.5, y: 0.5 };
  v.real = real;
  v.dialog.classList.toggle('is-real', real);
  v.size.setAttribute('aria-pressed', String(real));
  if (!real) return;
  const stage = v.stage.getBoundingClientRect?.();
  if (!stage) return;
  const at = point || { clientX: stage.left + stage.width / 2, clientY: stage.top + stage.height / 2 };
  v.stage.scrollLeft = ratio.x * v.image.naturalWidth - (at.clientX - stage.left);
  v.stage.scrollTop = ratio.y * v.image.naturalHeight - (at.clientY - stage.top);
}

function openViewer(frame, items, index) {
  viewer ||= buildViewer();
  viewer.frame = frame;
  viewer.items = items;
  viewer.index = Math.min(Math.max(Math.trunc(Number(index)) || 0, 0), items.length - 1);
  setViewerReal(false);
  syncViewerTheme();
  renderViewer();
  if (!viewer.dialog.open) viewer.dialog.showModal();
  viewer.close.focus();
}

function handleHtmlFrameMessage(event) {
  const frame = htmlFrame;
  if (!frame?.isConnected || event.source !== frame.contentWindow || !event.data || typeof event.data !== 'object') return;
  const { type, value } = event.data;
  if (type === 'athena:height' && Number.isFinite(value) && value >= 0) {
    frame.style.height = Math.min(Math.ceil(value), 100000) + 'px';
    frame.classList.add('is-ready');
    queueHtmlViewport();
  } else if (type === 'athena:ready' || type === 'athena:viewport-request') {
    syncHtmlFrame();
  } else if (type === 'athena:search') {
    focusSearch();
  } else if (type === 'athena:images') {
    const items = viewerItems(event.data.items);
    if (items) openViewer(frame, items, event.data.index);
  } else if (type === 'athena:scroll' && Number.isFinite(value)) {
    const offset = (document.querySelector('.reader-command')?.offsetHeight || 0) + 16;
    window.scrollTo({ top: Math.max(0, window.scrollY + frame.getBoundingClientRect().top + value - offset) });
  }
}

// The server ends an article with one .article-tools marker (Editar artículo, Exportar PDF);
// its links belong beside "Copiar página". The marker is removed, so a later sync does nothing.
function placeArticleTools() {
  const holder = document.querySelector('.markdown-section .article-tools');
  const copy = document.querySelector('.markdown-section .article-actions button.copy-page');
  if (!holder || !copy) return;
  copy.before(...holder.children);
  holder.remove();
}

function syncView() {
  const { path } = getRouteState();
  document.body.classList.toggle('home-view', path === '/');
  document.body.classList.toggle('article-view', path.startsWith('/content/'));
  updateCommand(path);
  buildRail();
  markRail();
  syncSearch();
  filterGuides();
  filterDownloads();
  buildPageTree();
  buildPdfViewer();
  buildHtmlArticle();
  // The viewer belongs to the article frame that opened it.
  if (viewer?.dialog.open && !viewer.frame?.isConnected) viewer.dialog.close();
  placeArticleTools();
  buildTableSorting();
  updateSignInLinks();
  if (path === '/search') renderSearchPage();
  window.AthenaI18n?.translate();
}

function commandLevels(path, name, kind, unavailable = false) {
  const home = { label: 'Athena', href: '#/' };
  const library = { label: 'Biblioteca', href: '#/?id=explorar' };
  if (path === '/') return [home, { label: 'Inicio' }];
  if (path.startsWith('/content/') && !unavailable) {
    const sections = { guide: ['Guías', '#/guides'], tool: ['Herramientas', '#/tools'], announcement: ['Actualizaciones', '#/updates'], release: ['Actualizaciones', '#/updates'] };
    const section = sections[kind];
    return [home, library, ...(section ? [{ label: section[0], href: section[1] }] : []), { label: name, article: true }];
  }
  return [home, ...( ['/guides', '/tools', '/updates', '/downloads'].includes(path) ? [library] : []), { label: name }];
}

function updateCommand(path) {
  const box = document.querySelector('.command-crumbs');
  if (!box) return;
  const pages = { '/': 'Inicio', '/guides': 'Guías', '/tools': 'Herramientas', '/updates': 'Actualizaciones', '/downloads': 'Descargas', '/search': 'Buscar en Athena', '/account': 'Mi cuenta', '/api': 'API para agentes' };
  const heading = document.querySelector('.markdown-section h1');
  const unavailable = Boolean(document.querySelector('.unavailable-page'));
  const article = path.startsWith('/content/') && !unavailable;
  const name = unavailable ? 'Artículo no disponible' : article ? heading?.textContent.trim() || 'Biblioteca' : pages[path] || heading?.textContent.trim() || 'Biblioteca';
  const levels = commandLevels(path, name, document.querySelector('[data-article-kind]')?.dataset.articleKind, unavailable);
  const label = (level) => level.article ? level.label : t(level.label);
  const link = (level) => {
    const node = document.createElement('a');
    node.href = level.href;
    node.textContent = label(level);
    return node;
  };
  const separator = () => {
    const node = document.createElement('span');
    node.textContent = '›';
    node.setAttribute('aria-hidden', 'true');
    return node;
  };
  box.replaceChildren(link(levels[0]), separator());
  const middle = levels.slice(1, -1);
  if (middle.length) {
    const details = document.createElement('details');
    details.className = 'crumb-collapse';
    const summary = document.createElement('summary');
    summary.setAttribute('aria-label', t('Mostrar niveles ocultos'));
    summary.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>';
    const menu = document.createElement('div');
    menu.className = 'crumb-menu';
    menu.append(...middle.map(link));
    details.append(summary, menu);
    const sep = separator();
    sep.className = 'crumb-more-sep';
    box.append(details, sep);
    middle.forEach((level) => {
      const node = link(level), sep = separator();
      node.className = sep.className = 'crumb-middle';
      box.append(node, sep);
    });
  }
  const current = document.createElement('span');
  current.setAttribute('aria-current', 'page');
  if (article) current.dataset.articleTitle = '';
  current.textContent = label(levels.at(-1));
  box.append(current);
  const parent = levels.at(-2), back = document.querySelector('.command-parent');
  back.hidden = !parent;
  if (parent) {
    back.href = parent.href;
    back.querySelector('span').textContent = label(parent);
  }
  document.title = (article ? name : t(name)) + ' · Athena';
  fitCommand();
}

function fitCommand() {
  const bar = document.querySelector('.reader-command');
  const box = document.querySelector('.command-crumbs');
  if (!bar || !box) return;
  bar.classList.remove('is-tight');
  box.classList.remove('is-collapsed');
  if (bar.scrollWidth > bar.clientWidth + 1 || [...box.children].some((node) => node.scrollWidth > node.clientWidth + 1)) {
    box.classList.add('is-collapsed');
    bar.classList.add('is-tight');
  }
}

function updateSignInLinks() {
  document.querySelectorAll('a[href^="/accounts/login/"]').forEach((link) => {
    link.href = '/accounts/login/?next=' + encodeURIComponent('/' + location.hash);
  });
}

document.addEventListener('click', async (event) => {
  if (event.target.closest('.skip-link')) {
    event.preventDefault();
    const main = document.querySelector('div#main');
    // Docsify replaces the shell node, so focusability is set at use time.
    main.tabIndex = -1;
    main.focus({ preventScroll: true });
    main.scrollIntoView({ block: 'start' });
    return;
  }
  if (event.target.closest('#search-scope')) {
    searchScope = '';
    syncSearch();
    filterGuides();
    filterDownloads();
    document.querySelector('#athena-search-input').focus();
  }
  document.querySelectorAll('.crumb-collapse[open]').forEach((menu) => { if (!menu.contains(event.target)) menu.open = false; });
  const topicJump = event.target.closest('[data-guide-topic]');
  if (topicJump) {
    const heading = document.getElementById(topicJump.dataset.guideTopic);
    if (heading) {
      event.preventDefault();
      heading.focus({ preventScroll: true });
      heading.scrollIntoView({ block: 'start' });
    }
  }
  const pageTreeLink = event.target.closest('.page-tree a');
  if (pageTreeLink) {
    updatePageTreeLayout();
    if (pageTreeLink.closest('.page-tree').dataset.layout === 'inline') pageTreeLink.closest('details').open = false;
  }

  const copyButton = event.target.closest('button.copy-page');
  if (!copyButton) return;
  const label = copyButton.querySelector('span');
  try {
    const route = getRouteState().path;
    // An HTML article copies its saved HTML source, not the reader's marker.
    const source = document.querySelector('.markdown-section .html-article-frame')?.dataset.source;
    const response = await fetch(source || (route.endsWith('.md') ? route : route + '.md'));
    if (!response.ok) throw new Error('Article request failed: ' + response.status);
    const text = source ? await response.text() : (await response.text()).replace(/\n*<div class="article-tools">.*<\/div>\n?$/, '\n').replace(/\n*<span class="article-context"[^>]*><\/span>\n?/, '\n');
    await navigator.clipboard.writeText(text);
    copyButton.classList.add('copied');
    label.textContent = t('Copiado');
    setTimeout(() => {
      if (!copyButton.isConnected) return;
      copyButton.classList.remove('copied');
      label.textContent = t('Copiar página');
    }, 2000);
  } catch {
    label.textContent = t('No se pudo copiar');
  }
});

document.addEventListener('submit', (event) => {
  if (!event.target.matches('#athena-search')) return;
  event.preventDefault();
  const query = event.target.querySelector('#athena-search-input').value;
  if (!query.trim()) return;
  const { path } = getRouteState();
  const type = path === '/search' ? document.querySelector('#athena-search-type')?.value || '' : searchScope;
  if (path === '/search') {
    replaceSearchUrl(query, type);
    renderSearchPage();
  } else {
    location.hash = buildSearchHash(query, type);
  }
});

document.addEventListener('input', (event) => {
  if (event.target.matches('#athena-search-input')) {
    filterGuides();
    filterDownloads();
  }
  if (event.target.matches('#athena-search-input') && getRouteState().path === '/search') {
    const type = document.querySelector('#athena-search-type')?.value || '';
    replaceSearchUrl(event.target.value, type);
    renderSearchPage();
  }
});

document.addEventListener('change', (event) => {
  if (event.target.matches('#download-section')) filterDownloads();
  if (event.target.matches('#athena-search-type')) {
    const query = document.querySelector('#athena-search-input')?.value || '';
    replaceSearchUrl(query, event.target.value);
    renderSearchPage();
  }
});

document.addEventListener('keydown', (event) => {
  const input = document.querySelector('#athena-search-input');
  if (!input) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    focusSearch();
  } else if (event.key === 'Escape') {
    document.querySelectorAll('.crumb-collapse[open]').forEach((menu) => { menu.open = false; });
    if (event.target !== input) return;
    event.preventDefault();
    if (input.value) {
      input.value = '';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    } else input.blur();
  }
});

window.athenaSyncView = syncView;
syncView();
document.addEventListener('suite:theme', () => {
  sendHtmlFrame('athena:theme', document.documentElement.dataset.theme);
  syncViewerTheme();
});
document.addEventListener('suite:lang', () => {
  sendHtmlFrame('athena:lang', currentLang());
  syncView();
  document.querySelectorAll('.table-sort').forEach((button) => {
    button.setAttribute('aria-label', sortLabel(button.textContent.trim(), button.closest('th').getAttribute('aria-sort') === 'ascending'));
  });
});
window.addEventListener('load', syncView);
window.addEventListener('hashchange', syncView);
window.addEventListener('scroll', updatePageTreeCurrent, { passive: true });
window.addEventListener('scroll', queueHtmlViewport, { passive: true });
window.addEventListener('resize', queueHtmlViewport);
window.addEventListener('message', handleHtmlFrameMessage);
const reader = document.querySelector('div#main');
if (reader) new ResizeObserver(updatePageTreeLayout).observe(reader);

const commandBar = document.querySelector('.reader-command');
if (commandBar) {
  new ResizeObserver(fitCommand).observe(commandBar);
  document.fonts.ready.then(fitCommand);
}
