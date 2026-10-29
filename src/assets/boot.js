// Blocking head script: resolve preferences before styles or page content can paint.
(function (root) {
  'use strict';
  const prefix = 'suite.athena.';
  const resolveTheme = (stored, dark) => stored === 'dark' || stored === 'light' ? stored : dark ? 'dark' : 'light';
  function resolveLang(stored, languages) {
    if (stored === 'en' || stored === 'es') return stored;
    for (const language of languages || []) {
      const match = String(language).toLowerCase().match(/^(en|es)(?:-|$)/);
      if (match) return match[1];
    }
    return 'es';
  }
  function read(key) {
    try { return root.localStorage.getItem(prefix + key); } catch { return null; }
  }
  const storedValueAfterToggle = (next, browser) => next === browser ? null : next;
  root.SuiteBoot = { resolveTheme, resolveLang, storedValueAfterToggle, read };
  if (!root.document) return;
  const html = root.document.documentElement;
  html.dataset.theme = resolveTheme(read('theme'), root.matchMedia('(prefers-color-scheme: dark)').matches);
  html.lang = resolveLang(read('lang'), root.navigator.languages);
  if (html.lang === 'en') {
    html.classList.add('suite-translating');
    root.setTimeout(() => html.classList.remove('suite-translating'), 1500);
  }
})(typeof window === 'undefined' ? globalThis : window);
