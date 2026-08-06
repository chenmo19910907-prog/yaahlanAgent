/**
 * Web Agent 客户端打点：POST /api/analytics/event
 */
(function (global) {
  'use strict';

  function currentPage() {
    return global.location.pathname + (global.location.search || '');
  }

  function Analytics() {
    this.staffId = '';
  }

  Analytics.prototype.setUser = function setUser(staffId) {
    this.staffId = String(staffId || '').trim();
  };

  Analytics.prototype.track = function track(event, props) {
    const name = String(event || '').trim();
    if (!name) return;
    const payload = {
      event: name,
      page: currentPage(),
      props: props && typeof props === 'object' ? props : {},
    };
    this._send(payload);
  };

  Analytics.prototype.trackPageView = function trackPageView(extraProps) {
    const props = Object.assign({ title: document.title || '' }, extraProps || {});
    this.track('page_view', props);
  };

  Analytics.prototype._send = function _send(payload) {
    const body = JSON.stringify(payload);
    try {
      if (global.navigator && global.navigator.sendBeacon) {
        const blob = new Blob([body], { type: 'application/json' });
        if (global.navigator.sendBeacon('/api/analytics/event', blob)) return;
      }
    } catch (_) { /* fallback fetch */ }
    global.fetch('/api/analytics/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      credentials: 'same-origin',
      keepalive: true,
    }).catch(function () {});
  };

  const instance = new Analytics();
  global.WebAgentAnalytics = instance;

  function autoPageView() {
    instance.trackPageView();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoPageView);
  } else {
    autoPageView();
  }
}(typeof window !== 'undefined' ? window : globalThis));
