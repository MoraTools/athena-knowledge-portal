// Reader side of HTML articles: the sandboxed frame, and which messages it accepts.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const documentHandlers = {};
const windowHandlers = {};
const queries = {};
let input;
const root = { dataset: { theme: 'dark' }, lang: 'es' };
const scrolls = [];
const fetched = [];
const timers = [];
const cleared = [];
let statusAnswer = async () => ({ ok: true, json: async () => ({}) });

function frameWindow() {
  return { messages: [], postMessage(message, target) { this.messages.push({ ...message, target }); } };
}
function fakeElement(tag) {
  const element = {
    tagName: tag, attributes: {}, dataset: {}, style: {}, listeners: {}, children: [], isConnected: false, hidden: false,
    textContent: '', innerHTML: '', scrollLeft: 0, scrollTop: 0, naturalWidth: 1440, naturalHeight: 900, open: false,
    classList: {
      values: new Set(), add(value) { this.values.add(value); }, remove(value) { this.values.delete(value); },
      contains(value) { return this.values.has(value); },
      toggle(value, force) { if (force ?? !this.values.has(value)) this.values.add(value); else this.values.delete(value); }
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] ?? null; },
    removeAttribute(name) { delete this.attributes[name]; if (name === 'src') delete this.src; },
    addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); },
    dispatch(type, event = {}) { for (const handler of this.listeners[type] || []) handler({ target: this, preventDefault() { this.prevented = true; }, ...event }); },
    append(...nodes) { this.children.push(...nodes); },
    querySelector(selector) { for (const child of this.children) { if (child.tagName === selector) return child; const found = child.querySelector?.(selector); if (found) return found; } return null; },
    remove() { if (queries['.page-tree'] === this) delete queries['.page-tree']; },
    focus() { activeElement = this; },
    showModal() { this.open = true; },
    close() { if (!this.open) return; this.open = false; this.dispatch('close'); },
    getBoundingClientRect: () => element.rect || { top: -300, height: 4000 }
  };
  created.push(element);
  return element;
}
let activeElement = null;
const bodyNodes = [];
const created = [];

const context = vm.createContext({
  URL, URLSearchParams, console, Intl,
  location: { hash: '#/content/demos', href: 'https://athena.test/#/content/demos', origin: 'https://athena.test' },
  history: { state: null, replaceState() {} },
  matchMedia: () => ({ matches: false }),
  ResizeObserver: class { observe() {} },
  navigator: { platform: 'Linux', clipboard: { writeText() {} } },
  setTimeout() {}, clearTimeout() {},
  fetch(url) { fetched.push(url); return statusAnswer(); },
  setInterval(callback, delay) { timers.push({ callback, delay }); return timers.length; },
  clearInterval(id) { cleared.push(id); },
  requestAnimationFrame(callback) { callback(); },
  getComputedStyle: () => ({ position: 'static' }),
  innerHeight: 900,
  scrollY: 500,
  scrollTo(options) { scrolls.push(options); },
  document: {
    documentElement: root,
    fonts: { ready: { then() {} } },
    addEventListener(type, handler) { documentHandlers[type] = handler; },
    querySelector: selector => queries[selector] ?? null,
    querySelectorAll: () => [],
    createElement: fakeElement,
    get activeElement() { return activeElement; },
    body: { classList: { add() {}, remove() {}, toggle() {} }, append(node) { node.isConnected = true; bodyNodes.push(node); } }
  }
});
context.window = context;
context.addEventListener = (type, handler) => { windowHandlers[type] = handler; };
vm.runInContext(readFileSync(new URL('../src/app.js', import.meta.url), 'utf8'), context);

// The marker becomes a sandboxed frame without same-origin access, loaded with the current theme and language.
let frame;
const marker = {
  dataset: { src: '/article-html/demos/', source: '/article-html/demos/source', title: 'Demos en vivo' },
  replaceWith(node) { frame = node; node.isConnected = true; node.contentWindow = frameWindow(); }
};
queries['.markdown-section .html-article[data-src]'] = marker;
context.buildHtmlArticle();
delete queries['.markdown-section .html-article[data-src]'];  // replaceWith removed the marker.
assert.equal(frame.tagName, 'iframe');
assert.equal(frame.attributes.sandbox, 'allow-scripts allow-popups allow-popups-to-escape-sandbox');
assert.ok(!frame.attributes.sandbox.includes('allow-same-origin'));
assert.equal(frame.src, '/article-html/demos/?theme=dark&lang=es');
assert.equal(frame.title, 'Demos en vivo');
assert.equal(frame.dataset.source, '/article-html/demos/source');
assert.equal(frame.classList.contains('is-ready'), false, 'The frame stays hidden until it reports its height.');

