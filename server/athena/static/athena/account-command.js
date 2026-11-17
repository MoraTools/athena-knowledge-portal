// Ctrl/Cmd+K focuses the command bar search, as in the reader (src/app.js), which the account pages do not load.
(() => {
  const input = document.querySelector('#athena-search-input');
  if (!input) return;
  const chip = input.parentElement.querySelector('kbd');
  if (chip && /Mac|iPhone|iPad/.test(navigator.platform)) chip.textContent = '⌘ K';
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      window.athenaRail?.closeDrawer();
      input.focus();
      input.select();
    }
  });
})();
