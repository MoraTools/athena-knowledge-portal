// The native GET form remains available when JavaScript is off.
const fold = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const search = document.getElementById('directory-q');
if (search) {
  const rows = [...document.querySelectorAll('.directory-table tbody tr')].map((row) => [row, fold(row.dataset.search)]);
  const sorts = [...document.querySelectorAll('.directory-sort')];
  const empty = document.querySelector('.directory-empty');
  search.addEventListener('input', () => {
    const query = fold(search.value.trim());
    let shown = 0;
    for (const [row, text] of rows) {
      row.hidden = !text.includes(query);
      if (!row.hidden) shown += 1;
    }
    empty.hidden = shown > 0;
    // Native links include the current live query, including opening a link in a new tab.
    for (const link of sorts) {
      const url = new URL(link.href, location.href);
      if (search.value.trim()) url.searchParams.set('q', search.value.trim());
      else url.searchParams.delete('q');
      link.href = url.pathname + url.search;
    }
  });
}