// Only this frame's window may resize the frame or move focus; values are checked.
const message = windowHandlers.message;
assert.equal(typeof message, 'function');
const other = frameWindow();
message({ source: other, data: { type: 'athena:height', value: 1200 } });
assert.equal(frame.style.height, undefined);
message({ source: frame.contentWindow, data: { type: 'athena:height', value: -5 } });
message({ source: frame.contentWindow, data: { type: 'athena:height', value: 'big' } });
message({ source: frame.contentWindow, data: null });
assert.equal(frame.style.height, undefined);
message({ source: frame.contentWindow, data: { type: 'athena:height', value: 3359.4 } });
assert.equal(frame.style.height, '3360px');
assert.equal(frame.classList.contains('is-ready'), true);
message({ source: frame.contentWindow, data: { type: 'athena:height', value: 5e9 } });
assert.equal(frame.style.height, '100000px');

// Ready: theme, language, and the visible part of the frame for its dialogs.
frame.contentWindow.messages.length = 0;
message({ source: frame.contentWindow, data: { type: 'athena:ready' } });
assert.equal(JSON.stringify(frame.contentWindow.messages), JSON.stringify([
  { type: 'athena:theme', value: 'dark', target: '*' },
  { type: 'athena:lang', value: 'es', target: '*' },
  { type: 'athena:viewport', value: { top: 300, height: 900 }, target: '*' }
]));
message({ source: other, data: { type: 'athena:ready' } });
assert.equal(frame.contentWindow.messages.length, 3, 'Another window cannot ask for the reader state.');

// Theme and language toggles reach the frame.
frame.contentWindow.messages.length = 0;
root.dataset.theme = 'light';
documentHandlers['suite:theme']();
root.lang = 'en';
documentHandlers['suite:lang']();
assert.equal(JSON.stringify(frame.contentWindow.messages.slice(0, 2)), JSON.stringify([
  { type: 'athena:theme', value: 'light', target: '*' },
  { type: 'athena:lang', value: 'en', target: '*' }
]));

// Ctrl K inside the frame opens the Athena search; in-page links scroll the reader.
input = { focused: false, focus() { this.focused = true; }, select() {} };
queries['#athena-search-input'] = input;
message({ source: other, data: { type: 'athena:search' } });
assert.equal(input.focused, false);
message({ source: frame.contentWindow, data: { type: 'athena:search' } });
assert.equal(input.focused, true);
queries['.reader-command'] = { offsetHeight: 56 };
message({ source: frame.contentWindow, data: { type: 'athena:scroll', value: 1000 } });
assert.equal(JSON.stringify(scrolls), JSON.stringify([{ top: 500 - 300 + 1000 - 72 }]));

// Image viewer: athena:images opens a full-window modal dialog; only valid managed images from this frame.
const id = n => `00000000-0000-4000-8000-00000000000${n}`;
const item = (n, extra = {}) => ({ src: `/article-images/${id(n)}/`, caption: `Captura ${n}`, alt: `Alt ${n}`, ...extra });
const items = [item(1), item(2, { src: `https://athena.test/article-images/${id(2)}/?sig=1a2b:c3-d_4` }), item(3)];
const images = data => message({ source: frame.contentWindow, data: { type: 'athena:images', ...data } });
message({ source: other, data: { type: 'athena:images', items, index: 0 } });
assert.equal(bodyNodes.length, 0, 'Another window cannot open the viewer.');
for (const bad of [
  [item(1, { src: 'https://evil.test/article-images/' + id(1) + '/' })],
  [item(1, { src: '/article-images/' + id(1) + '/../../admin/' })],
  [item(1, { src: '/content/demos.md' })],
  [item(1, { src: 'javascript:alert(1)' })],
  [item(1, { src: '//evil.test/article-images/' + id(1) + '/' })],
  [item(1, { src: '/article-images/' + id(1) + '/?sig=x&next=1' })],
  [item(1, { src: '/article-images/' + id(1) + '/#x' })],
  [item(1, { src: 5 })], [null], [], 'items',
  [item(1), item(2, { src: 'data:image/png;base64,AAAA' })],
  Array.from({ length: 51 }, () => item(1))
]) images({ items: bad, index: 0 });
assert.equal(bodyNodes.length, 0, 'Bad sources, empty lists and more than 50 items are rejected.');

