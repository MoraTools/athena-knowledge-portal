// Portal rail, shared by the reader and the admin. <html data-rail> is expanded, compact or hidden.
// Wide screens keep the choice in localStorage; narrow screens open the rail as a drawer and never store it.
// Load it in <head> without defer so the stored state applies before the first paint.
(() => {
  const KEY = 'athena.rail';
  const STATES = ['expanded', 'compact', 'hidden'];
  const root = document.documentElement;
  const narrow = matchMedia('(max-width: 768px)');
  const ICONS = {
    home: '<path d="M3 11 12 4l9 7v9H3z"/>',
    book: '<path d="M4 4h12a3 3 0 0 1 3 3v13H7a3 3 0 0 0-3 3z"/><path d="M4 4v16"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
    tool: '<path d="m14 7 3-3 3 3-3 3zM4 20l9-9"/><path d="M4 20l4-1 1-4"/>',
    download: '<path d="M12 4v11m-5-4 5 5 5-5"/><path d="M4 20h16"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M3 20a6 6 0 0 1 12 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6 6 0 0 1 3 5.5"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    code: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>',
    file: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    collapse: '<path d="m15 6-6 6 6 6"/><path d="M5 5v14"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    dot: '<circle cx="12" cy="12" r="3"/>'
  };
  // Icons follow the link label from /_sidebar.md and the admin model names.
  const LABEL_ICONS = {
    Inicio: 'home', 'Guías': 'book', Actualizaciones: 'clock', Herramientas: 'tool', Descargas: 'download',
    Contribuir: 'plus', 'Mi cuenta': 'user', 'Administrar Athena': 'gear', 'API para agentes': 'code',
    'Artículos': 'file', 'Claves de API': 'key', Usuarios: 'users'
  };
  const tip = document.createElement('div');
  tip.className = 'rail-tip';
  tip.setAttribute('aria-hidden', 'true');

  const stored = () => {
    try { return localStorage.getItem(KEY); } catch { return null; }
  };
  const initial = () => (narrow.matches ? 'hidden' : STATES.includes(stored()) ? stored() : 'expanded');

  function set(state, remember = !narrow.matches) {
    root.dataset.rail = state;
    if (remember) {
      try { localStorage.setItem(KEY, state); } catch { /* private mode: the state lasts for this page only */ }
    }
    const toggle = document.querySelector('.rail-toggle');
    if (toggle) {
      const action = narrow.matches ? 'Cerrar' : state === 'compact' ? 'Expandir' : 'Contraer';
      toggle.querySelector('.rail-label').textContent = action;
      toggle.setAttribute('aria-label', action + ' la navegación');
      toggle.setAttribute('aria-expanded', String(state === 'expanded'));
    }
    document.querySelector('.rail-reveal')?.setAttribute('aria-expanded', String(state !== 'hidden'));
    tip.classList.remove('is-visible');
    const rail = document.querySelector('.rail');
    if (state === 'hidden' && rail?.contains(document.activeElement)) document.querySelector('.rail-reveal')?.focus();
  }

  function decorate(scope = document) {
    scope.querySelectorAll('[data-icon], .rail-item').forEach((element) => {
      if (element.querySelector(':scope > svg')) return;
      const name = element.dataset.icon || LABEL_ICONS[element.textContent.trim()] || 'dot';
      element.insertAdjacentHTML('afterbegin', `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name]}</svg>`);
    });
  }

  function showTip(event) {
    const item = event.target.closest?.('.rail .rail-item, .rail .rail-toggle');
    if (!item || root.dataset.rail !== 'compact') {
      tip.classList.remove('is-visible');
      return;
    }
    const box = item.getBoundingClientRect();
    tip.textContent = item.textContent.trim() || item.getAttribute('aria-label');
    tip.style.top = box.top + box.height / 2 + 'px';
    tip.style.left = box.right + 10 + 'px';
    tip.classList.add('is-visible');
  }

  set(initial(), false);

  document.addEventListener('DOMContentLoaded', () => {
    decorate();
    document.body.append(tip);
    set(root.dataset.rail, false);
  });
  document.addEventListener('pointerover', showTip);
  document.addEventListener('focusin', showTip);
  document.addEventListener('focusout', () => tip.classList.remove('is-visible'));
  document.addEventListener('scroll', () => tip.classList.remove('is-visible'), true);

  document.addEventListener('click', (event) => {
    const control = event.target.closest('.rail-toggle, .rail-reveal, .rail-search-button, .rail-item');
    if (control?.matches('.rail-toggle')) {
      set(narrow.matches ? 'hidden' : root.dataset.rail === 'compact' ? 'expanded' : 'compact');
    } else if (control?.matches('.rail-reveal')) {
      set('expanded');
      if (narrow.matches) document.querySelector('.rail .rail-item[href]')?.focus();
    } else if (control?.matches('.rail-search-button')) {
      set('expanded');
      document.querySelector('#athena-search-input')?.focus();
    } else if (narrow.matches && root.dataset.rail === 'expanded' && (event.target.closest('.rail a') || !event.target.closest('.rail'))) {
      set('hidden'); // A followed link or a tap outside closes the drawer.
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && narrow.matches && root.dataset.rail === 'expanded') {
      set('hidden');
      document.querySelector('.rail-reveal')?.focus();
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input, textarea, select, [contenteditable]')) return;
    if (event.key === '[') set(root.dataset.rail === 'hidden' ? 'expanded' : 'hidden');
    if (event.key === ']' && !narrow.matches) set(root.dataset.rail === 'compact' ? 'expanded' : 'compact');
  });

  narrow.addEventListener('change', () => set(initial(), false));
  window.athenaRail = { decorate };
})();
