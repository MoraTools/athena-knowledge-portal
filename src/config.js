window.$docsify = {
  name: 'ATHENA',
  homepage: 'README.md',
  // The portal rail (src/assets/rail.js, src/app.js) replaces Docsify's sidebar.
  loadSidebar: false,
  hideSidebar: true,
  skipLink: false,
  auto2top: true,
  relativePath: true,
  maxLevel: 3,
  subMaxLevel: 0,
  executeScript: false,
  noEmoji: true,
  notFoundPage: '/not-found.md',
  noCompileLinks: ['/(?:pdf|downloads|article-images)/.*', '/content/[^?#]+\\.pdf(?:[?#].*)?'],
  markdown: {
    renderer: {
      link(token) {
        let href = token.href.replace(/^\/?#(?=\/)/, '');
        // Docsify otherwise adds a second '?' when a reader link has both query and fragment.
        if (href.includes('?') && href.indexOf('#') > 0
          && !/^(?:[a-z][a-z0-9+.-]*:|\/\/|\/(?:pdf|downloads|article-images)\/|\/content\/[^?#]+\.pdf(?:[?#]|$))/i.test(href)) {
          href = href.replace('#', '&id=');
        }
        return this.origin.link.call(this, { ...token, href });
      },
      image(token) {
        // Docsify treats a leading slash as relative to the article directory.
        const href = token.href.startsWith('/article-images/') ? new URL(token.href, location.origin).href : token.href;
        return this.origin.image({ ...token, href });
      }
    }
  },
  plugins: [
    function copyArticle(hook, vm) {
      hook.afterEach((html) => {
        if (!vm.route.path.startsWith('/content/') || html.includes('class="unavailable-page"')) return html;
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
  ]
};
