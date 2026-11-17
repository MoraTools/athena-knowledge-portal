// Django renders its own admin strings (Añadir, Modificar, filters, form errors) in the language of the
// django_language cookie (AdminLanguageMiddleware in admin.py). Keep that cookie equal to the suite language, and reload a page that
// Django rendered in the other language, unless the user has typed into it.
(() => {
  'use strict';
  const rendered = document.currentScript.dataset.lang;
  const secure = location.protocol === 'https:' ? '; secure' : '';
  const key = 'athena.admin.langReload';
  let edited = false;
  document.addEventListener('input', () => { edited = true; }, true);
  function follow(lang) {
    document.cookie = `django_language=${lang}; path=/admin/; max-age=31536000; samesite=lax${secure}`;
    try {
      if (lang === rendered) return sessionStorage.removeItem(key);
      // One reload per language, so a server that ignores the cookie cannot cause a reload loop.
      if (edited || sessionStorage.getItem(key) === lang || !document.cookie.split('; ').includes(`django_language=${lang}`)) return;
      sessionStorage.setItem(key, lang);
      location.replace(location.pathname + location.search); // A GET, never a form resubmission.
    } catch { /* A blocked store: Django's strings follow at the next page load. */ }
  }
  document.addEventListener('suite:lang', (event) => follow(event.detail.lang));
  follow(document.documentElement.lang);
})();