images({ items: [...items.slice(0, 2), item(3, { caption: '<b>x</b>'.padEnd(900, 'y'), alt: 'a'.repeat(900) })], index: 7 });
const dialog = bodyNodes[0];
const parts = {};
(function walk(node) { for (const name of String(node.className).split(' ')) parts[name] ||= node; node.children.forEach(walk); })(dialog);
const { 'image-viewer__image': image, 'image-viewer__counter': counter, 'image-viewer__caption': caption,
  'image-viewer__prev': prev, 'image-viewer__next': next, 'image-viewer__size': size, 'image-viewer__original': original,
  'image-viewer__close': close, 'image-viewer__stage': stage } = parts;
assert.equal(dialog.tagName, 'dialog');
assert.equal(dialog.open, true);
assert.equal(dialog.dataset.theme, 'dark');
assert.equal(activeElement, close, 'Focus starts on the close button.');
assert.equal(counter.textContent, '3 / 3', 'The index is clamped.');
assert.equal(image.src, `/article-images/${id(3)}/`);
assert.equal(caption.textContent.length, 500, 'Captions are cut to 500 characters.');
assert.ok(caption.textContent.startsWith('<b>x</b>'), 'The caption is text, never HTML.');
assert.equal(caption.innerHTML, '');
assert.equal(image.alt.length, 500);
assert.equal(original.href, image.src);
assert.equal(original.target, '_blank');
assert.equal(next.disabled, true);
const preloads = () => created.filter(node => node.tagName === 'img' && node !== image).map(node => node.src);
assert.ok(preloads().includes(`/article-images/${id(2)}/?sig=1a2b:c3-d_4`), 'The previous image is preloaded; the signature is kept.');

// Previous and next buttons, arrow keys; no step past the ends.
prev.dispatch('click');
assert.equal(counter.textContent, '2 / 3');
assert.equal(image.src, `/article-images/${id(2)}/?sig=1a2b:c3-d_4`);
dialog.dispatch('keydown', { key: 'ArrowLeft' });
assert.equal(counter.textContent, '1 / 3');
assert.equal(prev.disabled, true);
assert.ok(preloads().includes(`/article-images/${id(2)}/?sig=1a2b:c3-d_4`));
dialog.dispatch('keydown', { key: 'ArrowLeft' });
assert.equal(counter.textContent, '1 / 3');
dialog.dispatch('keydown', { key: 'ArrowRight' });
next.dispatch('click');
assert.equal(counter.textContent, '3 / 3');
dialog.dispatch('keydown', { key: 'ArrowLeft' });
assert.equal(counter.textContent, '2 / 3');

// Real size: toggle button and double-click, back to fit; the double-clicked point stays under the pointer.
size.dispatch('click');
assert.equal(dialog.classList.contains('is-real'), true);
assert.equal(size.attributes['aria-pressed'], 'true');
size.dispatch('click');
assert.equal(dialog.classList.contains('is-real'), false);
assert.equal(size.attributes['aria-pressed'], 'false');
image.rect = { left: 100, top: 100, width: 720, height: 450 };
stage.rect = { left: 0, top: 50, width: 1000, height: 700 };
dialog.dispatch('dblclick', { target: image, clientX: 460, clientY: 325 });
assert.equal(dialog.classList.contains('is-real'), true);
assert.equal(stage.scrollLeft, 0.5 * 1440 - 460);
assert.equal(stage.scrollTop, 0.5 * 900 - 275);
// Touch swipe goes to the next image only in fit mode; a step returns to fit.
stage.dispatch('pointerdown', { pointerType: 'touch', clientX: 300, clientY: 300 });
stage.dispatch('pointerup', { pointerType: 'touch', clientX: 100, clientY: 310, target: stage });
assert.equal(counter.textContent, '2 / 3', 'No swipe step in real size.');
dialog.dispatch('dblclick', { target: image });
assert.equal(dialog.classList.contains('is-real'), false);
stage.dispatch('pointerdown', { pointerType: 'touch', clientX: 300, clientY: 300 });
stage.dispatch('pointerup', { pointerType: 'touch', clientX: 100, clientY: 310, target: stage });
assert.equal(counter.textContent, '3 / 3');
stage.dispatch('pointerdown', { pointerType: 'touch', clientX: 100, clientY: 300 });
stage.dispatch('pointerup', { pointerType: 'touch', clientX: 300, clientY: 290, target: stage });
assert.equal(counter.textContent, '2 / 3');
// A click on the image does not close; Escape (the dialog's native cancel) and the scrim do.
dialog.dispatch('click', { target: image });
assert.equal(dialog.open, true);
frame.focus = function () { activeElement = this; };
frame.contentWindow.messages.length = 0;
dialog.close();
assert.equal(dialog.open, false);
assert.equal(activeElement, frame, 'Focus returns to the article frame.');
assert.equal(JSON.stringify(frame.contentWindow.messages), JSON.stringify([{ type: 'athena:images-closed', index: 1, target: '*' }]));
assert.equal(image.src, undefined);

