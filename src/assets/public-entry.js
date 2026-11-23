(() => {
  const key = 'athena.public';
  const url = new URL(location.href);
  let publicEntry = false;

  function redirectHome() {
    if (publicEntry || !['', '#', '#/', '#/README', '#/README.md'].includes(location.hash)) return;
    try { if (sessionStorage.getItem(key) === '1') return; } catch {}
    location.replace('/accounts/login/');
  }

  if (url.searchParams.getAll('biblioteca').includes('publica')) {
    // Keep this page open when Docsify adds #/ and storage is blocked.
    try { sessionStorage.setItem(key, '1'); } catch { publicEntry = true; }
    url.searchParams.delete('biblioteca');
    history.replaceState(history.state, '', url);
  } else {
    redirectHome();
  }
  addEventListener('hashchange', redirectHome);
})();
