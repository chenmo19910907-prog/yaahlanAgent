/**
 * Web Agent · Yaha 盘古（Application.yaha_task_show_switch）
 */
(function (global) {
  'use strict';

  const REGISTRY_ID = 'yaha_pangu_task_show_switch';
  const SCENARIO_KEY = 'yaha_task_show_switch';
  const LS_PREFIX = 'web_agent_yaha_pangu_config_value';

  const YahaPanguPanel = {
    renderShell() {
      return `<div class="guild-pangu-panel" data-yaha-pangu-panel>
        <p class="guild-pangu-env-hint">预上线 stage · <code>Application.yaha_task_show_switch</code></p>
        <div class="guild-pangu-usage" data-yp-usage></div>
        <label class="guild-pangu-field">
          <span>展示开关 <em class="guild-pangu-field-tag">1 开 / 0 关</em></span>
          <select data-yp-value>
            <option value="1">1 — 展示每日任务</option>
            <option value="0">0 — 隐藏每日任务</option>
          </select>
          <small data-yp-value-help></small>
        </label>
        <p class="guild-pangu-field" data-yp-current-wrap hidden>
          <span>当前线上值</span>
          <code data-yp-current></code>
        </p>
        <div class="guild-pangu-actions">
          <button type="button" class="btn primary" data-yp-run>生成执行提示</button>
        </div>
        <p class="guild-pangu-status" data-yp-status hidden></p>
      </div>`;
    },

    setStatus(root, text, isError) {
      const el = root.querySelector('[data-yp-status]');
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
      const usageEl = root.querySelector('[data-yp-usage]');
      const help = root.querySelector('[data-yp-value-help]');
      const usage = [meta.usageNote, meta.example ? `举例：${meta.example}` : '']
        .filter(Boolean)
        .join('\n');
      if (usageEl) usageEl.textContent = usage || catalog?.docNote || '';
      const fh = meta.fieldHelp || catalog?.web_usage?.field_help || {};
      if (help) help.textContent = fh.configValue || '';
    },

    applyValues(root, values) {
      const sel = root.querySelector('[data-yp-value]');
      let v = '';
      try {
        v = localStorage.getItem(LS_PREFIX) || '';
      } catch (_e) {
        /* ignore */
      }
      if (!v && values && values.configValue != null) v = String(values.configValue);
      if (sel && (v === '0' || v === '1')) sel.value = v;
      const cur = root.querySelector('[data-yp-current]');
      const wrap = root.querySelector('[data-yp-current-wrap]');
      if (cur && values && values.configValue != null && String(values.configValue) !== '') {
        cur.textContent = String(values.configValue);
        if (wrap) wrap.hidden = false;
      }
    },

    buildPrompt(root) {
      const val = root.querySelector('[data-yp-value]')?.value?.trim() || '1';
      return [
        '请执行 Yaha 每日任务展示开关盘古配置（预上线 stage 保存并全量发布）。',
        '配置：Application.yaha_task_show_switch',
        `configValue=${val}（1 展示 / 0 隐藏）`,
        '',
        `命令：python3 workflow/workflow_execute.py run yaha-pangu-task-show-switch --config-value ${val}`,
      ].join('\n');
    },

    bind(root, onSubmit, meta, catalog) {
      root.querySelector('[data-yp-value]')?.addEventListener('change', () => {
        try {
          localStorage.setItem(LS_PREFIX, root.querySelector('[data-yp-value]')?.value || '');
        } catch (_e) {
          /* ignore */
        }
      });
      root.querySelector('[data-yp-run]')?.addEventListener('click', () => {
        try {
          localStorage.setItem(LS_PREFIX, root.querySelector('[data-yp-value]')?.value || '');
        } catch (_e) {
          /* ignore */
        }
        const text = this.buildPrompt(root);
        if (typeof onSubmit === 'function') onSubmit(text);
      });
      this.fillUsage(root, meta, catalog);
    },

    async mount(container, onSubmit) {
      container.innerHTML = this.renderShell();
      const root = container.querySelector('[data-yaha-pangu-panel]');
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
        let current = {};
        try {
          current = await curRes.json();
          if (!curRes.ok) current = {};
        } catch (_e) {
          current = {};
        }
        this.bind(root, onSubmit, meta, catalog);
        this.applyValues(root, current);
      } catch (err) {
        this.setStatus(root, `加载失败：${err.message || err}`, true);
      }
    },
  };

  global.YahaPanguPanel = YahaPanguPanel;
  global.isYahaPanguCapItem = (item) =>
    String(item?.registry_id || '').trim() === REGISTRY_ID;
}(typeof window !== 'undefined' ? window : globalThis));