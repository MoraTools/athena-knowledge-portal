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
  // Reader shell only: a script that fails to load, or no render after 10 s, turns the loading line into an error.
  function failBoot() {
    const status = root.document.querySelector('.boot-status');
    if (!status || 'failed' in status.dataset) return;
    status.dataset.failed = '';
    const reload = root.document.createElement('a');
    reload.href = root.location.href;
    reload.textContent = 'Volver a cargar';
    // A same-page link with a hash does not reload by itself.
    reload.addEventListener('click', (event) => { event.preventDefault(); root.location.reload(); });
    status.replaceChildren('No se pudo cargar Athena. ', reload);
    if (root.AthenaI18n) root.AthenaI18n.translate();
  }
  root.addEventListener('error', (event) => { if (event.target instanceof root.HTMLScriptElement) failBoot(); }, true);
  root.setTimeout(failBoot, 10000);
})(typeof window === 'undefined' ? globalThis : window);
