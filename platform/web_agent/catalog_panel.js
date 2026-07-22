/**
 * 工具台能力目录面板（Web Agent 深色主题版）
 * onRunPrompt(text) — 填参后点击「执行」时回调（填入提问栏，不自动发送）
 */
(function (global) {
  'use strict';

  const PROMPT_PLACEHOLDER_RE = /<([^>]+)>/g;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function smallIcon(name) {
    const icons = {
      module: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true"><path d="M4 5h7v7H4zM13 5h7v7h-7zM4 14h7v5H4zM13 14h7v5h-7z"/></svg>',
      spark: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true"><path d="M12 3l1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
      play: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
    };
    return icons[name] || icons.spark;
  }

  function assemblePromptLine(lineEl) {
    let result = '';
    lineEl.querySelector('.prompt-text').childNodes.forEach(node => {
      if (node.nodeType === Node.TEXT_NODE) {
        result += node.textContent;
      } else if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains('prompt-field')) {
        const val = node.value.trim();
        const key = node.getAttribute('data-key') || node.placeholder;
        result += val || ('<' + key + '>');
      }
    });
    return result;
  }

  function CatalogPanel(options) {
    this.onRunPrompt = options.onRunPrompt || function () {};
    this.root = options.root;
    this.metaEl = options.metaEl;
    this.searchEl = options.searchEl;
    this.navEl = options.navEl;
    this.mainEl = options.mainEl;
    this.envCheckBtn = options.envCheckBtn || null;
    this.DATA = null;
    this.activeModule = 'all';
    this.query = '';
  }

  CatalogPanel.prototype.load = async function load(fetchData) {
    this.DATA = typeof fetchData === 'function' ? await fetchData() : fetchData;
    if (this.metaEl && this.DATA) {
      this.metaEl.textContent = `${this.DATA.module_count} 模块 · ${this.DATA.total_items} 能力`;
    }
    if (this.envCheckBtn) {
      const envCfg = this.DATA.env_check || {};
      if (envCfg.label) this.envCheckBtn.textContent = envCfg.label;
      this.envCheckBtn.onclick = () => {
        this.onRunPrompt(envCfg.prompt || '@新手上手.md 运行环境检查');
      };
    }
    this.renderNav();
    this.render();
  };

  CatalogPanel.prototype.matches = function matches(item, funcLabel, catName, q) {
    if (!q) return true;
    const prompts = (item.prompts || []).join('\n');
    const hay = (funcLabel + '\n' + catName + '\n' + item.name + '\n' +
      (item.source || '') + '\n' + prompts).toLowerCase();
    return hay.includes(q);
  };

  CatalogPanel.prototype.renderPromptLine = function renderPromptLine(text) {
    const spanParts = [];
    let last = 0;
    let m;
    const re = new RegExp(PROMPT_PLACEHOLDER_RE.source, 'g');
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) spanParts.push(escapeHtml(text.slice(last, m.index)));
      const key = m[1];
      const width = Math.min(12, Math.max(4, key.length + 1));
      spanParts.push(
        `<input type="text" class="prompt-field" data-key="${escapeHtml(key)}" ` +
        `placeholder="${escapeHtml(key)}" aria-label="${escapeHtml(key)}" ` +
        `style="width:${width}em">`
      );
      last = re.lastIndex;
    }
    if (last < text.length) spanParts.push(escapeHtml(text.slice(last)));
    return `<div class="prompt-line">
      <span class="prompt-text">${spanParts.join('')}</span>
      <div class="prompt-line-footer">
        <button type="button" class="prompt-run" title="填入提问栏">执行</button>
      </div>
    </div>`;
  };

  CatalogPanel.prototype.renderCapItem = function renderCapItem(item) {
    const prompts = item.prompts || [];
    const hasPrompts = prompts.length > 0;
    const promptHtml = prompts.map(t => this.renderPromptLine(t)).join('');
    const headToggle = hasPrompts ? ' is-toggle' : '';
    const headAria = hasPrompts ? ' aria-expanded="false"' : '';
    const source = item.source
      ? `<span class="source-badge" data-env="${escapeHtml(item.env || '')}" data-source-id="${escapeHtml(item.source_id || '')}">${escapeHtml(item.source)}</span>`
      : '';
    const chevron = hasPrompts ? '<span class="cap-chevron" aria-hidden="true">▸</span>' : '';
    return `<li class="cap">
      <div class="cap-head${headToggle}"${headAria}>
        ${chevron}
        <span class="cap-icon" aria-hidden="true">${smallIcon('spark')}</span>
        <div class="cap-main">
          <span class="cap-name">${escapeHtml(item.name)}</span>
          ${source}
        </div>
      </div>
      <div class="prompt-panel" hidden>${hasPrompts ? `<div class="prompt-list">${promptHtml}</div>` : ''}</div>
    </li>`;
  };

  CatalogPanel.prototype.bindPromptToggles = function bindPromptToggles(root) {
    root.querySelectorAll('.cap-head.is-toggle').forEach(head => {
      head.addEventListener('click', () => {
        const panel = head.closest('.cap').querySelector('.prompt-panel');
        const open = head.getAttribute('aria-expanded') === 'true';
        head.setAttribute('aria-expanded', open ? 'false' : 'true');
        panel.hidden = open;
      });
    });
  };

  CatalogPanel.prototype.bindPromptPanels = function bindPromptPanels(root) {
    this.bindPromptToggles(root);
  };

  CatalogPanel.prototype.renderPlaybookStep = function renderPlaybookStep(step) {
    const ops = (step.operations || []).map(op => `<li>${escapeHtml(op)}</li>`).join('');
    const prompts = (step.prompts || []).map(t => this.renderPromptLine(t)).join('');
    const title = step.workflowName || step.workflowId || step.note || `步骤 ${step.order}`;
    const subParts = [];
    if (step.workflowId && step.workflowName) subParts.push(`<code>${escapeHtml(step.workflowId)}</code>`);
    if (step.sheet) subParts.push(`Sheet「${escapeHtml(step.sheet)}」`);
    const sub = subParts.join(' · ');
    const noteBlock = (step.note && title !== step.note)
      ? `<div class="playbook-step-note">${escapeHtml(step.note)}</div>` : '';
    return `<div class="playbook-step">
      <div class="playbook-step-head" aria-expanded="false">
        <span class="playbook-step-num">${step.order}</span>
        <div>
          <div class="playbook-step-title">${escapeHtml(title)}</div>
          ${sub ? `<div class="playbook-step-sub">${sub}</div>` : ''}
        </div>
      </div>
      <div class="playbook-step-body" hidden>
        ${noteBlock}
        ${ops ? `<ol class="playbook-ops">${ops}</ol>` : ''}
        ${prompts ? `<div class="prompt-list">${prompts}</div>` : ''}
      </div>
    </div>`;
  };

  CatalogPanel.prototype.renderPlaybook = function renderPlaybook(pb) {
    const defaults = Object.entries(pb.defaults || {})
      .map(([k, v]) => `<span class="default-chip"><code>${escapeHtml(k)}</code> ${escapeHtml(v)}</span>`)
      .join('');
    const steps = (pb.steps || []).map(s => this.renderPlaybookStep(s)).join('');
    const topPrompts = (pb.prompts || []).map(t => this.renderPromptLine(t)).join('');
    const stepCount = (pb.steps || []).length;
    return `<section class="playbook-section" id="playbook-${escapeHtml(pb.id)}">
      <div class="playbook-head">
        <h3>${escapeHtml(pb.title)}</h3>
        <p class="playbook-summary">${escapeHtml(pb.summary || '')}</p>
        <div class="playbook-tag-row">
          <span class="playbook-tag">${escapeHtml(pb.category || '工作流')}</span>
          <span class="playbook-tag">${stepCount} 步</span>
        </div>
        ${defaults ? `<div class="playbook-defaults">${defaults}</div>` : ''}
        ${topPrompts ? `<div class="prompt-list" style="margin-top:10px">${topPrompts}</div>` : ''}
      </div>
      <div class="playbook-steps">${steps}</div>
    </section>`;
  };

  CatalogPanel.prototype.bindPlaybookToggles = function bindPlaybookToggles(root) {
    root.querySelectorAll('.playbook-step-head').forEach(head => {
      head.addEventListener('click', () => {
        const body = head.nextElementSibling;
        const open = head.getAttribute('aria-expanded') === 'true';
        head.setAttribute('aria-expanded', open ? 'false' : 'true');
        if (body) body.hidden = open;
      });
    });
  };

  CatalogPanel.prototype.renderPlaybooks = function renderPlaybooks(container) {
    const playbooks = this.DATA.playbooks || [];
    if (!playbooks.length) return;
    if (this.activeModule !== 'all' && this.activeModule !== '工作流') return;
    const wrap = document.createElement('div');
    wrap.innerHTML = playbooks.map(pb => this.renderPlaybook(pb)).join('');
    while (wrap.firstChild) container.appendChild(wrap.firstChild);
    this.bindPlaybookToggles(container);
    this.bindPromptPanels(container);
  };

  CatalogPanel.prototype.render = function render() {
    const q = this.query.trim().toLowerCase();
    const main = this.mainEl;
    main.innerHTML = '';
    let any = false;

    this.renderPlaybooks(main);
    if ((this.DATA.playbooks || []).length && (this.activeModule === 'all' || this.activeModule === '工作流')) {
      any = true;
    }

    for (const mod of this.DATA.modules) {
      if (this.activeModule !== 'all' && mod.id !== this.activeModule) continue;

      let catsHtml = '';
      let visibleCount = 0;
      for (const cat of mod.categories) {
        const filtered = cat.items.filter(it => this.matches(it, mod.label, cat.name, q));
        if (!filtered.length) continue;
        visibleCount += filtered.length;
        const items = filtered.map(it => this.renderCapItem(it)).join('');
        catsHtml += `<li><span class="cat-name">${escapeHtml(cat.name)}</span><ul class="items">${items}</ul></li>`;
      }
      if (!visibleCount) continue;
      any = true;

      const section = document.createElement('section');
      section.className = 'catalog-module';
      section.id = 'catalog-mod-' + mod.id;
      section.innerHTML = `
        <div class="module-head">
          <span class="module-icon" aria-hidden="true">${smallIcon('module')}</span>
          <div>
            <h3>${escapeHtml(mod.label)}</h3>
            <div class="sub">${visibleCount} 项能力</div>
          </div>
        </div>
        <ol class="cats">${catsHtml}</ol>`;
      main.appendChild(section);
    }

    if (!any) {
      main.innerHTML = '<div class="catalog-empty">没有匹配的能力</div>';
    } else {
      this.bindPromptPanels(main);
    }
  };

  CatalogPanel.prototype.renderNav = function renderNav() {
    const nav = this.navEl;
    const playbookCount = (this.DATA.playbooks || []).length;
    const buttons = [
      `<button type="button" data-id="all" class="${this.activeModule === 'all' ? 'active' : ''}"><span class="nav-label">全部</span><span class="count">${this.DATA.total_items}</span></button>`
    ];
    if (playbookCount > 0) {
      buttons.push(
        `<button type="button" data-id="工作流" class="${this.activeModule === '工作流' ? 'active' : ''}"><span class="nav-label">Playbook</span><span class="count">${playbookCount}</span></button>`
      );
    }
    for (const mod of this.DATA.modules) {
      if (mod.id === '工作流' && playbookCount > 0) continue;
      buttons.push(
        `<button type="button" data-id="${mod.id}" class="${this.activeModule === mod.id ? 'active' : ''}"><span class="nav-label">${escapeHtml(mod.label)}</span><span class="count">${mod.item_count}</span></button>`
      );
    }
    nav.innerHTML = buttons.join('');
    nav.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        this.activeModule = btn.dataset.id;
        this.renderNav();
        this.render();
        if (this.activeModule !== 'all') {
          const el = document.getElementById('catalog-mod-' + this.activeModule);
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
    const activeBtn = nav.querySelector('button.active');
    if (activeBtn) activeBtn.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  };

  CatalogPanel.prototype.bindEvents = function bindEvents() {
    if (this.searchEl) {
      this.searchEl.addEventListener('input', e => {
        this.query = e.target.value;
        this.render();
      });
    }
    this.root.addEventListener('click', e => {
      const runBtn = e.target.closest('.prompt-run');
      if (runBtn) {
        e.preventDefault();
        const line = runBtn.closest('.prompt-line');
        if (line) this.onRunPrompt(assemblePromptLine(line));
      }
    });
  };

  CatalogPanel.prototype.init = async function init(fetchData) {
    this.bindEvents();
    await this.load(fetchData);
  };

  global.CatalogPanel = CatalogPanel;
})(window);
