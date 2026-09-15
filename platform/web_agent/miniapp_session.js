/** 钉钉小程序 web-view 会话桥：URL ?_session= 换 Cookie */
(function (global) {
  'use strict';

  async function bootstrapFromUrl() {
    const url = new URL(global.location.href);
    const token = (url.searchParams.get('_session') || '').trim();
    if (!token) return false;
    url.searchParams.delete('_session');
    const clean = url.pathname + (url.search || '') + (url.hash || '');
    try {
      const res = await fetch('/api/auth/miniapp-bridge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ sessionToken: token }),
      });
      if (!res.ok) return false;
      global.history.replaceState(null, '', clean || url.pathname);
      return true;
    } catch (_) {
      return false;
    }
  }

  global.MiniappSession = {
    bootstrapFromUrl,
  };
})(window);
