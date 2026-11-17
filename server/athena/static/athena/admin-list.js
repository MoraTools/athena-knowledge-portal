// Bulk bar for admin changelists: appears when rows are checked and runs Django's delete_selected
// through the hidden action form, so the confirmation page still protects the deletion.
const form = document.getElementById('changelist-form');
const action = form?.querySelector('.bulk-source select[name=action]');
const boxes = form ? [...form.querySelectorAll('input.action-select')] : [];
if (action && boxes.length && [...action.options].some((option) => option.value === 'delete_selected')) {
  const bar = document.createElement('div');
  bar.className = 'bulk-bar';
  bar.hidden = true;
  bar.setAttribute('role', 'region');
  bar.setAttribute('aria-label', 'Selección');
  bar.innerHTML = '<span class="bulk-count" aria-live="polite"></span>'
    + '<button type="button" class="button danger" data-bulk="delete">Eliminar seleccionados</button>'
    + '<button type="button" class="button" data-bulk="cancel">Cancelar</button>';
  form.querySelector('.results').before(bar);
  const count = bar.querySelector('.bulk-count');

  const update = () => {
    const selected = boxes.filter((box) => box.checked).length;
    bar.hidden = selected === 0;
    count.textContent = selected === 1 ? '1 seleccionado' : `${selected} seleccionados`;
  };

  bar.addEventListener('click', (event) => {
    const button = event.target.closest('[data-bulk]');
    if (button?.dataset.bulk === 'delete') {
      action.value = 'delete_selected';
      form.querySelector('.bulk-source button[name=index]').click();
    } else if (button?.dataset.bulk === 'cancel') {
      // A change event per box keeps Django's actions.js (row highlight, select-all toggle) in step.
      boxes.filter((box) => box.checked).forEach((box) => {
        box.checked = false;
        box.dispatchEvent(new Event('change', { bubbles: true }));
      });
      (document.getElementById('action-toggle') || boxes[0]).focus();
    }
  });
  // Form-level listeners run after Django's tbody listener, so shift-range and select-all are counted.
  form.addEventListener('change', update);
  window.addEventListener('pageshow', update);
  update();
}