// The dialog is built once; a second open reuses it, and a scrim click closes.
images({ items: [item(4)], index: -3 });
assert.equal(bodyNodes.length, 1);
assert.equal(counter.textContent, '1 / 1');
assert.equal(prev.hidden && next.hidden && counter.hidden, true, 'One image: no paging.');
assert.equal(dialog.classList.contains('is-real'), false);
dialog.dispatch('click', { target: stage });
assert.equal(dialog.open, false);
assert.equal(frame.contentWindow.messages.at(-1).index, 0);

// Page tree ("En esta página") from the frame's athena:outline: same component as Markdown, validated items only.
const title = { id: 'demos-en-vivo', textContent: ' Demos en vivo ', rect: { top: -400 }, attributes: {},
  getBoundingClientRect() { return this.rect; }, hasAttribute(name) { return name in this.attributes; },
  setAttribute(name, value) { this.attributes[name] = value; }, focus() { activeElement = this; } };
const article = {
  querySelector: selector => selector === '.unavailable-page' ? null : selector === '.html-article, .html-article-frame' ? frame : selector === 'h1[id]' ? title : null,
  before(node) { node.isConnected = true; queries['.page-tree'] = node; }
};
queries['.markdown-section'] = article;
const tree = () => queries['.page-tree'];
const links = () => tree().querySelector('ol').children.map(li => ({ level: li.className, text: li.children[0].textContent, href: li.children[0].href, current: li.children[0].attributes['aria-current'] ?? null }));
const outline = items => message({ source: frame.contentWindow, data: { type: 'athena:outline', items } });
const heading = (id, text, level, top) => ({ id, text, level, top });
frame.rect = { top: -300, height: 4000 };
message({ source: other, data: { type: 'athena:outline', items: [heading('uno', 'Uno', 1, 0)] } });
assert.equal(tree(), undefined, 'Another window cannot draw the tree.');
outline([
  heading('uno', '  Uno  ', 1, 0), heading('dos', 'Dos', 2, 400), heading('tres', 'Tres '.repeat(80), 1, 900),
  heading('1bad', 'Id starts with a digit', 1, 10), heading('a b', 'Space in id', 1, 10), heading('x'.repeat(129), 'Long id', 1, 10),
  heading('nivel', 'Level 3', 3, 10), heading('nivel0', 'Level 0', 0, 10), heading('arriba', 'Negative top', 1, -1),
  heading('inf', 'Infinite top', 1, Infinity), heading('texto', 5, 1, 10), heading('vacio', '   ', 1, 10), null, 'x',
  { id: 'html', text: '<img src=x onerror=alert(1)>', level: 1, top: 1000 }
]);
assert.equal(tree().className, 'page-tree');
assert.equal(tree().attributes['aria-label'], 'En esta página');
assert.equal(tree().children[0].tagName, 'details');
assert.equal(tree().children[0].children[0].tagName, 'summary');
assert.equal(tree().children[0].children[0].textContent, 'En esta página');
assert.equal(tree().dataset.layout, 'inline', 'Below 900px the tree is the closed box above the article.');
assert.deepEqual(links().map(({ level, text }) => [level, text]), [
  ['page-tree__level-1', 'Demos en vivo'], ['page-tree__level-2', 'Uno'], ['page-tree__level-3', 'Dos'],
  ['page-tree__level-2', ('Tres '.repeat(80)).trim().slice(0, 200)], ['page-tree__level-2', '<img src=x onerror=alert(1)>']
]);
assert.equal(links()[1].href, '#/content/demos?id=uno');
assert.ok(tree().querySelector('ol').children.every(li => li.children[0].innerHTML === ''), 'Tree text is textContent only.');

