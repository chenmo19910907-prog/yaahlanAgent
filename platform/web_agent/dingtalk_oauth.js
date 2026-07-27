/** 钉钉 H5 OAuth 免登（login.html / chat.html 共用） */
(function (global) {
  'use strict';

  function isLikelyDingTalkClient() {
    const ua = navigator.userAgent || '';
    return /DingTalk/i.test(ua) || /AliApp\(DingTalk/i.test(ua);
  }

  function requestAuthCode(config) {
    return new Promise((resolve) => {
      const ddApi = global.dd;
      if (!ddApi || !config || !config.corpId) {
        resolve(null);
        return;
      }
      const onSuccess = (result) => {
        const code = (result && (result.code || result.authCode)) || '';
        resolve(code || null);
      };
      const onFail = () => resolve(null);
      const invoke = () => {
        if (typeof ddApi.requestAuthCode === 'function') {
          ddApi.requestAuthCode({
            corpId: config.corpId,
            clientId: config.clientId,
            onSuccess,
            onFail,
          });
          return;
        }
        if (
          ddApi.runtime
          && ddApi.runtime.permission
          && typeof ddApi.runtime.permission.requestAuthCode === 'function'
        ) {
          ddApi.runtime.permission.requestAuthCode({
            corpId: config.corpId,
            onSuccess,
            onFail,
          });
          return;
        }
        resolve(null);
      };
      if (typeof ddApi.ready === 'function') {
        ddApi.ready(invoke);
        if (typeof ddApi.error === 'function') {
          ddApi.error(() => resolve(null));
        }
        return;
      }
      invoke();
    });
  }

  async function exchangeAuthCode(authCode) {
    const res = await fetch('/api/auth/dingtalk-oauth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ authCode }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || '钉钉登录失败');
    }
    return data;
  }

  async function tryDingTalkOAuthLogin(config) {
    if (!config || !config.enabled || !config.corpId || !config.clientId) {
      return false;
    }
    if (!isLikelyDingTalkClient() && !global.dd) {
      return false;
    }
    const authCode = await requestAuthCode(config);
    if (!authCode) {
      return false;
    }
    await exchangeAuthCode(authCode);
    return true;
  }

  global.DingtalkOAuth = {
    isLikelyDingTalkClient,
    requestAuthCode,
    exchangeAuthCode,
    tryDingTalkOAuthLogin,
  };
})(window);
