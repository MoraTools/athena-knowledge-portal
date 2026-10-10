import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../server/athena/static/athena/article-images.js', import.meta.url), 'utf8');
class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.classList = { toggle() {} };
    this.disabled = false;
    this.textContent = '';
  }
  append(...items) { this.children.push(...items); }
  before(item) { this.wrapper = item; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] || null; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  dispatchEvent(event) { for (const handler of this.listeners[event.type] || []) handler(event); }
  focus() { this.focused = true; }
  click() { this.dispatchEvent({ type: 'click' }); }
}

function setup({ disabled = false } = {}) {
  const requests = [];
  const submits = [new Element('input'), new Element('input')];
  submits[1].disabled = true;
  const form = new Element('form');
  form.querySelectorAll = () => submits;
  form.querySelector = () => ({ value: 'csrf-token' });
  const textarea = new Element('textarea');
  Object.assign(textarea, {
    form, disabled, dataset: { imageUploadUrl: '/article-images/upload/', imageArticleId: '12' },
    value: 'Before SELECTED After', selectionStart: 7, selectionEnd: 15,
    selectionDirection: 'backward', scrollTop: 83,
    setRangeText(value, start, end) { this.value = this.value.slice(0, start) + value + this.value.slice(end); },
    setSelectionRange(start, end, direction) {
      this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction;
    }
  });
  const handlers = {};
  let serial = 0;
  const context = vm.createContext({
    document: {
      createElement: tag => new Element(tag), querySelector: () => textarea,
      addEventListener(type, callback) { handlers[type] = callback; }
    },
    window: { addEventListener(type, callback) { handlers[type] = callback; } },
    crypto: { randomUUID: () => `00000000-0000-4000-8000-${String(++serial).padStart(12, '0')}` },
    Event: class { constructor(type) { this.type = type; } },
    FormData: class { constructor() { this.fields = new Map(); } append(name, value) { this.fields.set(name, value); } },
    fetch(url, options) { return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })); }
  });
  vm.runInContext(source, context);
  handlers.DOMContentLoaded();
  const tools = textarea.wrapper?.children[1];
  const [button, picker, status] = tools?.children || [];
  return { textarea, form, submits, requests, button, picker, status, handlers };
}

const file = (name = 'screenshot.png') => ({ name, type: 'image/png', size: 123 });
function paste(textarea, files = []) {
  let prevented = false;
  textarea.dispatchEvent({
    type: 'paste', clipboardData: { items: files.map(value => ({ kind: 'file', type: value.type, getAsFile: () => value })) },
    preventDefault() { prevented = true; }
  });
  return prevented;
}
function submit(form) {
  let prevented = false;
  form.dispatchEvent({ type: 'submit', preventDefault() { prevented = true; }, stopImmediatePropagation() {} });
  return prevented;
}
const url = n => `/article-images/00000000-0000-4000-8000-${String(n).padStart(12, '0')}/`;
async function success(request, n) {
  request.resolve({ ok: true, json: async () => ({ url: url(n) }) });
  await new Promise(setImmediate);
}
async function failure(request, error = 'La imagen no es válida.') {
  request.resolve({ ok: false, json: async () => ({ error }) });
  await new Promise(setImmediate);
}

// Text paste uses the browser's existing operation. View-only fields get no uploader.
{
  const state = setup();
  assert.equal(paste(state.textarea), false);
  assert.equal(state.textarea.value, 'Before SELECTED After');
  assert.equal(state.requests.length, 0);
  assert.equal(setup({ disabled: true }).button, undefined);
}

// Insert at a selected range without discarding its text; block save and send CSRF + article scope.
{
  const state = setup();
  assert.equal(paste(state.textarea, [file()]), true);
  assert.equal(submit(state.form), true);
  assert.ok(state.submits.every(button => button.disabled));
  assert.equal(state.textarea.value.slice(state.textarea.selectionStart, state.textarea.selectionEnd), 'SELECTED');
  const request = state.requests[0];
  assert.equal(request.url, '/article-images/upload/');
  assert.equal(request.options.headers['X-CSRFToken'], 'csrf-token');
  assert.equal(request.options.credentials, 'same-origin');
  assert.equal(request.options.body.fields.get('article_id'), '12');
  state.textarea.setSelectionRange(state.textarea.value.length, state.textarea.value.length, 'none');
  state.textarea.value += ' typed while uploading';
  state.textarea.setSelectionRange(state.textarea.value.length, state.textarea.value.length, 'none');
  await success(request, 1);
  assert.equal(state.textarea.value, `Before ![Imagen](${url(1)})SELECTED After typed while uploading`);
  assert.equal(state.textarea.selectionStart, state.textarea.value.length);
  assert.equal(state.textarea.scrollTop, 83);
  assert.equal(state.submits[0].disabled, false);
  assert.equal(state.submits[1].disabled, true);
  assert.equal(submit(state.form), false);
}

