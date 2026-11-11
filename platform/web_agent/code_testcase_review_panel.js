/**
 * Web Agent · 代码×用例交叉审查（五阶段工作流 + 钉钉表链接）
 */
(function (global) {
  'use strict';

  const REGISTRY_ID = 'code_testcase_review';
  const SHEET_URL_LS = 'web_agent_ctr_sheet_url';
  const SHEET_NAME_LS = 'web_agent_ctr_sheet_name';
  const USER_NOTE_LS_PREFIX = 'web_agent_ctr_user_note_';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function isCodeTestcaseReviewCapItem(item) {
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

  function scenarioFlowBtnHtml(s) {
    const skey = escapeHtml(String(s.key || ''));
    const name = escapeHtml(s.name || skey);
    const tip = escapeHtml(String(s.guideShort || '').trim() || String(s.usageNote || '').trim());
    const titleAttr = tip ? ` title="${tip}"` : '';
    return `<button type="button" class="guild-pangu-flow-step" data-ctr-guide-key="${skey}" data-ctr-pick="${skey}"${titleAttr}>${name}</button>`;
  }

  const CodeTestcaseReviewPanel = {
    REGISTRY_ID,
    _catalog: null,
    _currentScenario: 'full',

    renderShell() {
      return `<div class="guild-pangu-panel" data-ctr-panel="1">
        <div class="guild-pangu-status" data-ctr-status hidden></div>
        <section class="guild-pangu-form-wrap">
          <header class="guild-pangu-form-head">
            <h4 class="guild-pangu-form-title" data-ctr-panel-title>代码×用例交叉审查</h4>
            <span class="guild-pangu-form-badge">五阶段</span>
          </header>
          <p class="guild-pangu-doc-note" data-ctr-doc-note hidden></p>
          <p class="guild-pangu-env guild-pangu-env--compact" data-ctr-env></p>
          <nav class="guild-pangu-flow" data-ctr-scenario-guide role="tablist" aria-label="工作流阶段"></nav>
          <p class="guild-pangu-form-lead guild-pangu-form-lead--compact">点阶段可切换入口；填链接后「填入提问栏」。</p>
          <label class="guild-pangu-field">
            <span>执行入口</span>
            <select data-ctr-scenario disabled><option>加载中…</option></select>
          </label>
          <div class="guild-pangu-usage-block guild-pangu-usage-block--slim">
            <p class="guild-pangu-usage-readonly" data-ctr-usage-note></p>
            <label class="guild-pangu-field guild-pangu-field--compact">
              <span>补充说明 <em class="guild-pangu-field-tag">本机保存</em></span>
              <textarea rows="2" data-ctr-user-note autocomplete="off" placeholder="Sheet 名、范围、指定仓…"></textarea>
            </label>
          </div>
          <label class="guild-pangu-field guild-pangu-field--primary is-primary-field">
            <span>钉钉用例表 <em class="guild-pangu-field-tag">必填</em></span>
            <input type="url" data-ctr-sheet-url autocomplete="off" placeholder="https://alidocs.dingtalk.com/i/nodes/..." />
          </label>
          <p class="guild-pangu-field-help" data-ctr-sheet-url-help></p>
          <label class="guild-pangu-field is-secondary-field">
            <span>Sheet 名 <em class="guild-pangu-field-tag">可选</em></span>
            <input type="text" data-ctr-sheet-name autocomplete="off" placeholder="留空自动列举" />
          </label>
          <div class="guild-pangu-actions">
            <button type="button" class="guild-pangu-btn primary" data-ctr-run>填入提问栏</button>
          </div>
        </section>
      </div>`;
    },

    async loadCatalog() {
      if (this._catalog) return this._catalog;
      const res = await fetch('/api/devcode/code-testcase-review/scenarios', { credentials: 'same-origin' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      this._catalog = data;
      return data;
    },

    renderFormHeader(root, catalog) {
      const web = catalog.web_usage || {};
      const titleEl = root.querySelector('[data-ctr-panel-title]');
      const panelTitle = String(catalog.panelTitle || web.title || '').trim();
      if (titleEl && panelTitle) titleEl.textContent = panelTitle;
      const docEl = root.querySelector('[data-ctr-doc-note]');
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
      const envEl = root.querySelector('[data-ctr-env]');
      if (envEl) envEl.textContent = web.env_hint || '';
      const urlHelp = root.querySelector('[data-ctr-sheet-url-help]');
      const fh = web.field_help || {};
      if (urlHelp) urlHelp.textContent = fh.sheetUrl || '';

      const guideEl = root.querySelector('[data-ctr-scenario-guide]');
      if (!guideEl) return;
      const scenarios = (catalog.scenarios || []).filter((s) => String(s.key) !== 'full');
      guideEl.innerHTML = scenarios
        .map((s, i) => {
          const sep = i > 0 ? '<span class="guild-pangu-flow-arrow" aria-hidden="true">→</span>' : '';
          return sep + scenarioFlowBtnHtml(s);
        })
        .join('');
    },

    fillScenarioSelect(root, catalog) {
      const sel = root.querySelector('[data-ctr-scenario]');
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
      const activeKey = String(key) === 'full' ? '' : String(key);
      root.querySelectorAll('[data-ctr-guide-key]').forEach((el) => {
        el.classList.toggle('is-active', activeKey && el.getAttribute('data-ctr-guide-key') === activeKey);
      });
    },

    updateScenarioDetail(root, catalog, key) {
      const meta = this.scenarioMeta(catalog, key);
      const usageEl = root.querySelector('[data-ctr-usage-note]');
      this.highlightGuideItem(root, key);
      if (!meta) {
        if (usageEl) {
          usageEl.textContent = '';
          usageEl.hidden = true;
        }
        this.syncUserNoteField(root, '');
        return;
      }
      const usage = String(meta.usageNote || '').trim();
      if (usageEl) {
        usageEl.textContent = usage || '（暂无说明）';
        usageEl.hidden = !usage;
      }
      this.syncUserNoteField(root, key);
    },

    syncUserNoteField(root, key) {
      const ta = root.querySelector('[data-ctr-user-note]');
      if (!ta) return;
      ta.value = loadUserNote(key);
    },

    syncSheetFields(root) {
      const url = root.querySelector('[data-ctr-sheet-url]');
      const name = root.querySelector('[data-ctr-sheet-name]');
      if (url) url.value = loadSheetUrl();
      if (name) name.value = loadSheetName();
    },

    setStatus(root, text, isError) {
      const el = root.querySelector('[data-ctr-status]');
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
      const sel = root.querySelector('[data-ctr-scenario]');
      const key = sel ? String(sel.value || '').trim() : 'full';
      const meta = this.scenarioMeta(catalog, key);
      const name = meta?.name || key;
      const sheetUrl = root.querySelector('[data-ctr-sheet-url]')?.value?.trim() || '';
      const sheetName = root.querySelector('[data-ctr-sheet-name]')?.value?.trim() || '';
      const userNote = root.querySelector('[data-ctr-user-note]')?.value?.trim() || '';
      const skill = catalog.skillPath || '.cursor/skills/code-testcase-review/SKILL.md';
      const tpl = meta?.promptTemplate || '用例覆盖率分析 <sheetUrl>';
      const promptLine = tpl.replace(/<sheetUrl>/g, sheetUrl || '<钉钉用例表URL>');

      const lines = [
        `请执行代码×用例交叉审查：「${name}」（${key}）。`,
        promptLine,
      ];
      if (sheetUrl) lines.push('', `钉钉用例表：${sheetUrl}`);
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
        '约束：voga-repos 只读；钉钉表仅写 E/F',
        'registry：code_testcase_review',
      );
      return lines.join('\n');
    },

    bind(root, onSubmit) {
      const sel = root.querySelector('[data-ctr-scenario]');
      const userNoteEl = root.querySelector('[data-ctr-user-note]');
      const sheetUrlEl = root.querySelector('[data-ctr-sheet-url]');
      const sheetNameEl = root.querySelector('[data-ctr-sheet-name]');

      root.querySelectorAll('[data-ctr-pick]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const pick = String(btn.getAttribute('data-ctr-pick') || '').trim();
          if (!pick || !sel) return;
          sel.value = pick;
          this._currentScenario = pick;
          const catalog = await this.loadCatalog();
          this.updateScenarioDetail(root, catalog, pick);
        });
      });
      sel?.addEventListener('change', async () => {
        this._currentScenario = String(sel.value || '');
        const catalog = await this.loadCatalog();
        this.updateScenarioDetail(root, catalog, this._currentScenario);
      });
      userNoteEl?.addEventListener('input', () => {
        const key = sel ? String(sel.value || '').trim() : '';
        saveUserNote(key, userNoteEl.value);
      });
      sheetUrlEl?.addEventListener('input', () => saveSheetUrl(sheetUrlEl.value));
      sheetNameEl?.addEventListener('input', () => saveSheetName(sheetNameEl.value));

      root.querySelector('[data-ctr-run]')?.addEventListener('click', async () => {
        try {
          const catalog = await this.loadCatalog();
          const key = sel ? String(sel.value || '').trim() : '';
          saveUserNote(key, userNoteEl?.value || '');
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
      const root = container.querySelector('[data-ctr-panel]');
      if (!root) return;
      try {
        const catalog = await this.loadCatalog();
        this.renderFormHeader(root, catalog);
        this.fillScenarioSelect(root, catalog);
        this.syncSheetFields(root);
        this.updateScenarioDetail(root, catalog, root.querySelector('[data-ctr-scenario]')?.value);
        this.bind(root, onSubmit);
      } catch (err) {
        this.setStatus(root, `加载失败：${err.message || err}`, true);
      }
    },
  };

  global.CodeTestcaseReviewPanel = CodeTestcaseReviewPanel;
  global.isCodeTestcaseReviewCapItem = isCodeTestcaseReviewCapItem;
}(typeof window !== 'undefined' ? window : globalThis));
