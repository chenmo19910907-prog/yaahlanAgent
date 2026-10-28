/**
 * Web Agent · 公会盘古统一配置面板（改参并发布 + 场景说明 + 白名单 + 三时间字段预填）
 */
(function (global) {
  'use strict';

  const REGISTRY_ID = 'guild_pangu_shift_config';
  const USER_NOTE_LS_PREFIX = 'web_agent_guild_pangu_user_note_';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function isGuildPanguCapItem(item) {
    return String(item?.registry_id || '').trim() === REGISTRY_ID;
  }

  function onlyEditFields(meta) {
    const raw = meta?.onlyEditFields || meta?.editFields || meta?.fields || [];
    return Array.isArray(raw) ? raw.map((f) => String(f)) : [];
  }

  function onlyEditShort(meta) {
    const names = onlyEditFields(meta);
    return names.length ? `仅修改 ${names.join('、')}，其他字段请勿改动。` : '';
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
      /* ignore quota / private mode */
    }
  }

  function scenarioGuideItemHtml(s) {
    const name = escapeHtml(s.name || '');
    const skey = escapeHtml(String(s.key || ''));
    const short = escapeHtml(onlyEditShort(s));
    const usage = String(s.usageNote || '').trim();
    if (usage) {
      const ex = String(s.example || '').trim();
      const exBlock = ex && !usage.includes(ex)
        ? `<p class="guild-pangu-guide-ex">举例：${escapeHtml(ex)}</p>`
        : '';
      return `<li data-gp-guide-key="${skey}">
        <details class="guild-pangu-guide-details">
          <summary><strong>${name}</strong> — ${short || '展开查看完整说明'}</summary>
          <p class="guild-pangu-guide-full">${escapeHtml(usage)}</p>
          ${exBlock}
        </details>
      </li>`;
    }
    const extra = s.extraNote ? `${escapeHtml(s.extraNote)} ` : '';
    const ex = String(s.example || '').trim();
    const exampleText = ex ? `举例：${escapeHtml(ex)}` : '';
    const body = [short, extra, exampleText].filter(Boolean).join(' ');
    return `<li data-gp-guide-key="${skey}"><strong>${name}</strong> ${body}</li>`;
  }

  const GuildPanguPanel = {
    REGISTRY_ID,
    _catalog: null,
    _currentScenario: '',

    renderShell() {
      return `<div class="guild-pangu-panel" data-guild-pangu-panel="1">
        <div class="guild-pangu-status" data-gp-status hidden></div>
        <section class="guild-pangu-form-wrap">
          <h4 class="guild-pangu-form-title">改参并发布</h4>
          <p class="guild-pangu-doc-note" data-gp-doc-note hidden></p>
          <p class="guild-pangu-env" data-gp-env></p>
          <p class="guild-pangu-guide-lead">九条业务说明（可展开查看完整文案；选中场景后下方也会展示同一份说明）：</p>
          <ul class="guild-pangu-scenario-guide" data-gp-scenario-guide></ul>
          <p class="guild-pangu-form-lead">选择业务场景后，下方会代入<strong>当前预上线配置</strong>；只改说明里要求改的字段即可。</p>
          <label class="guild-pangu-field">
            <span>业务场景</span>
            <select data-gp-scenario disabled><option>加载中…</option></select>
          </label>
          <p class="guild-pangu-edit-fields" data-gp-edit-fields></p>
          <div class="guild-pangu-usage-block">
            <div class="guild-pangu-field guild-pangu-usage-readonly-wrap">
              <span>场景说明（来自仓库 workflow 配置，只读）</span>
              <pre class="guild-pangu-usage-readonly" data-gp-usage-note></pre>
            </div>
            <label class="guild-pangu-field">
              <span>补充说明（可编辑，按场景保存在本浏览器；会写入提问栏）</span>
              <textarea rows="5" data-gp-user-note autocomplete="off" placeholder="可粘贴业务文档里的长说明、验收步骤、账号用途等；留空则不写入提问栏。"></textarea>
            </label>
          </div>
          <label class="guild-pangu-field">
            <span>whiteUsers（逗号分隔 userId）</span>
            <input type="text" data-gp-white autocomplete="off" placeholder="100447582,4295973599" />
          </label>
          <p class="guild-pangu-field-help" data-gp-white-help></p>
          <div class="guild-pangu-time-row">
            <label class="guild-pangu-field" data-gp-field="fixedTimeSec">
              <span>fixedTimeSec <em class="guild-pangu-field-tag" data-gp-tag="fixedTimeSec"></em></span>
              <input type="text" data-gp-fixed autocomplete="off" inputmode="numeric" />
            </label>
            <label class="guild-pangu-field" data-gp-field="expireTimeSec">
              <span>expireTimeSec <em class="guild-pangu-field-tag" data-gp-tag="expireTimeSec"></em></span>
              <input type="text" data-gp-expire autocomplete="off" inputmode="numeric" />
            </label>
            <label class="guild-pangu-field" data-gp-field="shiftTime">
              <span>shiftTime <em class="guild-pangu-field-tag" data-gp-tag="shiftTime"></em></span>
              <input type="text" data-gp-shift autocomplete="off" inputmode="numeric" />
            </label>
          </div>
          <div class="guild-pangu-actions">
            <button type="button" class="guild-pangu-btn secondary" data-gp-refresh>刷新当前值</button>
            <button type="button" class="guild-pangu-btn primary" data-gp-run>填入提问栏</button>
          </div>
        </section>
      </div>`;
    },

    async loadCatalog() {
      if (this._catalog) return this._catalog;
      const res = await fetch('/api/guild/pangu/scenarios', { credentials: 'same-origin' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      this._catalog = data;
      return data;
    },

    renderFormHeader(root, catalog) {
      const web = catalog.web_usage || {};
      const docEl = root.querySelector('[data-gp-doc-note]');
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
      const envEl = root.querySelector('[data-gp-env]');
      if (envEl) envEl.textContent = web.env_hint || '';
      const whiteHelp = root.querySelector('[data-gp-white-help]');
      const fh = web.field_help || {};
      if (whiteHelp) whiteHelp.textContent = fh.whiteUsers || '';

      const guideEl = root.querySelector('[data-gp-scenario-guide]');
      if (!guideEl) return;
      guideEl.innerHTML = (catalog.scenarios || []).map((s) => scenarioGuideItemHtml(s)).join('');
    },

    fillScenarioSelect(root, catalog) {
      const sel = root.querySelector('[data-gp-scenario]');
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
        this._currentScenario = String(scenarios[0].key || '');
      }
      if (this._currentScenario) sel.value = this._currentScenario;
    },

    scenarioMeta(catalog, key) {
      return (catalog.scenarios || []).find((s) => String(s.key) === String(key)) || null;
    },

    highlightGuideItem(root, key) {
      root.querySelectorAll('[data-gp-guide-key]').forEach((li) => {
        li.classList.toggle('is-active', li.getAttribute('data-gp-guide-key') === String(key));
      });
    },

    updateFieldHighlights(root, meta) {
      const editFields = new Set(onlyEditFields(meta));
      const hint = root.querySelector('[data-gp-edit-fields]');
      if (hint) {
        const names = [...editFields];
        hint.textContent = names.length
          ? `当前场景：${onlyEditShort(meta)}（下方三时间字段已代入预上线当前值。）`
          : '';
      }
      ['fixedTimeSec', 'expireTimeSec', 'shiftTime'].forEach((name) => {
        const label = root.querySelector(`[data-gp-field="${name}"]`);
        const tag = root.querySelector(`[data-gp-tag="${name}"]`);
        const active = editFields.has(name);
        if (label) label.classList.toggle('is-primary-field', active);
        if (label) label.classList.toggle('is-secondary-field', !active);
        if (tag) tag.textContent = active ? '需修改' : '保持不动';
      });
    },

    syncUserNoteField(root, key) {
      const ta = root.querySelector('[data-gp-user-note]');
      if (!ta) return;
      ta.value = loadUserNote(key);
    },

    updateScenarioDetail(root, catalog, key) {
      const meta = this.scenarioMeta(catalog, key);
      const usageEl = root.querySelector('[data-gp-usage-note]');
      this.highlightGuideItem(root, key);
      if (!meta) {
        if (usageEl) usageEl.textContent = '';
        this.updateFieldHighlights(root, null);
        this.syncUserNoteField(root, '');
        return;
      }
      const usage = String(meta.usageNote || '').trim();
      if (usageEl) {
        usageEl.textContent = usage || '（该场景暂无长说明；可在下方「补充说明」自行填写，或改仓库 workflow 的 description。）';
      }
      this.updateFieldHighlights(root, meta);
      this.syncUserNoteField(root, key);
    },

    setStatus(root, text, isError) {
      const el = root.querySelector('[data-gp-status]');
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

    applyFormValues(root, values) {
      const w = root.querySelector('[data-gp-white]');
      const f = root.querySelector('[data-gp-fixed]');
      const e = root.querySelector('[data-gp-expire]');
      const sh = root.querySelector('[data-gp-shift]');
      if (w) w.value = values.whiteUsers != null ? String(values.whiteUsers) : '';
      if (f) f.value = values.fixedTimeSec != null ? String(values.fixedTimeSec) : '';
      if (e) e.value = values.expireTimeSec != null ? String(values.expireTimeSec) : '';
      if (sh) sh.value = values.shiftTime != null ? String(values.shiftTime) : '';
    },

    async refreshCurrent(root) {
      const sel = root.querySelector('[data-gp-scenario]');
      const key = sel ? String(sel.value || '').trim() : '';
      if (!key) return;
      this.setStatus(root, '正在读取 MSE 当前值…', false);
      try {
        const res = await fetch(`/api/guild/pangu/current?scenario=${encodeURIComponent(key)}`, {
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

    buildPrompt(root, catalog) {
      const sel = root.querySelector('[data-gp-scenario]');
      const key = sel ? String(sel.value || '').trim() : '';
      const meta = this.scenarioMeta(catalog, key);
      const name = meta?.name || key;
      const white = root.querySelector('[data-gp-white]')?.value?.trim() || '';
      const fixed = root.querySelector('[data-gp-fixed]')?.value?.trim() || '';
      const expire = root.querySelector('[data-gp-expire]')?.value?.trim() || '';
      const shift = root.querySelector('[data-gp-shift]')?.value?.trim() || '';
      const only = onlyEditFields(meta).join('、');
      const usage = String(meta?.usageNote || '').trim();
      const userNote = root.querySelector('[data-gp-user-note]')?.value?.trim() || '';
      const lines = [
        `请执行公会盘古配置：场景「${name}」（${key}），预上线 stage 保存并全量发布。`,
        only ? `仅修改字段：${only}；其他字段保持当前值不变。` : '',
      ];
      if (usage) {
        lines.push('', '【场景说明（仓库）】', usage);
      }
      if (userNote) {
        lines.push('', '【补充说明（操作人）】', userNote);
      }
      lines.push(
        '',
        `whiteUsers=${white}`,
        `fixedTimeSec=${fixed}`,
        `expireTimeSec=${expire}`,
        `shiftTime=${shift}`,
        '',
        `命令：python3 workflow/workflow_execute.py run guild_pangu_shift_config --scenario ${key} --white-users "${white}" --fixed-time-sec ${fixed} --expire-time-sec ${expire} --shift-time ${shift}`,
      );
      return lines.join('\n');
    },

    bind(root, onSubmit) {
      const sel = root.querySelector('[data-gp-scenario]');
      const userNoteEl = root.querySelector('[data-gp-user-note]');
      sel?.addEventListener('change', async () => {
        this._currentScenario = String(sel.value || '');
        const catalog = await this.loadCatalog();
        this.updateScenarioDetail(root, catalog, this._currentScenario);
        await this.refreshCurrent(root);
      });
      userNoteEl?.addEventListener('input', () => {
        const key = sel ? String(sel.value || '').trim() : '';
        saveUserNote(key, userNoteEl.value);
      });
      root.querySelector('[data-gp-refresh]')?.addEventListener('click', () => {
        this.refreshCurrent(root);
      });
      root.querySelector('[data-gp-run]')?.addEventListener('click', async () => {
        try {
          const catalog = await this.loadCatalog();
          const text = this.buildPrompt(root, catalog);
          if (typeof onSubmit === 'function') onSubmit(text);
        } catch (err) {
          this.setStatus(root, err.message || String(err), true);
        }
      });
    },

    async mount(container, onSubmit) {
      container.innerHTML = this.renderShell();
      const root = container.querySelector('[data-guild-pangu-panel]');
      if (!root) return;
      try {
        const catalog = await this.loadCatalog();
        this.renderFormHeader(root, catalog);
        this.fillScenarioSelect(root, catalog);
        this.updateScenarioDetail(root, catalog, root.querySelector('[data-gp-scenario]')?.value);
        this.bind(root, onSubmit);
        await this.refreshCurrent(root);
      } catch (err) {
        this.setStatus(root, `加载失败：${err.message || err}`, true);
      }
    },
  };

  global.GuildPanguPanel = GuildPanguPanel;
  global.isGuildPanguCapItem = isGuildPanguCapItem;
}(typeof window !== 'undefined' ? window : globalThis));
