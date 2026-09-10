const DEFAULT_CONFIG = {
  webAgentBaseUrl: '',
  corpId: '',
};

function loadConfig() {
  try {
    const local = require('../../config.json');
    return Object.assign({}, DEFAULT_CONFIG, local || {});
  } catch (e) {
    return Object.assign({}, DEFAULT_CONFIG);
  }
}

function normalizeBaseUrl(url) {
  return String(url || '').trim().replace(/\/+$/, '');
}

Page({
  data: {
    statusText: '正在连接 Agent…',
    errorText: '',
    showRetry: false,
  },

  onLoad() {
    this.config = loadConfig();
    this.bootstrap();
  },

  onRetry() {
    this.setData({ errorText: '', showRetry: false, statusText: '正在连接 Agent…' });
    this.bootstrap();
  },

  bootstrap() {
    const baseUrl = normalizeBaseUrl(this.config.webAgentBaseUrl);
    if (!baseUrl) {
      this.fail('请配置 config.json 中的 webAgentBaseUrl（Web Agent 公网 HTTPS 地址）');
      return;
    }
    const corpId = String(this.config.corpId || '').trim();
    if (!corpId) {
      this.openWebview(baseUrl + '/chat.html');
      return;
    }
    this.setData({ statusText: '正在获取钉钉身份…' });
    dd.getAuthCode({
      corpId,
      success: (res) => {
        const authCode = (res && (res.authCode || res.code)) || '';
        if (!authCode) {
          this.openWebview(baseUrl + '/login.html');
          return;
        }
        this.exchangeAndOpen(baseUrl, authCode);
      },
      fail: () => {
        this.openWebview(baseUrl + '/login.html');
      },
    });
  },

  exchangeAndOpen(baseUrl, authCode) {
    this.setData({ statusText: '正在登录…' });
    dd.httpRequest({
      url: baseUrl + '/api/auth/dingtalk-oauth',
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      data: JSON.stringify({ authCode }),
      dataType: 'json',
      success: (res) => {
        if (res.status === 200 && res.data && res.data.ok) {
          this.openWebview(baseUrl + '/chat.html');
          return;
        }
        const err = (res.data && res.data.error) || '登录失败';
        this.openWebview(baseUrl + '/login.html?err=' + encodeURIComponent(err));
      },
      fail: () => {
        this.openWebview(baseUrl + '/login.html');
      },
    });
  },

  openWebview(url) {
    dd.redirectTo({
      url: '/pages/webview/webview?target=' + encodeURIComponent(url),
    });
  },

  fail(message) {
    this.setData({
      statusText: '无法启动',
      errorText: message,
      showRetry: true,
    });
  },
});
