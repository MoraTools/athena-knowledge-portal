import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import * as marked from 'marked';

const calls = [];
const window = {};
vm.runInNewContext(readFileSync(new URL('../server/athena/static/athena/article-editor.js', import.meta.url), 'utf8'), {
  window, document: { addEventListener() {} }, marked, URL,
  location: { origin: 'https://athena.test' },
  // The browser smoke uses real DOMPurify. This check guards the required sanitizer boundary.
  DOMPurify: { sanitize(html, options) { calls.push({ html, options }); return html; } }
});
const render = window.athenaRenderMarkdown;
const managed = '/article-images/00000000-0000-4000-8000-000000000001/';
const html = render(`# Guide\n\n**Strong** and [reference](other.md).\n\n![Image](${managed})\n\n![Relative](images/diagram.png)`, {
  title: 'Guide', published: true, slug: 'guide'
});
assert.match(html, /<h1>Guide<\/h1>/);
assert.match(html, /<strong>Strong<\/strong>/);
assert.match(render('- [x] Done\n- [ ] Pending', { published: true }), /\[x\] Done/);
assert.match(render('- [x] Done\n- [ ] Pending', { published: true }), /\[ \] Pending/);
assert.ok(html.includes(`src="https://athena.test${managed}"`));
assert.ok(html.includes('src="https://athena.test/content/images/diagram.png"'));
assert.ok(!html.includes('/admin/'));
assert.match(render('Body', { title: '<script>title</script>', published: false }), /&lt;script&gt;title&lt;\/script&gt;/);
assert.match(render('Body', { title: 'Guide', published: false, pdfName: 'original.pdf', slug: 'guide' }), /Borrador/);
assert.ok(render('Body', { title: 'Guide', published: true, pdfName: 'original.pdf', slug: 'guide' }).includes('/pdf/guide.pdf'));
for (const [source, expected] of [
  ['#/tools?tag=RPA', '/#/tools?tag=RPA'],
  ['/#/tools', '/#/tools'],
  ['/content/other', '/#/content/other'],
  ['/content/other.md?q=one#detail', '/#/content/other?q=one&id=detail'],
  ['other', '/#/content/other'],
  ['other.md?q=one#detail', '/#/content/other?q=one&id=detail'],
  ['other.md#detail', '/#/content/other?id=detail'],
  ['#/content/other?q=one#detail', '/#/content/other?q=one&id=detail'],
  ['/#/content/other#detail', '/#/content/other?id=detail'],
  ['other.md#caf%C3%A9', '/#/content/other?id=caf%C3%A9'],
  ['other.md#bad%', '/#/content/other?id=bad%25'],
  ['../tools', '/#/tools'],
  ['/guides.md', '/#/guides'],
  ['/tools', '/#/tools'],
  ['/downloads.md', '/#/downloads'],
  ['/pdf/guide.pdf', 'https://athena.test/pdf/guide.pdf'],
  ['/pdf/guide.pdf#page=2', 'https://athena.test/pdf/guide.pdf#page=2'],
  ['/downloads/file?version=2', 'https://athena.test/downloads/file?version=2'],
  [managed, 'https://athena.test' + managed],
  ['images/diagram.png', 'https://athena.test/content/images/diagram.png'],
  ['https://example.test/other.md?q=one#detail', 'https://example.test/other.md?q=one#detail'],
  ['//example.test/other.md', '//example.test/other.md'],
  ['#detail', '#detail'],
  ['mailto:reader@example.test', 'mailto:reader@example.test']
]) {
  const output = render(`[Link](${source})`, { title: 'Guide', published: true, slug: 'guide' });
  assert.equal(output.match(/href="([^"]+)"/)[1].replaceAll('&amp;', '&'), expected, source);
}

