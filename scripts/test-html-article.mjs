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

// A removed frame accepts nothing; a marker for another route is ignored.
frame.isConnected = false;
message({ source: frame.contentWindow, data: { type: 'athena:height', value: 10 } });
assert.equal(frame.style.height, '100000px');
const previous = frame;
queries['.markdown-section .html-article[data-src]'] = { ...marker, dataset: { src: 'https://example.test/' } };
context.buildHtmlArticle();
assert.equal(frame, previous);

console.log('HTML article frame sandbox, URL, height source checks, theme/lang/viewport messages, Ctrl K, in-page scroll and image viewer passed.');
