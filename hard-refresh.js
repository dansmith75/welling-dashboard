// User-facing refresh control. Reloads the site using a unique URL so the latest
// GitHub Pages HTML/data is requested without users needing Ctrl+F5.
(() => {
  const header = document.querySelector('.hero');
  if (!header || document.getElementById('hard-refresh-button')) return;

  const button = document.createElement('button');
  button.id = 'hard-refresh-button';
  button.type = 'button';
  button.className = 'hard-refresh-button';
  button.title = 'Refresh latest version';
  button.setAttribute('aria-label', 'Refresh latest version');
  button.innerHTML = '<span aria-hidden="true">↻</span>';

  const style = document.createElement('style');
  style.textContent = `
    .hero { position:relative; }
    .hard-refresh-button {
      position:absolute;
      top:14px;
      right:14px;
      width:46px;
      height:46px;
      border:1px solid rgba(255,255,255,.45);
      border-radius:50%;
      background:rgba(255,255,255,.14);
      color:#fff;
      display:grid;
      place-items:center;
      padding:0;
      cursor:pointer;
      font:900 30px/1 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      box-shadow:0 2px 8px rgba(0,0,0,.12);
      -webkit-tap-highlight-color:transparent;
    }
    .hard-refresh-button:hover { background:rgba(255,255,255,.22); }
    .hard-refresh-button:focus-visible { outline:3px solid #fff; outline-offset:2px; }
    .hard-refresh-button.refreshing span { animation:welling-refresh-spin .7s linear infinite; }
    @keyframes welling-refresh-spin { to { transform:rotate(360deg); } }
    @media(max-width:520px){
      .hard-refresh-button { top:10px; right:10px; width:42px; height:42px; font-size:27px; }
    }
    @media(prefers-reduced-motion:reduce){ .hard-refresh-button.refreshing span { animation:none; } }
  `;
  document.head.appendChild(style);
  header.appendChild(button);

  button.addEventListener('click', async () => {
    if (button.disabled) return;
    button.disabled = true;
    button.classList.add('refreshing');

    try {
      if ('caches' in window) {
        const names = await caches.keys();
        await Promise.all(names.map(name => caches.delete(name)));
      }
    } catch (_) {
      // Cache Storage is an enhancement only; continue with the cache-busting reload.
    }

    const url = new URL(window.location.href);
    url.searchParams.set('_refresh', Date.now().toString());
    window.location.replace(url.toString());
  });
})();