// Opening a preview link in a new tab must produce the intended initial reader route and anchor.
const readerLocation = {
  origin: 'https://athena.test', pathname: '/', href: '',
  replace(href) { this.href = href; }
};
Object.assign(globalThis, { document: { body: {}, head: {} }, window: { location: readerLocation }, location: readerLocation });
const { HashHistory } = await import('../node_modules/docsify/src/core/router/history/hash.js');
const readerRouter = new HashHistory({ basePath: '', ext: '.md', relativePath: true });
for (const source of ['other.md#detail', 'other.md?q=one#detail', '#/content/other?q=one#detail']) {
  const output = render(`[Link](${source})`, { title: 'Guide', published: true, slug: 'guide' });
  const href = output.match(/href="([^"]+)"/)[1].replaceAll('&amp;', '&');
  readerLocation.href = new URL(href, readerLocation.origin).href;
  readerRouter.normalize();
  const route = readerRouter.parse();
  assert.equal(route.path, '/content/other', source);
  assert.equal(route.query.id, 'detail', source);
  if (source.includes('?')) assert.equal(route.query.q, 'one', source);
}
delete globalThis.document;
delete globalThis.window;
delete globalThis.location;
render('<form><input name="published" form="article_form"><button>Save</button></form><script>alert(1)</script><img src="x" onerror="alert(1)">');
const { options } = calls.at(-1);
for (const tag of ['form', 'input', 'button', 'textarea', 'select', 'script', 'style', 'iframe', 'object', 'embed']) {
  assert.ok(options.FORBID_TAGS.includes(tag));
}
for (const attribute of ['name', 'form', 'id', 'style', 'class', 'autofocus']) assert.ok(options.FORBID_ATTR.includes(attribute));
assert.equal(options.ALLOW_DATA_ATTR, false);
console.log('Article preview Markdown, title, image paths, draft/PDF parity, and sanitizer boundary checks passed.');

