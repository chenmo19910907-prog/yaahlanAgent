/**
 * Web Agent · 币商充值跳过真人认证（Application.dealerAuthConfig）
 */
(function (global) {
  'use strict';

  const REGISTRY_ID = 'dealer_pangu_recharge_auth_whitelist';
  const SCENARIO_KEY = 'dealer_recharge_auth_whitelist';
  const LS_PREFIX = 'web_agent_dealer_auth_whitelist_fields_';
  const MSE_APP_KEY = 'momo.bpm.biz.gameplatform.overseas-voga-mts-user';
  const MSE_NAMESPACE = 'Application';
  const MSE_CONFIG_KEY = 'dealerAuthConfig';

  function buildMseConfigUrl(catalog) {
    const env = catalog?.env || {};
    const q = new URLSearchParams({
      corp: String(env.region || 'alpha'),
      env: String(env.cluster || 'stage'),
      appKey: MSE_APP_KEY,
      nameSpace: MSE_NAMESPACE,
      configKey: MSE_CONFIG_KEY,
    });
    return `https://mse.wemomo.com/#/config/app?${q.toString()}`;
  }

  function loadSavedFields() {
    try {
      const raw = localStorage.getItem(LS_PREFIX);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (_e) {
      return {};
    }
  }

  function saveFieldsFromRoot(root) {
    try {
      localStorage.setItem(
        LS_PREFIX,
        JSON.stringify({
          whiteUsers: root.querySelector('[data-dra-white]')?.value?.trim() || '',
        }),
      );
    } catch (_e) {
      /* ignore */
    }
  }

  const DealerRechargeAuthPanel = {
    renderShell() {
      return `<div class="guild-pangu-panel" data-dealer-auth-panel>
        <p class="guild-pangu-env-hint">预上线 stage · 用户服务 · <code>Application.dealerAuthConfig</code></p>
        <div class="guild-pangu-usage" data-dra-usage></div>
        <label class="guild-pangu-field">
          <span>whitelistUserIds（币商 id）</span>
          <textarea rows="4" data-dra-white placeholder="逗号分隔，打开面板会拉取 MSE 当前白名单"></textarea>
          <small data-dra-white-help></small>
        </label>
        <div class="guild-pangu-actions">
          <button type="button" class="btn" data-dra-reload>重新拉取 MSE 白名单</button>
          <button type="button" class="btn" data-dra-run>生成执行提示</button>
          <button type="button" class="btn" data-dra-mse>打开 MSE 配置</button>
        </div>
        <p class="guild-pangu-status" data-dra-status hidden></p>
      </div>`;
    },

    setStatus(root, text, isError) {
      const el = root.querySelector('[data-dra-status]');
      if (!el) return;
      if (!text) {
        el.hidden = true;
        el.textContent = '';
        return;
      }
      el.hidden = false;
      el.textContent = text;
      el.classList.toggle('is-error', !!isError);
    },

    async loadMeta() {
      const res = await fetch('/api/dealer/pangu/scenarios', { credentials: 'same-origin' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      const scenarios = data.scenarios || [];
      return scenarios.find((s) => String(s.key) === SCENARIO_KEY) || scenarios[0] || {};
    },

    async loadCurrentFromMse() {
      const res = await fetch(
        `/api/dealer/pangu/current?scenario=${encodeURIComponent(SCENARIO_KEY)}`,
        { credentials: 'same-origin' },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      return data;
    },

    fillUsage(root, meta, catalog) {
      const usageEl = root.querySelector('[data-dra-usage]');
      const help = root.querySelector('[data-dra-white-help]');
      const usage = [meta.usageNote, meta.example ? `举例：${meta.example}` : '']
        .filter(Boolean)
        .join('\n');
      if (usageEl) usageEl.textContent = usage || catalog?.docNote || '';
      const fh = meta.fieldHelp || catalog?.web_usage?.field_help || {};
      if (help) help.textContent = fh.whitelistUserIds || fh.whiteUsers || '';
    },

    applyValues(root, values) {
      const saved = loadSavedFields();
      const w = root.querySelector('[data-dra-white]');
      if (w) w.value = saved.whiteUsers || values.whiteUsers || '';
    },

    buildPrompt(root) {
      const white = root.querySelector('[data-dra-white]')?.value?.trim() || '';
      return [
        '请执行币商充值跳过真人认证盘古配置（预上线 stage 保存并全量发布）。',
        '配置：Application.dealerAuthConfig（用户服务 appKey）',
        `whitelistUserIds=${white}`,
        '须保留白名单中已有 userId，勿漏删。',
        '',
        `命令：python3 workflow/workflow_execute.py run dealer-pangu-recharge-auth-whitelist --white-users "${white}"`,
      ].join('\n');
    },

    async reloadMse(root) {
      try {
        this.setStatus(root, '正在拉取 MSE 当前白名单…', false);
        const current = await this.loadCurrentFromMse();
        const w = root.querySelector('[data-dra-white]');
        if (w) w.value = current.whiteUsers || '';
        localStorage.removeItem(LS_PREFIX);
        this.setStatus(root, '已从 MSE 载入当前白名单', false);
        setTimeout(() => this.setStatus(root, ''), 2500);
      } catch (err) {
        this.setStatus(root, `拉取失败：${err.message || err}`, true);
      }
    },

    applyMseLink(root, catalog) {
      const btn = root.querySelector('[data-dra-mse]');
      if (btn) btn.dataset.mseUrl = buildMseConfigUrl(catalog);
    },

    bind(root, onSubmit, meta, catalog) {
      this.applyMseLink(root, catalog);
      root.querySelector('[data-dra-white]')?.addEventListener('input', () => saveFieldsFromRoot(root));
      root.querySelector('[data-dra-reload]')?.addEventListener('click', () => {
        this.reloadMse(root);
      });
      root.querySelector('[data-dra-mse]')?.addEventListener('click', () => {
        const url = root.querySelector('[data-dra-mse]')?.dataset.mseUrl || '';
        if (url) window.open(url, '_blank', 'noopener,noreferrer');
      });
      root.querySelector('[data-dra-run]')?.addEventListener('click', () => {
        saveFieldsFromRoot(root);
        const text = this.buildPrompt(root);
        if (typeof onSubmit === 'function') onSubmit(text);
      });
      this.fillUsage(root, meta, catalog);
    },

    async mount(container, onSubmit) {
      container.innerHTML = this.renderShell();
      const root = container.querySelector('[data-dealer-auth-panel]');
      if (!root) return;
      try {
        const res = await fetch('/api/dealer/pangu/scenarios', { credentials: 'same-origin' });
        const catalog = await res.json();
        if (!res.ok) throw new Error(catalog.error || `HTTP ${res.status}`);
        const scenarios = catalog.scenarios || [];
        const meta = scenarios.find((s) => String(s.key) === SCENARIO_KEY) || {};
        this.bind(root, onSubmit, meta, catalog);
        const current = await this.loadCurrentFromMse();
        this.applyValues(root, current);
      } catch (err) {
        this.setStatus(root, `加载失败：${err.message || err}`, true);
      }
    },
  };

  global.DealerRechargeAuthPanel = DealerRechargeAuthPanel;
  global.isDealerRechargeAuthCapItem = (item) =>
    String(item?.registry_id || '').trim() === REGISTRY_ID;
}(typeof window !== 'undefined' ? window : globalThis));