// Current link: frame top plus item top, the Markdown rule (the last heading at or above 120px).
assert.equal(links().find(link => link.current)?.text, 'Dos', '-300 + 400 = 100');
frame.rect = { top: -790, height: 4000 };
context.updatePageTreeCurrent();
assert.equal(links().find(link => link.current)?.text.slice(0, 4), 'Tres', '-790 + 900 = 110, no frame round trip');
frame.rect = { top: 100, height: 4000 };
context.updatePageTreeCurrent();
assert.equal(links().find(link => link.current)?.text, 'Uno', 'The title is above, Uno at 100.');
// New tops alone keep the tree and move the current link.
const firstTree = tree();
outline([heading('uno', 'Uno', 1, 0), heading('dos', 'Dos', 2, 10), heading('tres', 'Tres '.repeat(80), 1, 900), { id: 'html', text: '<img src=x onerror=alert(1)>', level: 1, top: 1000 }]);
assert.equal(tree(), firstTree);
assert.equal(links().find(link => link.current)?.text, 'Dos', '100 + 10 = 110');

// Click: scroll the reader to the heading below the command bar, then focus it in the frame; the route stays.
const clickLink = (index, extra = {}) => {
  const link = tree().querySelector('ol').children[index].children[0];
  link.closest = selector => selector === '.page-tree' ? tree() : tree().children[0];
  const event = { target: { closest: selector => selector === '.page-tree a' ? link : null }, button: 0, preventDefault() { this.prevented = true; }, ...extra };
  documentHandlers.click(event);
  return event;
};
scrolls.length = 0;
frame.contentWindow.messages.length = 0;
tree().children[0].open = true;
const hash = context.location.hash;
assert.equal(clickLink(3).prevented, true);
assert.equal(JSON.stringify(scrolls), JSON.stringify([{ top: 500 + 100 + 900 - 72 }]));
assert.equal(JSON.stringify(frame.contentWindow.messages), JSON.stringify([{ type: 'athena:focus', value: 'tres', target: '*' }]));
assert.equal(context.location.hash, hash);
assert.equal(tree().children[0].open, false, 'The inline box closes after a choice.');
assert.equal(clickLink(0).prevented, true, 'The title link scrolls to the reader title.');
assert.equal(scrolls.at(-1).top, 500 - 400 - 72);
assert.equal(activeElement, title);
assert.equal(title.attributes.tabindex, '-1');
assert.equal(clickLink(2, { ctrlKey: true }).prevented, undefined, 'A modified click keeps the browser behavior.');

// Mutation in the frame (for example the language switch) sends new text: the tree is rebuilt with it.
outline([heading('uno', 'One', 1, 0), heading('dos', 'Two', 2, 10)]);
assert.notEqual(tree(), firstTree);
assert.deepEqual(links().map(({ text }) => text), ['Demos en vivo', 'One', 'Two']);
// At most 100 items.
outline(Array.from({ length: 150 }, (_, n) => heading('h' + n, 'H ' + n, 1, n * 10)));
assert.equal(links().length, 101);
assert.equal(links().at(-1).text, 'H 99');
// Empty list (or the opt-out meta): no tree, no empty column.
outline([]);
assert.equal(tree(), undefined);
outline('nope');
assert.equal(tree(), undefined);
delete queries['.markdown-section'];

