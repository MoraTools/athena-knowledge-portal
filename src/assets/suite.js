(() => {
  'use strict';
  const html = document.documentElement;
  const { resolveTheme, resolveLang, storedValueAfterToggle, read } = window.SuiteBoot;
  const media = matchMedia('(prefers-color-scheme: dark)');
  const browserTheme = () => resolveTheme(null, media.matches);
  const browserLang = () => resolveLang(null, navigator.languages);
  const icons = {
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/>',
    moon: '<path d="M20.9 13a9 9 0 0 1-9.9-9.9A9 9 0 1 0 20.9 13Z"/>',
    languages: '<path d="m5 8 6 6m-7 0 6-6 2-5H2m5-2v2m7 19 5-11 5 11m-8-4h6"/>'
  };
  function save(key, value) {
    try {
      if (value === null) localStorage.removeItem('suite.athena.' + key);
      else localStorage.setItem('suite.athena.' + key, value);
    } catch { /* A blocked store keeps the choice for this page only. */ }
  }
  function labels() {
    const es = html.lang === 'es';
    for (const button of document.querySelectorAll('[data-suite-toggle]')) {
      const theme = button.dataset.suiteToggle === 'theme';
      const light = html.dataset.theme === 'dark';
      const label = theme
        ? es ? `Cambiar a tema ${light ? 'claro' : 'oscuro'}` : `Switch to ${light ? 'light' : 'dark'} theme`
        : es ? 'Switch the language to English' : 'Cambiar el idioma a español';
      button.setAttribute('aria-label', label);
      button.title = theme ? label : es ? 'English' : 'Español';
      const name = theme ? light ? 'sun' : 'moon' : 'languages';
      button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name]}</svg>`;
    }
  }
  function applyTheme(theme) {
    html.dataset.theme = theme;
    labels();
    const color = getComputedStyle(html).getPropertyValue('--bg').trim();
    // The media metas serve the first paint; a stored choice overrides the system theme.
    document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => { meta.content = color; });
    document.dispatchEvent(new CustomEvent('suite:theme', { detail: { theme } }));
  }
  function applyLang(lang) {
    html.lang = lang;
    labels();
    document.dispatchEvent(new CustomEvent('suite:lang', { detail: { lang } }));
  }
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-suite-toggle]');
    if (!button) return;
    if (button.dataset.suiteToggle === 'theme') {
      const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
      save('theme', storedValueAfterToggle(next, browserTheme()));
      applyTheme(next);
    } else {
      const next = html.lang === 'en' ? 'es' : 'en';
      save('lang', storedValueAfterToggle(next, browserLang()));
      applyLang(next);
    }
  });
  media.addEventListener('change', () => { if (!read('theme')) applyTheme(browserTheme()); });
  window.addEventListener('languagechange', () => { if (!read('lang')) applyLang(browserLang()); });
  window.addEventListener('storage', (event) => {
    if (event.key === 'suite.athena.theme') applyTheme(resolveTheme(read('theme'), media.matches));
    if (event.key === 'suite.athena.lang') applyLang(resolveLang(read('lang'), navigator.languages));
  });
  applyLang(html.lang);
  applyTheme(html.dataset.theme);
})();
