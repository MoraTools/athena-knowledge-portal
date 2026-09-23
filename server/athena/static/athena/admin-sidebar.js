// Opens the portal sidebar on narrow screens; Escape closes it and returns focus to the toggle.
const toggle = document.querySelector('.sidebar-toggle');
if (toggle) {
  const setOpen = (open) => {
    document.body.classList.toggle('sidebar-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Ocultar navegación' : 'Mostrar navegación');
  };
  toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.body.classList.contains('sidebar-open')) {
      setOpen(false);
      toggle.focus();
    }
  });
}
