// Filters the user directory in place; accent- and case-insensitive.
const fold = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const search = document.getElementById('directory-q');
if (search) {
  const list = document.querySelector('.directory-list ul');
  const rows = [...list.querySelectorAll('li')].map((li) => [li, fold(li.dataset.search)]);
  const empty = document.querySelector('.directory-empty');
  search.addEventListener('input', () => {
    const query = fold(search.value.trim());
    let shown = 0;
    for (const [li, text] of rows) {
      li.hidden = !text.includes(query);
      if (!li.hidden) shown += 1;
    }
    empty.hidden = shown > 0;
  });
  const current = list.querySelector('[aria-current]');
  if (current) list.scrollTop = current.offsetTop - list.clientHeight / 2;
}