// Live status: asked for when this frame is ready, validated, posted only to the frame window, asked again every 5 minutes.
{
  const tick = () => new Promise(resolve => setImmediate(resolve));
  const ready = source => message({ source, data: { type: 'athena:ready' } });
  const posts = () => frame.contentWindow.messages.filter(data => data.type === 'athena:status');
  const checked_at = '2026-11-11T15:00:00+00:00';
  await tick();
  assert.equal(frame.dataset.status, '/article-status/demos/');
  assert.equal(posts().length, 0, 'An article with no marked links gets no status message.');
  fetched.length = 0;
  frame.contentWindow.messages.length = 0;
  other.messages.length = 0;
  statusAnswer = async () => ({ ok: true, json: async () => ({
    'https://demo.test/': { state: 'online', checked_at, extra: 'dropped' },
    'http://off.test/x': { state: 'offline', checked_at },
    'javascript:alert(1)': { state: 'online', checked_at },
    'https://unknown.test/': { state: 'maybe', checked_at },
    'https://undated.test/': { state: 'online', checked_at: 'yesterday' },
    'https://null.test/': null
  }) });
  ready(other);
  message({ source: frame.contentWindow, data: { type: 'athena:viewport-request' } });
  await tick();
  assert.equal(fetched.length, 0, 'Only athena:ready from this frame starts the status.');
  const timersBefore = timers.length;
  ready(frame.contentWindow);
  await tick();
  assert.deepEqual(fetched, ['/article-status/demos/']);
  assert.equal(JSON.stringify(posts()), JSON.stringify([{ type: 'athena:status', items: {
    'https://demo.test/': { state: 'online', checked_at }, 'http://off.test/x': { state: 'offline', checked_at }
  }, target: '*' }]));
  assert.equal(other.messages.length, 0, 'Another window never gets the status.');
  assert.equal(timers.length, timersBefore + 1);
  assert.equal(timers.at(-1).delay, 5 * 60 * 1000);
  assert.ok(cleared.includes(timersBefore), 'A new ready replaces the earlier timer.');
  timers.at(-1).callback();
  await tick();
  assert.equal(fetched.length, 2);
  assert.equal(posts().length, 2, 'The timer asks and posts again.');
  // More than 20 items, a list, a server error or no network: nothing is posted.
  for (const answer of [
    async () => ({ ok: true, json: async () => Object.fromEntries(Array.from({ length: 30 }, (_, n) => [`https://d${n}.test/`, { state: 'online', checked_at }])) }),
    async () => ({ ok: true, json: async () => [{ state: 'online', checked_at }] }),
    async () => ({ ok: false, json: async () => ({ 'https://demo.test/': { state: 'online', checked_at } }) }),
    async () => { throw new TypeError('network'); }
  ]) {
    statusAnswer = answer;
    timers.at(-1).callback();
    await tick();
  }
  assert.equal(posts().length, 3);
  assert.equal(Object.keys(posts().at(-1).items).length, 20);
  // A removed frame stops its timer and asks for nothing.
  const asked = fetched.length;
  frame.isConnected = false;
  timers.at(-1).callback();
  await tick();
  assert.equal(fetched.length, asked);
  assert.equal(cleared.at(-1), timers.length);
  frame.isConnected = true;
  statusAnswer = async () => ({ ok: true, json: async () => ({}) });
}

// A removed frame accepts nothing; a marker for another route is ignored.
frame.isConnected = false;
message({ source: frame.contentWindow, data: { type: 'athena:height', value: 10 } });
assert.equal(frame.style.height, '100000px');
const previous = frame;
queries['.markdown-section .html-article[data-src]'] = { ...marker, dataset: { src: 'https://example.test/' } };
context.buildHtmlArticle();
assert.equal(frame, previous);

