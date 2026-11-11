/**
 * Web Agent · 写回翻译文档（五阶段 + 多语言词条表）
 */
(function (global) {
  'use strict';

  const REGISTRY_ID = 'multilang_doc_writeback';
  const MULTILANG_URL_LS = 'web_agent_cmr_multilang_url';
  const SHEET_URL_LS = 'web_agent_cmr_sheet_url';
  const SHEET_NAME_LS = 'web_agent_cmr_sheet_name';
  const USER_NOTE_LS_PREFIX = 'web_agent_cmr_user_note_';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function isCodeMultilangReviewCapItem(item) {
    return String(item?.registry_id || '').trim() === REGISTRY_ID;
  }

  function loadUserNote(scenarioKey) {
    const key = String(scenarioKey || '').trim();
    if (!key) return '';
    try {
      return localStorage.getItem(USER_NOTE_LS_PREFIX + key) || '';
    } catch (_e) {
      return '';
    }
  }

  function saveUserNote(scenarioKey, text) {
    const key = String(scenarioKey || '').trim();
    if (!key) return;
    try {
      localStorage.setItem(USER_NOTE_LS_PREFIX + key, String(text || ''));
    } catch (_e) {
      /* ignore */
    }
  }

  function loadMultilangUrl() {
    try {
      return localStorage.getItem(MULTILANG_URL_LS) || '';
    } catch (_e) {
      return '';
    }
  }

  function saveMultilangUrl(url) {
    try {
      localStorage.setItem(MULTILANG_URL_LS, String(url || ''));
    } catch (_e) {
      /* ignore */
    }
  }

  function loadSheetUrl() {
    try {
      return localStorage.getItem(SHEET_URL_LS) || '';
    } catch (_e) {
      return '';
    }
  }

  function saveSheetUrl(url) {
    try {
      localStorage.setItem(SHEET_URL_LS, String(url || ''));
    } catch (_e) {
      /* ignore */
    }
  }

  function loadSheetName() {
    try {
      return localStorage.getItem(SHEET_NAME_LS) || '';
    } catch (_e) {
      return '';
    }
  }

  function saveSheetName(name) {
    try {
      localStorage.setItem(SHEET_NAME_LS, String(name || ''));
    } catch (_e) {
      /* ignore */
    }
  }

  function scenarioGuideItemHtml(s) {
    const name = escapeHtml(s.name || '');
    const skey = escapeHtml(String(s.key || ''));
    const usage = String(s.usageNote || '').trim();
    if (usage.length > 120) {
      return `<li data-cmr-guide-key="${skey}">
        <details class="guild-pangu-guide-details">
          <summary><strong>${name}</strong> — 展开查看完整说明</summary>
          <p class="guild-pangu-guide-full">${escapeHtml(usage)}</p>
        </details>
      </li>`;
    }
    return `<li data-cmr-guide-key="${skey}"><strong>${name}</strong> ${escapeHtml(usage)}</li>`;
  }

  const CodeMultilangReviewPanel = {
    REGISTRY_ID,
    _catalog: null,
    _currentScenario: 'full',

    renderShell() {
      return `<div class="guild-pangu-panel" data-cmr-panel="1">
        <div class="guild-pangu-status" data-cmr-status hidden></div>
        <section class="guild-pangu-form-wrap">
          <h4 class="guild-pangu-form-title">五阶段工作流 · 多语言</h4>
          <p class="guild-pangu-doc-note" data-cmr-doc-note hidden></p>
          <p class="guild-pangu-env" data-cmr-env></p>
          <p class="guild-pangu-guide-lead">六条入口（含全流程；选中后下方展示同一份阶段说明）：</p>
          <ul class="guild-pangu-scenario-guide" data-cmr-scenario-guide></ul>
          <p class="guild-pangu-form-lead">填写多语言文档与版本表链接后点「填入提问栏」；结果写入 <strong>I/J/K</strong>（服务端/Android/iOS）。</p>
          <label class="guild-pangu-field">
            <span>执行入口</span>
            <select data-cmr-scenario disabled><option>加载中…</option></select>
          </label>
          <div class="guild-pangu-usage-block">
            <div class="guild-pangu-field guild-pangu-usage-readonly-wrap">
              <span>阶段说明（来自仓库 DevCode 配置，只读）</span>
              <pre class="guild-pangu-usage-readonly" data-cmr-usage-note></pre>
            </div>
            <label class="guild-pangu-field">
              <span>补充说明（可编辑，按入口保存在本浏览器）</span>
              <textarea rows="4" data-cmr-user-note autocomplete="off" placeholder="版本号、Sheet 名、指定仓库/分支等。"></textarea>
            </label>
          </div>
          <label class="guild-pangu-field">
            <span>多语言词条文档</span>
            <input type="url" data-cmr-multilang-url autocomplete="off" placeholder="https://alidocs.dingtalk.com/i/nodes/..." />
          </label>
          <p class="guild-pangu-field-help" data-cmr-multilang-url-help></p>
          <label class="guild-pangu-field">
            <span>版本测试表（含 I/J/K 列）</span>
            <input type="url" data-cmr-sheet-url autocomplete="off" placeholder="https://alidocs.dingtalk.com/i/nodes/..." />
          </label>
          <p class="guild-pangu-field-help" data-cmr-sheet-url-help></p>
          <label class="guild-pangu-field">
            <span>Sheet 名（可选）</span>
            <input type="text" data-cmr-sheet-name autocomplete="off" placeholder="留空则由 Agent 列举确认" />
          </label>
          <div class="guild-pangu-actions">
            <button type="button" class="guild-pangu-btn primary" data-cmr-run>填入提问栏</button>
          </div>
        </section>
      </div>`;
    },

    async loadCatalog() {
      if (this._catalog) return this._catalog;
      const res = await fetch('/api/devcode/code-multilang-review/scenarios', { credentials: 'same-origin' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      this._catalog = data;
      return data;
    },

    renderFormHeader(root, catalog) {
      const web = catalog.web_usage || {};
      const docEl = root.querySelector('[data-cmr-doc-note]');
      const docNote = String(catalog.docNote || '').trim();
      if (docEl) {
        if (docNote) {
          docEl.hidden = false;
          docEl.textContent = docNote;
        } else {
          docEl.hidden = true;
          docEl.textContent = '';
        }
      }
      const envEl = root.querySelector('[data-cmr-env]');
      if (envEl) envEl.textContent = web.env_hint || '';
      const fh = web.field_help || {};
      const mlHelp = root.querySelector('[data-cmr-multilang-url-help]');
      if (mlHelp) mlHelp.textContent = fh.multilangDocUrl || '';
      const urlHelp = root.querySelector('[data-cmr-sheet-url-help]');
      if (urlHelp) urlHelp.textContent = fh.sheetUrl || '';

      const guideEl = root.querySelector('[data-cmr-scenario-guide]');
      if (!guideEl) return;
      const scenarios = (catalog.scenarios || []).filter((s) => String(s.key) !== 'full');
      guideEl.innerHTML = scenarios.map((s) => scenarioGuideItemHtml(s)).join('');
    },

    fillScenarioSelect(root, catalog) {
      const sel = root.querySelector('[data-cmr-scenario]');
      if (!sel) return;
      const scenarios = catalog.scenarios || [];
      sel.innerHTML = scenarios
        .map(
          (s) =>
            `<option value="${escapeHtml(String(s.key || ''))}">${escapeHtml(s.name || s.key || '')}</option>`,
        )
        .join('');
      sel.disabled = !scenarios.length;
      if (scenarios.length && !this._currentScenario) {
        this._currentScenario = String(scenarios[0].key || 'full');
      }
      if (this._currentScenario) sel.value = this._currentScenario;
    },

    scenarioMeta(catalog, key) {
      return (catalog.scenarios || []).find((s) => String(s.key) === String(key)) || null;
    },

    highlightGuideItem(root, key) {
      if (String(key) === 'full') {
        root.querySelectorAll('[data-cmr-guide-key]').forEach((li) => li.classList.remove('is-active'));
        return;
      }
      root.querySelectorAll('[data-cmr-guide-key]').forEach((li) => {
        li.classList.toggle('is-active', li.getAttribute('data-cmr-guide-key') === String(key));
      });
    },

    updateScenarioDetail(root, catalog, key) {
      const meta = this.scenarioMeta(catalog, key);
      const usageEl = root.querySelector('[data-cmr-usage-note]');
      this.highlightGuideItem(root, key);
      if (!meta) {
        if (usageEl) usageEl.textContent = '';
        this.syncUserNoteField(root, '');
        return;
      }
      const usage = String(meta.usageNote || '').trim();
      if (usageEl) {
        usageEl.textContent =
          usage || '（该入口暂无说明；请改 DevCode/config/code_multilang_review_panel.json）';
      }
      this.syncUserNoteField(root, key);
    },

    syncUserNoteField(root, key) {
      const ta = root.querySelector('[data-cmr-user-note]');
      if (!ta) return;
      ta.value = loadUserNote(key);
    },

    syncUrlFields(root, catalog) {
      const ml = root.querySelector('[data-cmr-multilang-url]');
      const url = root.querySelector('[data-cmr-sheet-url]');
      const name = root.querySelector('[data-cmr-sheet-name]');
      const storedMl = loadMultilangUrl();
      const defaultMl = String(catalog?.defaultMultilangDocUrl || '').trim();
      if (ml) ml.value = storedMl || defaultMl;
      if (url) url.value = loadSheetUrl();
      if (name) name.value = loadSheetName();
    },

    setStatus(root, text, isError) {
      const el = root.querySelector('[data-cmr-status]');
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

    buildPrompt(root, catalog) {
      const sel = root.querySelector('[data-cmr-scenario]');
      const key = sel ? String(sel.value || '').trim() : 'full';
      const meta = this.scenarioMeta(catalog, key);
      const name = meta?.name || key;
      const multilangUrl = root.querySelector('[data-cmr-multilang-url]')?.value?.trim() || '';
      const sheetUrl = root.querySelector('[data-cmr-sheet-url]')?.value?.trim() || '';
      const sheetName = root.querySelector('[data-cmr-sheet-name]')?.value?.trim() || '';
      const userNote = root.querySelector('[data-cmr-user-note]')?.value?.trim() || '';
      const skill = catalog.skillPath || '.cursor/skills/code-multilang-review/SKILL.md';
      const docUrl = multilangUrl || sheetUrl;
      const tpl = meta?.promptTemplate || '写回翻译文档校验结果 <multilangDocUrl>';
      const promptLine = tpl
        .replace(/<multilangDocUrl>/g, docUrl || '<翻译表URL>')
        .replace(/<sheetUrl>/g, docUrl || '<翻译表URL>');

      const lines = [
        `请执行写回翻译文档：「${name}」（${key}）。`,
        promptLine,
      ];
      if (docUrl) lines.push('', `翻译/多语言词条表：${docUrl}`);
      if (sheetName) lines.push(`Sheet：${sheetName}`);
      const usage = String(meta?.usageNote || '').trim();
      if (usage) {
        lines.push('', '【阶段说明（仓库）】', usage);
      }
      if (userNote) {
        lines.push('', '【补充说明（操作人）】', userNote);
      }
      lines.push(
        '',
        `Skill：${skill}`,
        '前置：python3 DevCode/voga_pull_execute.py',
        '约束：voga-repos 只读；翻译表仅写 I/J/K/L（L=H5）',
        'registry：multilang_doc_writeback',
      );
      return lines.join('\n');
    },

    bind(root, onSubmit) {
      const sel = root.querySelector('[data-cmr-scenario]');
      const userNoteEl = root.querySelector('[data-cmr-user-note]');
      const multilangEl = root.querySelector('[data-cmr-multilang-url]');
      const sheetUrlEl = root.querySelector('[data-cmr-sheet-url]');
      const sheetNameEl = root.querySelector('[data-cmr-sheet-name]');

      sel?.addEventListener('change', async () => {
        this._currentScenario = String(sel.value || '');
        const catalog = await this.loadCatalog();
        this.updateScenarioDetail(root, catalog, this._currentScenario);
      });
      userNoteEl?.addEventListener('input', () => {
        const key = sel ? String(sel.value || '').trim() : '';
        saveUserNote(key, userNoteEl.value);
      });
      multilangEl?.addEventListener('input', () => saveMultilangUrl(multilangEl.value));
      sheetUrlEl?.addEventListener('input', () => saveSheetUrl(sheetUrlEl.value));
      sheetNameEl?.addEventListener('input', () => saveSheetName(sheetNameEl.value));

      root.querySelector('[data-cmr-run]')?.addEventListener('click', async () => {
        try {
          const catalog = await this.loadCatalog();
          const key = sel ? String(sel.value || '').trim() : '';
          saveUserNote(key, userNoteEl?.value || '');
          saveMultilangUrl(multilangEl?.value || '');
          saveSheetUrl(sheetUrlEl?.value || '');
          saveSheetName(sheetNameEl?.value || '');
          const text = this.buildPrompt(root, catalog);
          if (typeof onSubmit === 'function') onSubmit(text);
        } catch (err) {
          this.setStatus(root, err.message || String(err), true);
        }
      });
    },

    async mount(container, onSubmit) {
      container.innerHTML = this.renderShell();
      const root = container.querySelector('[data-cmr-panel]');
      if (!root) return;
      try {
        const catalog = await this.loadCatalog();
        this.renderFormHeader(root, catalog);
        this.fillScenarioSelect(root, catalog);
        this.syncUrlFields(root, catalog);
        this.updateScenarioDetail(root, catalog, root.querySelector('[data-cmr-scenario]')?.value);
        this.bind(root, onSubmit);
      } catch (err) {
        this.setStatus(root, `加载失败：${err.message || err}`, true);
      }
    },
  };

  global.CodeMultilangReviewPanel = CodeMultilangReviewPanel;
  global.isCodeMultilangReviewCapItem = isCodeMultilangReviewCapItem;
}(typeof window !== 'undefined' ? window : globalThis));
