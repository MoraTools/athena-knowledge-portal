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
  return {
    tagName: tag, attributes: {}, dataset: {}, style: {}, listeners: {}, isConnected: false,
    classList: { values: new Set(), add(value) { this.values.add(value); }, contains(value) { return this.values.has(value); } },
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); },
    getBoundingClientRect: () => ({ top: -300, height: 4000 })
  };
}

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
    body: { classList: { add() {}, remove() {}, toggle() {} } }
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

// A removed frame accepts nothing; a marker for another route is ignored.
frame.isConnected = false;
message({ source: frame.contentWindow, data: { type: 'athena:height', value: 10 } });
assert.equal(frame.style.height, '100000px');
const previous = frame;
queries['.markdown-section .html-article[data-src]'] = { ...marker, dataset: { src: 'https://example.test/' } };
context.buildHtmlArticle();
assert.equal(frame, previous);

console.log('HTML article frame sandbox, URL, height source checks, theme/lang/viewport messages, Ctrl K and in-page scroll passed.');
