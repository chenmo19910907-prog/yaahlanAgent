/**
 * Web Agent · 币商助理额度盘古（Application.shiftTime.dealerAssistant）
 */
(function (global) {
  'use strict';

  const REGISTRY_ID = 'dealer_pangu_assistant_quota_time';
  const SCENARIO_KEY = 'dealer_assistant_quota';
  const LS_PREFIX = 'web_agent_dealer_pangu_fields_';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
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
          whiteUsers: root.querySelector('[data-dp-white]')?.value?.trim() || '',
          fixedTimeSec: root.querySelector('[data-dp-fixed]')?.value?.trim() || '',
        }),
      );
    } catch (_e) {
      /* ignore */
    }
  }

  const DealerPanguPanel = {
    renderShell() {
      return `<div class="guild-pangu-panel" data-dealer-pangu-panel>
        <p class="guild-pangu-env-hint">预上线 stage · <code>Application.shiftTime.dealerAssistant</code></p>
        <div class="guild-pangu-usage" data-dp-usage></div>
        <label class="guild-pangu-field">
          <span>whiteUsers（币商 id）</span>
          <input type="text" data-dp-white placeholder="逗号分隔币商 userId" />
          <small data-dp-white-help></small>
        </label>
        <label class="guild-pangu-field">
          <span>fixedTimeSec <em class="guild-pangu-field-tag">中东算薪偏移</em></span>
          <input type="text" data-dp-fixed inputmode="numeric" placeholder="1796227200" />
        </label>
        <div class="guild-pangu-actions">
          <button type="button" class="btn primary" data-dp-run>生成执行提示</button>
        </div>
        <p class="guild-pangu-status" data-dp-status hidden></p>
      </div>`;
    },

    setStatus(root, text, isError) {
      const el = root.querySelector('[data-dp-status]');
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

    fillUsage(root, meta, catalog) {
      const usageEl = root.querySelector('[data-dp-usage]');
      const help = root.querySelector('[data-dp-white-help]');
      const usage = [meta.usageNote, meta.example ? `举例：${meta.example}` : '']
        .filter(Boolean)
        .join('\n');
      if (usageEl) usageEl.textContent = usage || catalog?.docNote || '';
      const fh = meta.fieldHelp || catalog?.web_usage?.field_help || {};
      if (help) help.textContent = fh.whiteUsers || '';
    },

    applyValues(root, values, defaults) {
      const saved = loadSavedFields();
      const w = root.querySelector('[data-dp-white]');
      const f = root.querySelector('[data-dp-fixed]');
      const defFixed =
        defaults?.fixedTimeSec != null ? String(defaults.fixedTimeSec) : '1796227200';
      if (w) w.value = saved.whiteUsers || values.whiteUsers || '';
      if (f) f.value = saved.fixedTimeSec || values.fixedTimeSec || defFixed;
    },

    buildPrompt(root) {
      const white = root.querySelector('[data-dp-white]')?.value?.trim() || '';
      const fixed = root.querySelector('[data-dp-fixed]')?.value?.trim() || '';
      return [
        '请执行币商助理额度盘古配置（预上线 stage 保存并全量发布）。',
        '配置：Application.shiftTime.dealerAssistant',
        `whiteUsers=${white}`,
        `fixedTimeSec=${fixed}（中东区算薪结算时刻）`,
        '',
        `命令：python3 workflow/workflow_execute.py run dealer-pangu-assistant-quota-time --white-users "${white}" --fixed-time-sec ${fixed}`,
      ].join('\n');
    },

    bind(root, onSubmit, meta, catalog) {
      root.querySelector('[data-dp-white]')?.addEventListener('input', () => saveFieldsFromRoot(root));
      root.querySelector('[data-dp-fixed]')?.addEventListener('input', () => saveFieldsFromRoot(root));
      root.querySelector('[data-dp-run]')?.addEventListener('click', () => {
        saveFieldsFromRoot(root);
        const text = this.buildPrompt(root);
        if (typeof onSubmit === 'function') onSubmit(text);
      });
      this.fillUsage(root, meta, catalog);
    },

    async mount(container, onSubmit) {
      container.innerHTML = this.renderShell();
      const root = container.querySelector('[data-dealer-pangu-panel]');
      if (!root) return;
      try {
        const res = await fetch('/api/dealer/pangu/scenarios', { credentials: 'same-origin' });
        const catalog = await res.json();
        if (!res.ok) throw new Error(catalog.error || `HTTP ${res.status}`);
        const scenarios = catalog.scenarios || [];
        const meta = scenarios.find((s) => String(s.key) === SCENARIO_KEY) || {};
        this.bind(root, onSubmit, meta, catalog);
        this.applyValues(root, {}, meta.defaults || { fixedTimeSec: '1796227200' });
      } catch (err) {
        this.setStatus(root, `加载失败：${err.message || err}`, true);
      }
    },
  };

  global.DealerPanguPanel = DealerPanguPanel;
  global.isDealerPanguCapItem = (item) =>
    String(item?.registry_id || '').trim() === REGISTRY_ID;
}(typeof window !== 'undefined' ? window : globalThis));