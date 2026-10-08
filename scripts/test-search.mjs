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
  get rows() { return this.childNodes.filter((child) => child.tagName === 'TR'); }
  get cells() { return this.childNodes.filter((child) => ['TD', 'TH'].includes(child.tagName)); }
  setAttribute(name, value) { this.attributes.set(name, value); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  append(...children) {
    children.forEach((child) => {
      if (child.parentElement) child.parentElement.childNodes = child.parentElement.childNodes.filter((node) => node !== child);
      child.parentElement = this;
      this.childNodes.push(child);
    });
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
  addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
  click() { (this.listeners.click || []).forEach((handler) => handler({ target: this })); }
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
const footer = table(['Nombre'], [['2'], ['1']]);
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
const offsetDates = table(['Fecha'], [['01/01/2027'], ['01/01/2027']]);
offsetDates.tBodies[0].rows[0].cells[0].dataset.sortValue = '2027-01-01T01:00:00-05:00';
const earlierTime = new Element('time', '01/01/2027');
earlierTime.setAttribute('datetime', '2027-01-01T03:00:00+02:00');
offsetDates.tBodies[0].rows[1].cells[0].append(earlierTime);
const earlierRow = offsetDates.tBodies[0].rows[1];
const proseTable = table(['Method', 'Path', 'Result'], [['GET', '/me/', 'The current account, its key, expiry date, and the full set of allowed API operations.']]);
let tables = [records, emptyTable, footer, offsetDates, proseTable, ...skipped];
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
assert.deepEqual(proseTable.tHead.rows[0].cells.map((cell) => cell.dataset.longText), [undefined, undefined, 'true']);
assert.ok(columns.every((header) => !header.dataset.longText), 'Short account columns keep their natural width.');
const order = () => records.tBodies[0].rows.map((row) => originalRows.indexOf(row)).join(',');
context.document.activeElement = buttons[0];
buttons[0].click();
assert.equal(order(), '1,2,3,0', 'Names use Spanish, accent-insensitive and numeric-aware comparison.');
assert.equal(columns[0].getAttribute('aria-sort'), 'ascending');
assert.match(buttons[0].getAttribute('aria-label'), /descendente$/);
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
emptyTable.tHead.rows[0].cells[0].querySelector('button').click();
assert.equal(emptyTable.tBodies[0].rows.length, 0);
footer.tHead.rows[0].cells[0].querySelector('button').click();
assert.equal(footer.tBodies[0].rows[0].textContent, '1');
assert.equal(footer.tFoot.rows[0], footerSummary, 'Sorting only moves tbody rows and keeps the footer fixed.');
const dateButton = offsetDates.tHead.rows[0].cells[0].querySelector('button');
dateButton.click();
assert.equal(offsetDates.tBodies[0].rows[0], earlierRow, 'ISO machine dates compare their time values across offsets.');
dateButton.click();
assert.equal(offsetDates.tBodies[0].rows[1], earlierRow);
tables = [table(['New render'], [['2'], ['1']])];
context.syncView();
tables[0].tHead.rows[0].cells[0].querySelector('button').click();
assert.equal(tables[0].tBodies[0].rows[0].textContent, '1', 'A new Docsify render initializes independently.');

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
console.log('Search, sign-in, API version, reader sorting and live directory query checks passed.');