// Serial uploads keep paste order, and a later selection stays over its original text.
{
  const state = setup();
  state.textarea.setSelectionRange(7, 7, 'none');
  paste(state.textarea, [file('one.png'), file('two.png')]);
  const start = state.textarea.value.indexOf('After');
  state.textarea.setSelectionRange(start, start + 5, 'backward');
  assert.equal(state.requests.length, 1, 'The browser sends one image at a time.');
  await success(state.requests[0], 1);
  assert.equal(state.submits[0].disabled, true);
  await success(state.requests[1], 2);
  assert.equal(state.textarea.value, `Before ![Imagen](${url(1)})\n![Imagen](${url(2)})SELECTED After`);
  assert.equal(state.textarea.value.slice(state.textarea.selectionStart, state.textarea.selectionEnd), 'After');
  assert.equal(state.textarea.selectionDirection, 'backward');
}

// Failed upload removes only its marker; edits before/after it and selected text survive.
{
  const state = setup();
  paste(state.textarea, [file()]);
  state.textarea.value = 'New prefix ' + state.textarea.value + ' new suffix';
  const selected = state.textarea.value.indexOf('SELECTED');
  state.textarea.setSelectionRange(selected, selected + 8, 'forward');
  await failure(state.requests[0]);
  assert.equal(state.textarea.value, 'New prefix Before SELECTED After new suffix');
  assert.equal(state.textarea.value.slice(state.textarea.selectionStart, state.textarea.selectionEnd), 'SELECTED');
  assert.match(state.status.textContent, /Su texto se conservó/);
  assert.equal(submit(state.form), false);
}

// Different paste events retain order; deleting a pending marker must not resurrect it.
{
  const state = setup();
  state.textarea.setSelectionRange(0, 0, 'none');
  paste(state.textarea, [file('first.png')]);
  paste(state.textarea, [file('second.png')]);
  await success(state.requests[0], 1);
  await success(state.requests[1], 2);
  assert.ok(state.textarea.value.startsWith(`![Imagen](${url(1)})![Imagen](${url(2)})`));
  state.textarea.setSelectionRange(0, 0, 'none');
  paste(state.textarea, [file('deleted.png')]);
  state.textarea.value = state.textarea.value.replace(/<!-- athena-image-upload:[^>]* -->/, '');
  await success(state.requests[2], 3);
  assert.equal(state.textarea.value.includes(url(3)), false);
}

// Network and non-JSON server failures give Spanish errors and retain the original text.
{
  const state = setup();
  paste(state.textarea, [file()]);
  state.requests[0].reject(new TypeError('Failed to fetch'));
  await new Promise(setImmediate);
  assert.equal(state.textarea.value, 'Before SELECTED After');
  assert.match(state.status.textContent, /No se pudo conectar con el servidor/);
  paste(state.textarea, [file()]);
  state.requests[1].resolve({ ok: false, json: async () => { throw new SyntaxError('Unexpected HTML'); } });
  await new Promise(setImmediate);
  assert.equal(state.textarea.value, 'Before SELECTED After');
  assert.match(state.status.textContent, /El servidor no respondió/);
}

// Native file chooser works before the first article save; rejected formats preserve the body.
{
  const state = setup();
  state.textarea.dataset.imageArticleId = '';
  state.picker.files = [file()];
  state.picker.dispatchEvent({ type: 'change' });
  assert.equal(state.requests[0].options.body.fields.has('article_id'), false);
  await success(state.requests[0], 1);
  const original = state.textarea.value;
  paste(state.textarea, [{ name: 'bad.svg', type: 'image/svg+xml', size: 20 }]);
  assert.equal(state.textarea.value, original);
  assert.equal(state.requests.length, 1);
  assert.match(state.status.textContent, /Use PNG, JPEG, WebP o GIF/);
}

