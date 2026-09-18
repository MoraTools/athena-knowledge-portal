window.$docsify = {
  name: 'ATHENA',
  homepage: 'README.md',
  loadSidebar: true,
  auto2top: true,
  maxLevel: 3,
  subMaxLevel: 0,
  executeScript: false,
  noEmoji: true,
  plugins: [
    function copyArticle(hook, vm) {
      hook.afterEach((html) => {
        if (!vm.route.path.startsWith('/content/')) return html;
        return `<div class="article-actions"><button class="copy-page" type="button"><svg class="copy-page__copy" aria-hidden="true" viewBox="0 0 24 24"><path d="M8 7V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2M5 8h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2Z"/></svg><svg class="copy-page__check" aria-hidden="true" viewBox="0 0 24 24"><path d="m5 13 4 4L19 7"/></svg><span>Copiar página</span></button></div>${html}`;
      });
      hook.doneEach(() => window.athenaSyncView?.());
    },
    function sanitizeArticle(hook) {
      hook.afterEach((html) => DOMPurify.sanitize(html, {
        ADD_TAGS: ['input', 'select', 'option', 'label'],
        FORBID_TAGS: ['style', 'iframe', 'script', 'object', 'embed'],
        FORBID_ATTR: ['style']
      }));
    }
  ],
  alias: { '/.*/_sidebar.md': '/_sidebar.md' }
};
