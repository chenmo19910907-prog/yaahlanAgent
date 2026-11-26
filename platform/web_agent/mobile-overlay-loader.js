/**
 * 手机首屏：工具台/设置等大块 DOM 延后从 chat-overlays.fragment.html 注入。
 */
(function loadMobileOverlaysDeferred() {
  if (!document.documentElement.classList.contains('web-agent-mobile')) return;
  var host = document.getElementById('wa-overlay-defer-host');
  if (!host) return;

  var loaded = false;

  /** 片段摘自整页：含闭合 .main 的 </div>，注入点在 .main 内，须去掉以免拆坏布局 */
  function sanitizeOverlayFragmentHtml(html) {
    return String(html || '').replace(
      /<\/aside>\s*\r?\n\s*<\/div>\s*\r?\n/i,
      '</aside>\n',
    );
  }

  function purgeMobileBootstrapShellState() {
    document.body.classList.remove('layout-shell-pending', 'is-page-bootstrapping');
    document.body.classList.add('layout-ready', 'input-interactive');
    var input = document.getElementById('input');
    if (input) {
      input.readOnly = false;
      input.disabled = false;
    }
  }

  function inject(html) {
    if (loaded) return;
    loaded = true;
    host.insertAdjacentHTML('afterend', sanitizeOverlayFragmentHtml(html));
    host.remove();
    purgeMobileBootstrapShellState();
    document.dispatchEvent(new CustomEvent('wa-overlays-ready'));
  }

  function fetchOverlays() {
    return fetch('chat-overlays.fragment.html', { credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) throw new Error('overlay fragment ' + res.status);
        return res.text();
      })
      .then(inject)
      .catch(function (err) {
        console.warn('mobile overlay defer', err);
      });
  }

  function schedule() {
    if (document.body.classList.contains('input-focused')) {
      setTimeout(schedule, 300);
      return;
    }
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(function () { void fetchOverlays(); }, { timeout: 15000 });
    } else {
      setTimeout(function () { void fetchOverlays(); }, 4000);
    }
  }

  document.addEventListener('wa-need-overlays', function () {
    void fetchOverlays();
  }, { once: false });

  if (document.body.classList.contains('input-focused')) {
    var input = document.getElementById('input');
    if (input) input.addEventListener('blur', schedule, { once: true });
    else schedule();
  } else {
    schedule();
  }
})();