// The bridge in the frame: athena:outline from h2[id] and h3[id], one message per animation frame, opt-out meta, focus.
{
  const posted = [];
  const events = [];
  const frames = [];
  const listeners = {};
  let mutation;
  let meta = null;
  let focused = null;
  const head = (tagName, id, text, top) => ({
    tagName, id, textContent: text, attributes: {}, top,
    getBoundingClientRect() { return { top: this.top - bridgeWindow.scrollY }; },
    matches(selector) { return selector === 'h2, h3' && /^H[23]$/.test(this.tagName); },
    hasAttribute(name) { return name in this.attributes; }, setAttribute(name, value) { this.attributes[name] = value; },
    focus(options) { focused = { id: this.id, options }; }
  });
  let headings = [head('H2', 'resumen', ' Resumen\n  general ', 300), head('H3', 'detalle', 'Detalle', 900.4)];
  const paragraph = { ...head('P', 'nota', 'Nota', 50), matches: () => false };
  const bridgeWindow = {
    scrollY: 0, location: { search: '?theme=dark&lang=es' }, URLSearchParams, CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
    parent: { postMessage(data) { posted.push(JSON.parse(JSON.stringify(data))); } },
    requestAnimationFrame(callback) { frames.push(callback); },
    ResizeObserver: class { constructor(callback) { this.callback = callback; } observe() {} },
    MutationObserver: class { constructor(callback) { mutation = callback; } observe(node, options) { this.options = options; } },
    addEventListener(type, handler) { listeners[type] = handler; },
    document: {
      documentElement: { dataset: {}, getBoundingClientRect: () => ({ height: 1000 }) },
      querySelector: selector => selector === 'meta[name="athena-outline"]' ? meta : null,
      querySelectorAll: selector => selector === 'h2[id], h3[id]' ? headings : [],
      getElementById: id => [...headings, paragraph].find(node => node.id === id) || null,
      addEventListener() {}, dispatchEvent(event) { events.push(event); }
    }
  };
  bridgeWindow.window = bridgeWindow;
  vm.runInNewContext(readFileSync(new URL('../server/athena/static/athena/article-bridge.js', import.meta.url), 'utf8'), bridgeWindow);
  const outlines = () => posted.filter(data => data.type === 'athena:outline');
  const flush = () => { while (frames.length) frames.shift()(); };
  assert.equal(outlines().length, 0, 'The outline waits for the animation frame.');
  flush();
  assert.deepEqual(outlines(), [{ type: 'athena:outline', items: [
    { id: 'resumen', text: 'Resumen general', level: 1, top: 300 }, { id: 'detalle', text: 'Detalle', level: 2, top: 900 }
  ] }]);
  assert.deepEqual(new Set(posted.map(data => data.type)), new Set(['athena:ready', 'athena:outline']));
  // Many mutations in one frame: one message; nothing changed: no message.
  mutation(); mutation(); mutation();
  assert.equal(frames.length, 1);
  flush();
  assert.equal(outlines().length, 1, 'An unchanged outline is not sent again.');
  headings[0].textContent = 'Summary';
  mutation(); mutation();
  flush();
  assert.equal(outlines().length, 2);
  assert.equal(outlines().at(-1).items[0].text, 'Summary');
  // Positions are relative to the frame document, not to its scroll.
  bridgeWindow.scrollY = 200;
  headings = [...headings, head('H2', 'nuevo', 'Nuevo', 1500)];
  mutation(); flush();
  assert.deepEqual(outlines().at(-1).items.map(item => [item.id, item.top]), [['resumen', 300], ['detalle', 900], ['nuevo', 1500]]);
  // Opt-out meta: an empty list.
  meta = { getAttribute: () => ' OFF ' };
  mutation(); flush();
  assert.deepEqual(outlines().at(-1).items, []);
  // athena:focus: only from the parent, only h2/h3, tabindex -1 when missing, no scroll.
  const send = (source, data) => listeners.message({ source, data });
  send({}, { type: 'athena:focus', value: 'detalle' });
  assert.equal(focused, null);
  send(bridgeWindow.parent, { type: 'athena:focus', value: 'nota' });
  send(bridgeWindow.parent, { type: 'athena:focus', value: 7 });
  send(bridgeWindow.parent, { type: 'athena:focus', value: 'missing' });
  assert.equal(focused, null);
  send(bridgeWindow.parent, { type: 'athena:focus', value: 'detalle' });
  assert.equal(focused.id, 'detalle');
  assert.equal(focused.options.preventScroll, true);
  assert.equal(headings[1].attributes.tabindex, '-1');
  // athena:status: only from the parent, as the document event athena:status; nothing goes back to the parent.
  const items = { 'https://demo.test/': { state: 'online', checked_at: '2026-11-11T15:00:00+00:00' } };
  const sent = posted.length;
  events.length = 0;
  send({}, { type: 'athena:status', items });
  send(bridgeWindow.parent, { type: 'athena:status', items: 'online' });
  send(bridgeWindow.parent, { type: 'athena:status' });
  assert.equal(events.length, 0);
  send(bridgeWindow.parent, { type: 'athena:status', items });
  assert.deepEqual(events.map(event => [event.type, event.detail]), [['athena:status', items]]);
  assert.equal(posted.length, sent);
}

console.log('HTML article frame sandbox, URL, height source checks, theme/lang/viewport messages, Ctrl K, in-page scroll, image viewer, page tree, live status and bridge outline passed.');
