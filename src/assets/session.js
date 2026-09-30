// A full navigation clears Docsify's article cache and the search/rail promises on account changes.
(() => {
  const key = 'athena.session';
  const session = document.currentScript.dataset.session;
  try { localStorage.setItem(key, session); } catch { /* Storage can be unavailable in private browsing. */ }
  window.addEventListener('storage', (event) => {
    if (event.key === key && event.newValue !== session) location.reload();
  });
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) location.reload();
  });
})();
