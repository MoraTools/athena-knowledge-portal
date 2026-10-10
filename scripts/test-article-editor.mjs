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
