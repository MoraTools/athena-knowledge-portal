import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const handlers = {};
const context = vm.createContext({
  URL,
  URLSearchParams,
  console,
  location: { hash: '#/', href: 'https://athena.moratechnology.com/#/' },
  history: { state: null, replaceState(_state, _title, url) {
    context.location.href = url.href;
    context.location.hash = url.hash;
  } },
  matchMedia: () => ({ matches: false }),
  navigator: { clipboard: { writeText() {} } },
  setTimeout() {},
  document: {
    addEventListener(name, handler) { handlers[name] = handler; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    body: {
      append() {},
      classList: { add() {}, remove() {}, toggle() {} }
    }
  },
  window: { addEventListener() {} }
});

vm.runInContext(readFileSync(new URL('../src/app.js', import.meta.url), 'utf8'), context);

const duplicateIds = context.docsifyHeadingIds('Repeated', [
  { level: 4, title: 'Detail', text: '' },
  { level: 2, title: 'Repeated', text: '' },
  { level: 3, title: 'Detail', text: '' }
]);
assert.equal(duplicateIds.map(({ level, id }) => level + ':' + id).join(','), '2:repeated-1,3:detail-1');

const filler = 'relleno '.repeat(60);
const fold = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const excerptEntry = context.prepareSearchEntry({
  kind: 'guide',
  title: 'Ejemplo',
  summary: 'Resumen breve',
  author: 'Test',
  tags: ['Solución de problemas'],
  text: 'de ' + filler + 'problemas importantes y solución comprobada',
  headings: [{ level: 2, title: 'Introducción', text: 'de ' + filler }]
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
  headings: [{ level: 2, title: 'Solución', text: 'de detalles adicionales' }]
});
const headingExcerpt = context.findSnippet(headingEntry, context.searchTerms('Solución de problemas'));
assert.match(fold(headingExcerpt.text), /solucion/);

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

const schema = JSON.parse(readFileSync(new URL('../server/openapi.json', import.meta.url), 'utf8'));
const [apiMajor, apiMinor] = schema.info.version.split('.').map(Number);
assert.ok(apiMajor > 1 || (apiMajor === 1 && apiMinor >= 6), 'The API must not regress below its existing 1.6.0 version.');
assert.equal(schema.components.schemas.ArticleInput.properties.is_public.type, 'boolean');
assert.ok(schema.components.schemas.ArticleImage.properties.content_type.enum.includes('image/gif'));
assert.ok(schema.paths['/article-images/{id}/'].get.responses['200'].content['image/gif']);

// An unavailable article is not a document outline; its heading is nested inside a section.
vm.runInContext(`
  location.hash = '#/content/private';
  document.querySelector = (selector) => selector === '.markdown-section'
    ? { querySelector: () => ({}) }
    : null;
  buildPageTree();
`, context);
console.log('Search, sign-in return targets, API version and unavailable-page checks passed.');
