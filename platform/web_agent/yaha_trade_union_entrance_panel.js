/**
 * Web Agent · Yaha 大区公会入口（voga-common.trade_union_entrance_config）
 */
(function (global) {
  'use strict';

  const REGISTRY_ID = 'yaha_pangu_trade_union_entrance';
  const SCENARIO_KEY = 'yaha_trade_union_entrance';
  const LS_PREFIX = 'web_agent_yaha_trade_union_entrance_fields';

  const YahaTradeUnionEntrancePanel = {
    renderShell() {
      return `<div class="guild-pangu-panel" data-yaha-tu-entrance-panel>
        <p class="guild-pangu-env-hint">预上线 stage · <code>voga-common.trade_union_entrance_config</code></p>
        <div class="guild-pangu-usage" data-ytu-usage></div>
        <label class="guild-pangu-field">
          <span>总开关 enabled</span>
          <select data-ytu-enabled>
            <option value="true">true — 开启大区/白名单控制</option>
            <option value="false">false — 关闭</option>
          </select>
          <small data-ytu-enabled-help></small>
        </label>
        <label class="guild-pangu-field">
          <span>开放大区 openAreas</span>
          <input type="text" data-ytu-areas placeholder="MENA,TR,SA,SAM,RU" />
          <small data-ytu-areas-help></small>
        </label>
        <label class="guild-pangu-field">
          <span>白名单 whiteUserIds</span>
          <input type="text" data-ytu-white placeholder="逗号分隔 userId，可空" />
          <small data-ytu-white-help></small>
        </label>
        <div class="guild-pangu-actions">
          <button type="button" class="btn" data-ytu-refresh>刷新当前值</button>
          <button type="button" class="btn primary" data-ytu-run>生成执行提示</button>
        </div>
        <p class="guild-pangu-status" data-ytu-status hidden></p>
      </div>`;
    },

    setStatus(root, text, isError) {
      const el = root.querySelector('[data-ytu-status]');
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

    fillUsage(root, meta, catalog) {
      const usageEl = root.querySelector('[data-ytu-usage]');
      const usage = [meta.usageNote, meta.example ? `举例：${meta.example}` : '']
        .filter(Boolean)
        .join('\n');
      if (usageEl) usageEl.textContent = usage || catalog?.docNote || '';
      const fh = meta.fieldHelp || catalog?.web_usage?.field_help || {};
      const eh = root.querySelector('[data-ytu-enabled-help]');
      const ah = root.querySelector('[data-ytu-areas-help]');
      const wh = root.querySelector('[data-ytu-white-help]');
      if (eh) eh.textContent = fh.enabled || '';
      if (ah) ah.textContent = fh.openAreas || '';
      if (wh) wh.textContent = fh.whiteUserIds || '';
    },

    loadSaved() {
      try {
        const raw = localStorage.getItem(LS_PREFIX);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {};
      } catch (_e) {
        return {};
      }
    },

    saveFromRoot(root) {
      try {
        localStorage.setItem(
          LS_PREFIX,
          JSON.stringify({
            enabled: root.querySelector('[data-ytu-enabled]')?.value || 'true',
            openAreas: root.querySelector('[data-ytu-areas]')?.value?.trim() || '',
            whiteUserIds: root.querySelector('[data-ytu-white]')?.value?.trim() || '',
          }),
        );
      } catch (_e) {
        /* ignore */
      }
    },

    applyValues(root, values, defaults) {
      const saved = this.loadSaved();
      const en =
        saved.enabled ||
        (values && values.enabled) ||
        (defaults && defaults.enabled) ||
        'true';
      const areas =
        saved.openAreas ||
        (values && values.openAreas) ||
        (defaults && defaults.openAreas) ||
        '';
      const white =
        saved.whiteUserIds ||
        (values && (values.whiteUserIds || values.whiteUsers)) ||
        '';
      const enSel = root.querySelector('[data-ytu-enabled]');
      if (enSel && (en === 'true' || en === 'false')) enSel.value = en;
      const areasIn = root.querySelector('[data-ytu-areas]');
      if (areasIn && areas) areasIn.value = areas;
      const whiteIn = root.querySelector('[data-ytu-white]');
      if (whiteIn && white) whiteIn.value = white;
    },

    applyFormValues(root, values) {
      if (!values || typeof values !== 'object') return;
      const enSel = root.querySelector('[data-ytu-enabled]');
      if (enSel && values.enabled != null) {
        const en = String(values.enabled);
        if (en === 'true' || en === 'false') enSel.value = en;
      }
      const areasIn = root.querySelector('[data-ytu-areas]');
      if (areasIn && values.openAreas != null) areasIn.value = String(values.openAreas);
      const whiteIn = root.querySelector('[data-ytu-white]');
      const white = values.whiteUserIds != null ? values.whiteUserIds : values.whiteUsers;
      if (whiteIn && white != null) whiteIn.value = String(white);
      this.saveFromRoot(root);
    },

    async refreshCurrent(root) {
      this.setStatus(root, '正在读取 MSE 当前值…', false);
      try {
        const res = await fetch(`/api/yaha/pangu/current?scenario=${encodeURIComponent(SCENARIO_KEY)}`, {
          credentials: 'same-origin',
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        this.applyFormValues(root, data);
        this.setStatus(root, '已代入预上线当前值', false);
        window.setTimeout(() => this.setStatus(root, '', false), 2500);
      } catch (err) {
        this.setStatus(root, `读取失败：${err.message || err}`, true);
      }
    },

    buildPrompt(root) {
      const enabled = root.querySelector('[data-ytu-enabled]')?.value?.trim() || 'true';
      const openAreas = root.querySelector('[data-ytu-areas]')?.value?.trim() || '';
      const whiteUserIds = root.querySelector('[data-ytu-white]')?.value?.trim() || '';
      return [
        '请执行 Yaha 大区公会入口盘古配置（预上线 stage 保存并全量发布）。',
        '配置：voga-common.trade_union_entrance_config（vas）',
        `enabled=${enabled}`,
        `openAreas=${openAreas}`,
        whiteUserIds ? `whiteUserIds=${whiteUserIds}` : 'whiteUserIds=（未改可留空，发布前请与 MSE 当前值核对）',
        '',
        `命令：python3 workflow/workflow_execute.py run yaha-pangu-trade-union-entrance --enabled ${enabled} --open-areas "${openAreas}" --white-users "${whiteUserIds}"`,
      ].join('\n');
    },

    bind(root, onSubmit, meta, catalog, defaults) {
      const persist = () => this.saveFromRoot(root);
      root.querySelectorAll('[data-ytu-enabled], [data-ytu-areas], [data-ytu-white]').forEach((el) => {
        el.addEventListener('change', persist);
        el.addEventListener('input', persist);
      });
      root.querySelector('[data-ytu-refresh]')?.addEventListener('click', () => {
        this.refreshCurrent(root);
      });
      root.querySelector('[data-ytu-run]')?.addEventListener('click', () => {
        persist();
        const text = this.buildPrompt(root);
        if (typeof onSubmit === 'function') onSubmit(text);
      });
      this.fillUsage(root, meta, catalog);
    },

    async mount(container, onSubmit) {
      container.innerHTML = this.renderShell();
      const root = container.querySelector('[data-yaha-tu-entrance-panel]');
      if (!root) return;
      try {
        const [catRes, curRes] = await Promise.all([
          fetch('/api/yaha/pangu/scenarios', { credentials: 'same-origin' }),
          fetch(`/api/yaha/pangu/current?scenario=${encodeURIComponent(SCENARIO_KEY)}`, {
            credentials: 'same-origin',
          }),
        ]);
        const catalog = await catRes.json();
        if (!catRes.ok) throw new Error(catalog.error || `HTTP ${catRes.status}`);
        const scenarios = catalog.scenarios || [];
        const meta = scenarios.find((s) => String(s.key) === SCENARIO_KEY) || {};
        const defaults = meta.defaults || {};
        let current = {};
        try {
          current = await curRes.json();
          if (!curRes.ok) current = {};
        } catch (_e) {
          current = {};
        }
        this.bind(root, onSubmit, meta, catalog, defaults);
        this.applyValues(root, current, defaults);
      } catch (err) {
        this.setStatus(root, `加载失败：${err.message || err}`, true);
      }
    },
  };

  global.YahaTradeUnionEntrancePanel = YahaTradeUnionEntrancePanel;
  global.isYahaTradeUnionEntranceCapItem = (item) =>
    String(item?.registry_id || '').trim() === REGISTRY_ID;
}(typeof window !== 'undefined' ? window : globalThis));