// The editor uses native form controls. This DOM stub checks behavior without a new test dependency.
function editor({ readOnly = false, serverError = null, format = null, previewUrl = '' } = {}) {
  const handlers = {}, nodes = new Map(), closeEvents = [], posts = [];
  let focused = null, firstInvalid = null;
  function element(id = '', parent = null) {
    const node = { id, parent, dataset: {}, attributes: {}, listeners: {}, value: '',
      open: false, hidden: false, readOnly, files: [], style: {}, classList: { add() {}, remove() {} },
      addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); },
      async fire(type, extra = {}) {
        const event = { type, target: this, defaultPrevented: false,
          preventDefault() { this.defaultPrevented = true; }, ...extra };
        for (const callback of this.listeners[type] || []) await callback(event);
        return event;
      },
      setAttribute(name, value) { this.attributes[name] = value; },
      getAttribute(name) { return this.attributes[name] ?? null; },
      hasAttribute(name) { return name in this.attributes; },
      querySelector() { return null; }, querySelectorAll() { return []; },
      append() {}, scrollIntoView() {}, focus() { focused = this; },
      contains(target) { for (let node = target; node; node = node.parent) if (node === this) return true; return false; },
      closest(selector) { for (let node = this; node; node = node.parent) if (selector === '.desk-detail-panel' && node.panel) return node; return null; },
      showModal() { this.open = true; },
      close() {
        if (!this.open) return;
        this.open = false;
        closeEvents.push(() => { for (const callback of this.listeners.close || []) callback(); });
      },
      dispatchEvent(event) { for (const callback of this.listeners[event.type] || []) callback(event); }
    };
    nodes.set(id, node);
    return node;
  }
  const form = element('article_form'), dialog = element('article-details', form);
  const panels = [1, 2, 3].map(index => Object.assign(element(`desk-detail-panel-${index}`, dialog), { panel: true }));
  const detailTabs = panels.map((panel, index) => {
    const tab = element(`desk-detail-tab-${index + 1}`, dialog);
    tab.setAttribute('aria-controls', panel.id);
    return tab;
  });
  const tool = element('desk-tool-fields', panels[0]);
  const title = element('id_title', form), body = element('id_body', form);
  title.value = 'Title'; body.value = 'Unsaved Markdown';
  if (previewUrl) body.dataset.htmlPreviewUrl = previewUrl;
  const fields = { title, body };
  if (format) fields.format = { value: format };
  Object.assign(form.dataset, { format: format || 'markdown', articleSlug: 'guide' });
  for (const [name, parent] of [['summary', panels[0]], ['kind', panels[0]], ['url', tool],
    ['date', panels[1]], ['is_public', panels[1]], ['pdf_file', panels[2]], ['markdown_file', panels[2]]]) {
    fields[name] = Object.assign(element(`id_${name}`, parent), { name });
  }
  fields.kind.value = 'guide';
  element('id_markdown_file_helptext');
  for (const id of ['desk-preview-content', 'desk-image-footer', 'desk-state', 'desk-details-state', 'desk-count',
    'desk-source-heading', 'desk-preview-status']) element(id);
  const preview = nodes.get('desk-preview-content');
  preview.replaceChildren = (...children) => { preview.children = children; children.forEach(child => { child.isConnected = true; }); };
  preview.getBoundingClientRect = () => ({ top: 100, bottom: 700 });
  form.querySelector = () => ({ value: 'csrf-token' });
  const overflow = element('overflow'), mainOpener = element('opener'), importOpener = element('import', overflow);
  importOpener.dataset.detailFocus = 'id_markdown_file';
  const close = element('close', dialog), workspace = element('workspace');
  const paneTabs = ['source', 'preview'].map(pane => { const tab = element(pane); tab.dataset.pane = pane; return tab; });
  form.elements = { namedItem: name => readOnly ? null : fields[name] ?? null };
  const csrf = form.querySelector;
  form.querySelector = selector => selector === 'input[name="csrfmiddlewaretoken"]' ? csrf() : firstInvalid;
  form.checkValidity = () => {
    if (firstInvalid) form.dispatchEvent({ type: 'invalid', target: firstInvalid, preventDefault() {} });
    return !firstInvalid;
  };
  form.reportValidity = () => {};
  dialog.querySelectorAll = selector => selector === '[data-detail-tab]' ? detailTabs : panels;
  dialog.querySelector = () => serverError && fields[serverError];
  const queries = { '.desk-overflow': overflow, '[data-open-details]': mainOpener,
    '[data-close-details]': close, '.desk-workspace': workspace };
  vm.runInNewContext(readFileSync(new URL('../server/athena/static/athena/article-editor.js', import.meta.url), 'utf8'), {
    window: { addEventListener(type, callback) { handlers[type] = callback; } },
    document: { documentElement: { dataset: { theme: 'dark' }, lang: 'es' },
      body: { append(node) { node.isConnected = true; } },
      createElement(tag) {
        const node = element('');
        Object.assign(node, { tagName: tag, elements: {}, contentWindow: { messages: [], postMessage(message) { this.messages.push(message); } },
          append(...children) { for (const child of children) if (child.name) this.elements[child.name] = child; },
          submit() { posts.push({ action: this.action, target: this.target, method: this.method, body: this.elements.body.value,
            csrf: this.elements.csrfmiddlewaretoken.value }); },
          getBoundingClientRect: () => ({ top: 150, height: 3000 }) });
        return node;
      },
      getElementById: id => nodes.get(id) ?? null,
      querySelector: selector => queries[selector] ?? null,
      querySelectorAll: selector => selector === '[data-pane]' ? paneTabs : [mainOpener, importOpener],
      addEventListener(type, callback) { handlers[type] = callback; } },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    setTimeout() {}, clearTimeout() {}, TextDecoder, Event, URLSearchParams, innerHeight: 800,
    DOMParser: class { parseFromString(text) { return { querySelectorAll: () => [], body: { textContent: text.replace(/<[^>]*>/g, ' ') } }; } },
    requestAnimationFrame(callback) { callback(); },
    addEventListener(type, callback) { handlers['global:' + type] = callback; }
  });
  handlers.DOMContentLoaded();
  return { form, dialog, panels, detailTabs, fields, tool, close, mainOpener, importOpener, handlers, preview, posts, nodes,
    focused: () => focused, invalidate(field) { firstInvalid = fields[field]; },
    flushClose() { for (const callback of closeEvents.splice(0)) callback(); } };
}