// GIF files from clipboard files/items and the chooser share upload and save protection.
{
  const state = setup();
  assert.ok(state.picker.accept.includes('image/gif'));
  const gif = { name: 'animation.gif', type: 'image/gif', size: 123 };
  assert.equal(paste(state.textarea, [gif]), true);
  assert.equal(state.requests[0].options.body.fields.get('file'), gif);
  assert.equal(submit(state.form), true);
  await success(state.requests[0], 1);
  for (const type of ['image/gif', '', 'application/octet-stream']) {
    const clipboardGif = { ...gif, type };
    let prevented = false;
    state.textarea.dispatchEvent({ type: 'paste',
      clipboardData: { files: [clipboardGif], items: [{ kind: 'file', getAsFile: () => clipboardGif }] },
      preventDefault() { prevented = true; }
    });
    assert.equal(prevented, true);
    const request = state.requests.at(-1);
    assert.equal(request.options.body.fields.get('file'), clipboardGif);
    await success(request, 2);
  }
  assert.equal(state.requests.length, 4, 'Clipboard files/items must not upload the same file twice.');
  state.picker.files = [gif];
  state.picker.dispatchEvent({ type: 'change' });
  assert.equal(state.requests.at(-1).options.body.fields.get('file'), gif);
  await success(state.requests.at(-1), 3);
  assert.equal(submit(state.form), false);
}

console.log('Article image paste, async order, selection, failure, text, CSRF and native chooser checks passed.');

// Compile actual Markdown with the shipped Docsify bundle, including its image path resolution.
{
  const document = {
    body: { clientWidth: 1000 }, head: {}, documentElement: {}, readyState: 'loading', currentScript: null,
    addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    getElementsByTagName() { return []; }
  };
  const location = { pathname: '/', origin: 'https://athena.test', href: 'https://athena.test/#/content/example' };
  const window = { document, location, addEventListener() {} };
  const context = vm.createContext({
    window, document, location, URL, Element: class {}, navigator: { userAgent: 'Node' },
    console: { warn() {}, error: console.error }, setTimeout() {}, clearTimeout() {},
    getComputedStyle: () => ({ getPropertyValue: () => '' }), matchMedia: () => ({ matches: false })
  });
  // build-vps.py copies this exact runtime to dist/vendor/docsify.min.js.
  vm.runInContext(readFileSync(new URL('../node_modules/docsify/dist/docsify.min.js', import.meta.url), 'utf8'), context);
  assert.equal(window.Docsify.version, '5.0.0', 'The runtime must match the pinned Docsify version.');
  vm.runInContext(readFileSync(new URL('../src/config.js', import.meta.url), 'utf8'), context);
  // The installed router supplies relative path and fragment behavior to the shipped compiler.
  Object.assign(globalThis, { document, window, location });
  const { HashHistory } = await import('../node_modules/docsify/src/core/router/history/hash.js');
  const router = new HashHistory({ basePath: '', ext: '.md', ...window.$docsify });
  const compiler = new window.DocsifyCompiler(window.$docsify, router);
  const managed = url(8);
  for (const markdown of [`![Imagen](${managed})`, `![Imagen][image]\n\n[image]: ${managed}`,
                          `![Imagen](${managed}?version=1#image "Screenshot")`]) {
    const html = compiler.compile(markdown);
    assert.ok(html.includes(`src="${location.origin}${managed}`), html);
    assert.equal(html.includes('/content/article-images/'), false);
    assert.match(html, /alt="Imagen"/);
  }
  assert.ok(compiler.compile('![Relative](images/example.png)').includes('src="/content/images/example.png"'));
  const external = 'https://raw.githubusercontent.com/example/image.png';
  assert.ok(compiler.compile(`![External](${external})`).includes(`src="${external}"`));
  assert.ok(compiler.compile(`<img src="${managed}" alt="HTML">`).includes(`src="${managed}"`));
  for (const [href, expected] of [
    ['other', '#/content/other'], ['other.md', '#/content/other'],
    ['other.md?q=one#detail', '#/content/other?q=one&id=detail'],
    ['#/tools', '#/tools'], ['/#/tools?tag=rpa', '#/tools?tag=rpa'],
    ['/content/other', '#/content/other'], ['/pdf/other.pdf', '/pdf/other.pdf'],
    ['/pdf/other.pdf?download=1#page=2', '/pdf/other.pdf?download=1#page=2'],
    ['/content/example.pdf', '/content/example.pdf'], ['/downloads/file', '/downloads/file'],
    [managed, managed], [external, external]
  ]) {
    const html = compiler.compile(`[Link](${href})`);
    assert.ok(html.includes(`href="${expected.replaceAll('&', '&amp;')}"`), `${href}: ${html}`);
  }
  delete globalThis.document;
  delete globalThis.window;
  delete globalThis.location;
  console.log('Shipped Docsify inline/reference managed-image source and existing image path checks passed.');
}
