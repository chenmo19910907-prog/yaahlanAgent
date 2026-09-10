Page({
  data: {
    targetUrl: '',
  },

  onLoad(query) {
    const target = decodeURIComponent((query && query.target) || '');
    this.setData({ targetUrl: target });
  },

  onMessage(e) {
    // H5 可通过 dd.postMessage 与小程序通信（按需扩展）
    const detail = (e && e.detail) || {};
    console.log('web-view message', detail);
  },
});
