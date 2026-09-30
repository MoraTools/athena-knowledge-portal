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
render('<form><input name="published" form="article_form"><button>Save</button></form><script>alert(1)</script><img src="x" onerror="alert(1)">');
const { options } = calls.at(-1);
for (const tag of ['form', 'input', 'button', 'textarea', 'select', 'script', 'style', 'iframe', 'object', 'embed']) {
  assert.ok(options.FORBID_TAGS.includes(tag));
}
for (const attribute of ['name', 'form', 'id', 'style', 'class', 'autofocus']) assert.ok(options.FORBID_ATTR.includes(attribute));
assert.equal(options.ALLOW_DATA_ATTR, false);
console.log('Article preview Markdown, title, image paths, draft/PDF parity, and sanitizer boundary checks passed.');
