// The native GET form remains available when JavaScript is off.
const fold = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const search = document.getElementById('directory-q');
if (search) {
  const rows = [...document.querySelectorAll('.directory-table tbody tr')].map((row) => [row, fold(row.dataset.search)]);
  const empty = document.querySelector('.directory-empty');
  search.addEventListener('input', () => {
    const query = fold(search.value.trim());
    let shown = 0;
    for (const [row, text] of rows) {
      row.hidden = !text.includes(query);
      if (!row.hidden) shown += 1;
    }
    empty.hidden = shown > 0;
  });
}