for (const readOnly of [false, true]) {
  const state = editor({ readOnly });
  assert.equal(state.dialog.open, false);
  assert.deepEqual(state.panels.map(panel => panel.hidden), [false, true, true]);
  await state.mainOpener.fire('click');
  assert.equal(state.dialog.open, true);
  await state.detailTabs[0].fire('keydown', { key: 'ArrowLeft' });
  assert.equal(state.focused(), state.detailTabs[2]);
  assert.equal(state.detailTabs[2].getAttribute('aria-selected'), 'true');
  assert.deepEqual(state.detailTabs.map(tab => tab.tabIndex), [-1, -1, 0]);
  assert.deepEqual(state.panels.map(panel => panel.hidden), [true, true, false]);
  await state.detailTabs[2].fire('keydown', { key: 'ArrowRight' });
  assert.equal(state.focused(), state.detailTabs[0]);
  await state.detailTabs[0].fire('keydown', { key: 'End' });
  assert.equal(state.focused(), state.detailTabs[2]);
  await state.detailTabs[2].fire('keydown', { key: 'Home' });
  assert.equal(state.focused(), state.detailTabs[0]);
  await state.close.fire('click');
  assert.equal(state.dialog.open, false);
  state.flushClose();
  assert.equal(state.focused(), state.mainOpener);
  assert.equal(state.fields.body.value, 'Unsaved Markdown');
}
{
  const state = editor();
  await state.importOpener.fire('click');
  assert.deepEqual(state.panels.map(panel => panel.hidden), [true, true, false]);
  assert.equal(state.focused(), state.fields.markdown_file);
  state.invalidate('date');
  await state.form.fire('invalid', { target: state.fields.date });
  assert.equal(state.focused(), state.fields.date);
  assert.deepEqual(state.panels.map(panel => panel.hidden), [true, false, true]);
  const hiddenError = await state.form.fire('invalid', { target: state.fields.pdf_file });
  assert.equal(hiddenError.defaultPrevented, true);
  assert.equal(state.focused(), state.fields.date);
  assert.equal((await state.form.fire('submit')).defaultPrevented, true);
}
{
  const state = editor();
  await state.mainOpener.fire('click');
  state.invalidate('title');
  assert.equal((await state.form.fire('submit')).defaultPrevented, true);
  assert.equal(state.dialog.open, false);
  assert.equal(state.focused(), state.fields.title);
  state.flushClose();
  assert.equal(state.focused(), state.fields.title);
}
{
  const state = editor({ serverError: 'url' });
  assert.equal(state.dialog.open, true);
  assert.equal(state.tool.open, true);
  assert.equal(state.focused(), state.fields.url);
}
for (const field of ['date', 'pdf_file']) {
  const state = editor({ serverError: field });
  assert.equal(state.focused(), state.fields[field]);
  assert.equal(state.fields[field].parent.hidden, false);
}
{
  const state = editor();
  await state.form.fire('change', { target: state.fields.kind });
  let unloadBlocked = false;
  state.handlers.beforeunload({ preventDefault() { unloadBlocked = true; } });
  assert.equal(unloadBlocked, true);
  await state.mainOpener.fire('click');
  const cancel = await state.dialog.fire('cancel');
  assert.equal(cancel.defaultPrevented, false);
  state.dialog.close();
  assert.equal(state.fields.body.value, 'Unsaved Markdown');
  assert.equal((await state.form.fire('submit')).defaultPrevented, false);
  unloadBlocked = false;
  state.handlers.beforeunload({ preventDefault() { unloadBlocked = true; } });
  assert.equal(unloadBlocked, false);
}
{
  const state = editor();
  let finishRead;
  state.fields.markdown_file.value = 'selected.md';
  state.fields.markdown_file.files = [{ name: 'selected.md', size: 123,
    arrayBuffer: () => new Promise(resolve => { finishRead = resolve; }) }];
  const importing = state.fields.markdown_file.fire('change');
  assert.equal(state.fields.body.readOnly, true);
  assert.equal(state.fields.markdown_file.disabled, true);
  assert.equal((await state.form.fire('submit')).defaultPrevented, true);
  assert.equal(state.focused(), state.fields.markdown_file);
  assert.equal((await state.dialog.fire('cancel')).defaultPrevented, true);
  await state.close.fire('click');
  assert.equal(state.dialog.open, true);
  finishRead(new TextEncoder().encode('<!-- athena: imported -->\n# Imported\n\nBody.').buffer);
  await importing;
  assert.equal(state.fields.body.value, '# Imported\n\nBody.');
  assert.equal(state.fields.markdown_file.value, '');
  assert.equal(state.fields.body.readOnly, false);
  assert.equal(state.fields.markdown_file.disabled, false);
  state.fields.body.value += '\n\nEdited after import.';
  assert.equal((await state.form.fire('submit')).defaultPrevented, false);
  assert.match(state.fields.body.value, /Edited after import\.$/);
}
for (const file of [
  { name: 'too-large.md', size: 1024 * 1024 + 1 },
  { name: 'wrong.txt', size: 1 },
  { name: 'invalid.md', size: 1, arrayBuffer: async () => new Uint8Array([0xff]).buffer }
]) {
  const state = editor();
  state.fields.markdown_file.value = file.name;
  state.fields.markdown_file.files = [file];
  await state.fields.markdown_file.fire('change');
  assert.equal(state.fields.body.value, 'Unsaved Markdown');
  assert.equal(state.fields.markdown_file.value, file.name);
  assert.equal(state.fields.body.readOnly, false);
}
// HTML: the unsaved source is posted into the sandboxed preview frame, never put into srcdoc.
{
  const state = editor({ format: 'html', previewUrl: '/article-html-preview/' });
  const frame = state.preview.children[0];
  assert.equal(frame.tagName, 'iframe');
  assert.equal(frame.attributes.sandbox, 'allow-scripts allow-popups allow-popups-to-escape-sandbox');
  assert.equal(frame.srcdoc, undefined);
  assert.equal(state.nodes.get('desk-source-heading').textContent, 'HTML');
  assert.equal(state.nodes.get('desk-count').textContent, '2 palabras');
  assert.equal(JSON.stringify(state.posts), JSON.stringify([{ action: '/article-html-preview/?theme=dark&lang=es', target: frame.name, method: 'post',
    body: 'Unsaved Markdown', csrf: 'csrf-token' }]));
  const message = state.handlers['global:message'];
  message({ source: {}, data: { type: 'athena:height', value: 900 } });
  assert.equal(frame.style.height, undefined, 'Another window cannot resize the preview.');
  message({ source: frame.contentWindow, data: { type: 'athena:height', value: 1234.2 } });
  assert.equal(frame.style.height, '1235px');
  message({ source: frame.contentWindow, data: { type: 'athena:ready' } });
  assert.equal(JSON.stringify(frame.contentWindow.messages.slice(-3)), JSON.stringify([
    { type: 'athena:theme', value: 'dark' }, { type: 'athena:lang', value: 'es' }, { type: 'athena:viewport', value: { top: 0, height: 550 } }]));
  state.fields.format.value = 'markdown';
  await state.form.fire('change', { target: state.fields.format });
  assert.equal(state.nodes.get('desk-source-heading').textContent, 'Markdown');
}
{
  const state = editor({ format: 'html', readOnly: true });
  assert.equal(state.posts.length, 0, 'A view-only page has no preview endpoint.');
  assert.equal(state.preview.children[0].src, '/article-html/guide/?theme=dark&lang=es');
}
console.log('HTML preview frame, sandbox, POST source, message source checks, theme and viewport messages passed.');
console.log('Article detail tabs, read-only controls, keyboard focus, error routing, close retention and native save checks passed.');
