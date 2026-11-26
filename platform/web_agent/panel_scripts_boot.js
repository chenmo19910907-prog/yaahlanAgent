/**
 * 面板脚本按需加载：手机首屏只同步核心脚本，盘古/评审/MOA 录制等延后到 idle。
 */
(function webAgentPanelScriptsBoot() {
  const root = document.documentElement;
  const mobile = root.classList.contains('web-agent-mobile');

  const IMMEDIATE = [
    'https://g.alicdn.com/dingding/dingtalk-jsapi/3.0.25/dingtalk.open.js',
    'dingtalk_oauth.js',
    'miniapp_session.js',
    'analytics.js',
    'waiting_fx.js',
  ];

  const MOBILE_DEFERRED = [
    'bookmarks_panel.js',
    'message_board_panel.js?v=20260730b',
    'about_panel.js?v=20260814a',
    'catalog_panel.js?v=20261110c',
    'guild_pangu_panel.js?v=20261106a',
    'dealer_pangu_panel.js?v=20261117b',
    'yaha_pangu_panel.js?v=20261125a',
    'yaha_trade_union_entrance_panel.js?v=20261126a',
    'dealer_recharge_auth_panel.js?v=20261124b',
    'code_testcase_review_panel.js?v=20261110c',
    'code_multilang_review_panel.js?v=20261111b',
    'moa_record_panel.js?v=20260803d',
  ];

  const DESKTOP_PANELS = [
    'bookmarks_panel.js',
    'message_board_panel.js?v=20260730b',
    'about_panel.js?v=20260814a',
    'catalog_panel.js?v=20261110c',
  ].concat(MOBILE_DEFERRED);
  const DESKTOP_ALL = IMMEDIATE.concat(DESKTOP_PANELS);

  function injectScript(src) {
    document.write('<script src="' + src + '"><\/script>');
  }

  function injectAsync(src) {
    return new Promise((resolve, reject) => {
      const el = document.createElement('script');
      el.src = src;
      el.async = false;
      el.onload = () => resolve();
      el.onerror = () => reject(new Error('panel script failed: ' + src));
      document.body.appendChild(el);
    });
  }

  if (!mobile) {
    const loadList = DESKTOP_ALL;
    for (let i = 0; i < loadList.length; i += 1) {
      injectScript(loadList[i]);
    }
    window.__WEB_AGENT_DEFERRED_PANELS_READY__ = Promise.resolve();
    return;
  }

  function scheduleMobilePanelScripts() {
    let chain = Promise.resolve();
    for (let i = 0; i < IMMEDIATE.length; i += 1) {
      const src = IMMEDIATE[i];
      chain = chain.then(() => injectAsync(src));
    }
    for (let i = 0; i < MOBILE_DEFERRED.length; i += 1) {
      const src = MOBILE_DEFERRED[i];
      chain = chain.then(() => injectAsync(src));
    }
    return chain;
  }

  window.__WEB_AGENT_DEFERRED_PANELS_READY__ = new Promise((resolve) => {
    const run = () => {
      scheduleMobilePanelScripts()
        .then(resolve)
        .catch((err) => {
          console.warn('mobile panel scripts', err);
          resolve();
        });
    };
    const start = () => {
      if (document.body && document.body.classList.contains('input-focused')) {
        setTimeout(start, 200);
        return;
      }
      if (typeof requestIdleCallback === 'function') {
        requestIdleCallback(run, { timeout: 5000 });
      } else {
        setTimeout(run, 400);
      }
    };
    setTimeout(start, 1200);
  });
})();