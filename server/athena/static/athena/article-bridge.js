/* Athena injects this bridge into every HTML article, before the closing body tag. The page has an opaque origin. */
(() => {
  'use strict';
  const root = document.documentElement;
  const post = data => parent.postMessage(data, '*');
  const setTheme = value => { if (value === 'dark' || value === 'light') root.dataset.theme = value; };
  const setLang = value => {
    if (value === 'es' || value === 'en') document.dispatchEvent(new CustomEvent('athena:lang', { detail: value }));
  };
  // The reader puts the current theme and language in the frame URL, so the first paint already matches.
  const query = new URLSearchParams(location.search);
  setTheme(query.get('theme'));
  setLang(query.get('lang'));
  addEventListener('message', event => {
    if (event.source !== parent || !event.data || typeof event.data !== 'object') return;
    const { type, value } = event.data;
    if (type === 'athena:theme') setTheme(value);
    if (type === 'athena:lang') setLang(value);
    if (type === 'athena:viewport' && Number.isFinite(value?.top) && Number.isFinite(value?.height)) {
      document.dispatchEvent(new CustomEvent('athena:viewport', { detail: { top: value.top, height: value.height } }));
    }
  });
  let height = -1;
  function report() {
    const next = Math.ceil(root.getBoundingClientRect().height);
    if (next !== height) { height = next; post({ type: 'athena:height', value: next }); }
  }
  new ResizeObserver(report).observe(root);
  addEventListener('load', report);
  document.addEventListener('toggle', report, true);
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      post({ type: 'athena:search' });
    }
  });
  // The frame is as tall as its content, so an in-page link scrolls the Athena page instead of the frame.
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href^="#"]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    let id = link.getAttribute('href').slice(1);
    try { id = decodeURIComponent(id); } catch { /* Keep a malformed escape as written. */ }
    const target = id && document.getElementById(id);
    if (!target) return;
    event.preventDefault();
    post({ type: 'athena:scroll', value: target.getBoundingClientRect().top });
    if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  });
  post({ type: 'athena:ready' });
})();
